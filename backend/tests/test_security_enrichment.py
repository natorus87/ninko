"""Unit-Tests fuer LLM-Enrichment (Task 12)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.security.enrichment import _extract_json, enrich_finding
from modules.security.models import Finding, Severity

pytestmark = pytest.mark.unit


def _finding(**kw) -> Finding:
    defaults = {
        "scan_run_id": "run-1", "target_id": "target-1", "fingerprint": "fp1", "scanner_id": "trivy",
        "title": "Vulnerable libfoo", "severity": Severity.HIGH, "original_severity": Severity.HIGH,
    }
    defaults.update(kw)
    return Finding(**defaults)


@pytest.fixture
def security_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import core.config as core_config

    core_config._settings = None
    from modules.security import db as security_db_module

    security_db_module._db_path = None
    security_db_module._init_event = None
    yield security_db_module
    security_db_module._db_path = None
    security_db_module._init_event = None
    core_config._settings = None


# ── _extract_json ──────────────────────────────────────────────────────


def test_extract_json_strips_think_block():
    text = "<think>reasoning here</think>{\"a\": 1}"
    assert _extract_json(text) == {"a": 1}


def test_extract_json_finds_object_amid_prose():
    text = "Here is my answer:\n{\"a\": 1, \"b\": 2}\nHope that helps!"
    assert _extract_json(text) == {"a": 1, "b": 2}


def test_extract_json_raises_when_no_object():
    with pytest.raises(ValueError):
        _extract_json("no json here at all")


# ── enrich_finding ─────────────────────────────────────────────────────


def _fake_llm(response_text: str):
    llm = MagicMock()
    llm.model = "test-model"
    llm.ainvoke = AsyncMock(return_value=MagicMock(content=response_text))
    return llm


@pytest.mark.asyncio
async def test_enrich_finding_unknown_finding_raises(security_db):
    with pytest.raises(ValueError, match="Unbekanntes Finding"):
        await enrich_finding("does-not-exist")


@pytest.mark.asyncio
async def test_enrich_finding_valid_llm_output(security_db):
    finding = _finding()
    stored, _ = await security_db.upsert_finding(finding)

    valid_json = (
        '{"effective_severity": "high", "confidence": 0.85, "exploitability": "medium", '
        '"business_impact": "Could allow lateral movement.", "false_positive_probability": 0.05, '
        '"correlated_findings": [], "remediation_steps": ["Update libfoo to 1.0.1", "Redeploy"], '
        '"patch_proposal": null, "requires_human_review": false}'
    )
    with patch("modules.security.enrichment.get_llm", return_value=_fake_llm(valid_json)):
        enrichment = await enrich_finding(stored.id)

    assert enrichment.validation_status == "valid"
    assert enrichment.effective_severity == Severity.HIGH
    assert enrichment.confidence == 0.85
    assert "Update libfoo" in enrichment.remediation_proposal
    assert enrichment.requires_human_review is False


@pytest.mark.asyncio
async def test_enrich_finding_invalid_llm_output_falls_back_conservatively(security_db):
    finding = _finding(severity=Severity.MEDIUM, original_severity=Severity.MEDIUM)
    stored, _ = await security_db.upsert_finding(finding)

    with patch("modules.security.enrichment.get_llm", return_value=_fake_llm("this is not json")):
        enrichment = await enrich_finding(stored.id)

    assert enrichment.validation_status == "invalid"
    assert enrichment.requires_human_review is True
    assert enrichment.confidence == 0.0
    assert enrichment.effective_severity == Severity.MEDIUM  # Fallback auf Original-Severity


@pytest.mark.asyncio
async def test_enrich_finding_stores_separately_from_original(security_db):
    """Original-Finding darf durch Enrichment NIE veraendert werden."""
    finding = _finding()
    stored, _ = await security_db.upsert_finding(finding)

    valid_json = (
        '{"effective_severity": "low", "confidence": 0.9, "exploitability": "low", '
        '"business_impact": "Minor.", "false_positive_probability": 0.5, '
        '"correlated_findings": [], "remediation_steps": [], "patch_proposal": null, '
        '"requires_human_review": false}'
    )
    with patch("modules.security.enrichment.get_llm", return_value=_fake_llm(valid_json)):
        await enrich_finding(stored.id)

    unchanged = await security_db.get_finding(stored.id)
    assert unchanged.severity == Severity.HIGH  # unveraendert, obwohl LLM "low" einschaetzt
    assert unchanged.original_severity == Severity.HIGH


@pytest.mark.asyncio
async def test_enrich_finding_never_sends_secrets_in_prompt(security_db):
    """Beschreibung/Metadata koennten theoretisch sensible Daten enthalten (z.B. bei
    schlecht konfigurierten Scannern) — der Prompt darf trotzdem nur die definierten
    Felder enthalten, kein Dump von finding.metadata."""
    finding = _finding(metadata={"secret_token": "sk-should-never-appear-in-prompt"})
    stored, _ = await security_db.upsert_finding(finding)

    fake_llm = _fake_llm('{"effective_severity": "high", "confidence": 0.5, "exploitability": "unknown", '
                          '"business_impact": "", "false_positive_probability": 0.1, '
                          '"correlated_findings": [], "remediation_steps": [], "patch_proposal": null, '
                          '"requires_human_review": true}')
    with patch("modules.security.enrichment.get_llm", return_value=fake_llm):
        await enrich_finding(stored.id)

    sent_messages = fake_llm.ainvoke.call_args[0][0]
    sent_text = " ".join(m.content for m in sent_messages)
    assert "sk-should-never-appear-in-prompt" not in sent_text
