"""Security Core — LLM-Enrichment.

Nutzt Ninkos bestehende, provider-agnostische LLM-Abstraktion
(core.llm_factory.get_llm()) — kein fest verdrahteter Provider (LiteLLM,
vLLM, Ollama, OpenAI-kompatibel funktionieren alle gleich). Strukturierter
Output wird strikt gegen LLMFindingAssessment (Pydantic) validiert;
ungueltiger Output fuehrt NICHT zu einer automatischen Aktion — das LLM
assistiert nur, es aendert nie ein Finding direkt (siehe Modul-Docstring
policy.py: "Der Prompt eines Agents ist keine Sicherheitsgrenze").

Original-Finding und Enrichment bleiben strikt getrennt gespeichert (siehe
FindingEnrichment-Modell, Task 1). Keine Secrets/Tokens werden an das LLM
gesendet — der Prompt enthaelt nur normalisierte Finding-Metadaten, niemals
credentials_reference-Inhalte oder rohe Scanner-Secrets (Gitleaks redigiert
den Secret-Wert bereits vor dem Speichern, siehe adapters/gitleaks.py).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from core.llm_factory import get_llm

from . import db
from .models import Finding, FindingEnrichment, LLMFindingAssessment

logger = logging.getLogger("ninko.modules.security.enrichment")

_RE_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_PROMPT_VERSION = "v1"
_MAX_DESCRIPTION_CHARS = 1500

_SYSTEM_PROMPT = """You are a security analyst assistant. You receive a single, already-detected \
security finding produced by an automated scanner — you did not detect it and must not second-\
guess whether it is technically present. Your job is only to prioritize it in context, assess \
exploitability and business impact, estimate false-positive likelihood, and propose remediation.

Respond with a single JSON object matching exactly this schema, no prose before or after it:
{
  "effective_severity": "info"|"low"|"medium"|"high"|"critical",
  "confidence": <float 0.0-1.0>,
  "exploitability": "<short label, e.g. low|medium|high|unknown>",
  "business_impact": "<one or two sentences>",
  "false_positive_probability": <float 0.0-1.0>,
  "correlated_findings": [],
  "remediation_steps": ["<concrete step 1>", "<concrete step 2>"],
  "patch_proposal": <string with a concrete config/code change, or null>,
  "requires_human_review": <bool>
}

Never invent details not present in the finding. If uncertain, set requires_human_review=true \
and keep confidence low. Never claim a fix has been applied — you only propose."""


def _build_input_text(finding: Finding) -> str:
    return (
        f"scanner_id: {finding.scanner_id}\n"
        f"title: {finding.title}\n"
        f"description: {finding.description[:_MAX_DESCRIPTION_CHARS]}\n"
        f"severity: {finding.severity.value}\n"
        f"category: {finding.category}\n"
        f"cve: {finding.cve or '-'}\n"
        f"cwe: {finding.cwe or '-'}\n"
        f"cvss: {finding.cvss if finding.cvss is not None else '-'}\n"
        f"resource_type: {finding.resource_type}\n"
        f"resource_identifier: {finding.resource_identifier}\n"
        f"location: {finding.location}\n"
        f"occurrence_count: {finding.occurrence_count}\n"
    )


def _extract_json(text: str) -> dict:
    cleaned = _RE_THINK.sub("", text).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("LLM-Antwort enthaelt kein JSON-Objekt.")
    return json.loads(cleaned[start : end + 1])


async def enrich_finding(finding_id: str, *, tenant_id: str = "") -> FindingEnrichment:
    """Ruft das LLM einmal fuer ein Finding auf, validiert den Output strikt und
    speichert ihn getrennt vom Original-Finding.

    Wirft ValueError, wenn das Finding nicht existiert. Liefert bei ungueltigem
    LLM-Output KEINEN Fehler, sondern ein konservatives Enrichment mit
    validation_status='invalid' und requires_human_review=True — ein Format-
    Fehler des LLM darf den restlichen Scan-Flow nicht zum Absturz bringen.
    """
    finding = await db.get_finding(finding_id, tenant_id=tenant_id)
    if finding is None:
        raise ValueError(f"Unbekanntes Finding: {finding_id}")

    input_text = _build_input_text(finding)
    input_hash = hashlib.sha256(input_text.encode("utf-8")).hexdigest()

    llm = get_llm()
    response = await llm.ainvoke([
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=input_text),
    ])
    raw_text = response.content if isinstance(response.content, str) else str(response.content)

    validation_status = "valid"
    try:
        payload = _extract_json(raw_text)
        assessment = LLMFindingAssessment.model_validate(payload)
    except (ValueError, json.JSONDecodeError, TypeError) as exc:
        logger.warning("LLM-Enrichment fuer Finding %s lieferte ungueltigen Output: %s", finding_id, exc)
        validation_status = "invalid"
        assessment = LLMFindingAssessment(
            effective_severity=finding.severity,
            confidence=0.0,
            exploitability="unknown",
            business_impact="",
            false_positive_probability=0.0,
            requires_human_review=True,
        )

    model_name = getattr(llm, "model", None) or getattr(llm, "model_name", None) or "unknown"
    enrichment = FindingEnrichment(
        finding_id=finding_id,
        model=str(model_name),
        prompt_version=_PROMPT_VERSION,
        input_hash=input_hash,
        effective_severity=assessment.effective_severity,
        exploitability=assessment.exploitability,
        business_impact=assessment.business_impact,
        confidence=assessment.confidence,
        summary=assessment.business_impact,
        correlation_ids=assessment.correlated_findings,
        false_positive_probability=assessment.false_positive_probability,
        remediation_proposal=(
            "\n".join(f"- {s}" for s in assessment.remediation_steps) if assessment.remediation_steps else None
        ),
        patch_proposal=assessment.patch_proposal,
        requires_human_review=assessment.requires_human_review,
        validation_status=validation_status,
    )
    return await db.create_enrichment(enrichment)
