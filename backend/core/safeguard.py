"""
Ninko Safeguard Middleware
Modell-agnostisch: funktioniert mit jedem OpenAI-compatible LLM.

Integration in routes_chat.py (vor dem 4-tier routing):
    safeguard = request.app.state.safeguard
    if safeguard:
        result = await safeguard.check(user_message)
        if result.requires_confirmation and not body.confirmed:
            return ChatResponse(confirmation_required=True, safeguard=result.to_dict(), ...)
"""

import json
import re
import logging
from dataclasses import dataclass
from enum import Enum

from openai import AsyncOpenAI

logger = logging.getLogger("ninko.core.safeguard")


# ─── Classifier Prompt ────────────────────────────────────────────────────────
# Dieser Prompt macht jedes OpenAI-compatible Modell zum Classifier.
# Kein Harmony-Format nötig — funktioniert mit Llama, Qwen, Mistral, Gemma, etc.

SAFEGUARD_SYSTEM_PROMPT = """You are a strict safety classifier for an IT automation platform.
Your ONLY job is to classify user requests. You NEVER execute actions yourself.

## YOUR TASK
Analyze the user input and classify whether it requests a DESTRUCTIVE or STATE-CHANGING action
that requires explicit user confirmation before execution.

## CATEGORY DEFINITIONS

**DESTRUCTIVE** — irreversible data loss:
- Delete, remove, drop, wipe, purge, truncate, destroy
- Examples: delete pod, drop database, rm -rf, kubectl delete, pvremove

**STATE_CHANGING** — modifies existing state:
- Update, modify, patch, overwrite, reset, change, edit, set, apply
- Examples: change password, update config, scale deployment, edit secret

**SAFE** — read-only or informational:
- Get, list, show, describe, status, logs, explain, how-to, what-is
- Examples: get pods, show logs, describe node, how do I...

## OUTPUT RULES
You MUST respond with ONLY a single JSON object. No explanation, no markdown, no preamble.

Format:
{"violation": 0 or 1, "category": "SAFE" | "DESTRUCTIVE" | "STATE_CHANGING", "rationale": "one sentence"}

violation=1 means confirmation required.
violation=0 means safe to execute directly.

## EXAMPLES

Input: "delete all pods in production namespace"
Output: {"violation": 1, "category": "DESTRUCTIVE", "rationale": "Requests deletion of production pods, irreversible action."}

Input: "scale deployment frontend to 3 replicas"
Output: {"violation": 1, "category": "STATE_CHANGING", "rationale": "Modifies deployment replica count."}

Input: "show me all nodes in the cluster"
Output: {"violation": 0, "category": "SAFE", "rationale": "Read-only query, no state change."}

Input: "what is the CPU usage of my proxmox host?"
Output: {"violation": 0, "category": "SAFE", "rationale": "Informational query, no action executed."}

Input: "update the database password in all configmaps"
Output: {"violation": 1, "category": "STATE_CHANGING", "rationale": "Modifies credentials across multiple resources."}

Input: "list all GLPI tickets with status open"
Output: {"violation": 0, "category": "SAFE", "rationale": "Read-only query on ticket system."}

Input: "wipe the ceph pool data"
Output: {"violation": 1, "category": "DESTRUCTIVE", "rationale": "Irreversible deletion of entire storage pool."}

Classify the user input now. Respond ONLY with the JSON object."""


# ─── Dataclasses ──────────────────────────────────────────────────────────────

class ActionCategory(str, Enum):
    SAFE = "SAFE"
    DESTRUCTIVE = "DESTRUCTIVE"
    STATE_CHANGING = "STATE_CHANGING"
    UNKNOWN = "UNKNOWN"  # Fallback wenn Parse fehlschlägt


@dataclass
class SafeguardResult:
    requires_confirmation: bool
    category: ActionCategory
    rationale: str
    raw_response: str = ""

    def to_dict(self) -> dict:
        return {
            "requires_confirmation": self.requires_confirmation,
            "category": self.category.value,
            "rationale": self.rationale,
        }


# ─── Safeguard Middleware ─────────────────────────────────────────────────────

class SafeguardMiddleware:
    """
    Modell-agnostischer Safeguard mit globalem und per-Agent State.

    - Global:    safeguard.enabled        → gilt für interaktiven Chat
    - Per-Agent: safeguard.check(..., agent_id="xyz")
                 liest den gespeicherten State aus dem AgentConfigStore (Redis)
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        policy: str | None = None,
        timeout: float = 8.0,
        enabled: bool = True,
        agent_store: "AgentConfigStore | None" = None,
    ):
        self.client = client
        self.model = model
        self.policy = policy or SAFEGUARD_SYSTEM_PROMPT
        self.timeout = timeout
        self.enabled = enabled          # globaler Toggle (Chat)
        self.agent_store = agent_store  # None = kein per-Agent Persistence

    # ── Global Toggle ──────────────────────────────────────────────────────────
    def enable(self):
        self.enabled = True
        logger.info("[Safeguard] Global aktiviert.")

    def disable(self):
        self.enabled = False
        logger.warning("[Safeguard] Global DEAKTIVIERT — Autonomer Modus aktiv.")

    # ── Per-Agent Toggle (persistiert via AgentConfigStore in Redis) ───────────
    async def enable_for_agent(self, agent_id: str):
        if self.agent_store:
            await self.agent_store.set_safeguard(agent_id, enabled=True)
        logger.info("[Safeguard] Für Agent '%s' aktiviert.", agent_id)

    async def disable_for_agent(self, agent_id: str):
        if self.agent_store:
            await self.agent_store.set_safeguard(agent_id, enabled=False)
        logger.warning("[Safeguard] Für Agent '%s' DEAKTIVIERT — Autonomer Modus.", agent_id)

    async def _is_enabled_for(self, agent_id: str | None) -> bool:
        """
        Priorität: per-Agent Config > globaler Toggle.
        Kein agent_id → globaler State gilt.
        """
        if agent_id and self.agent_store:
            state = await self.agent_store.get_safeguard(agent_id)
            if state is not None:
                return state
        return self.enabled

    async def check(self, user_input: str, agent_id: str | None = None) -> SafeguardResult:
        """
        Klassifiziert den User-Input via LLM.

        agent_id=None  → globaler State wird geprüft
        agent_id="xyz" → per-Agent gespeicherter State wird geprüft

        Wenn disabled → SAFE ohne LLM-Call.
        Im Fehlerfall (Timeout, Parse-Error) → fail-safe: requires_confirmation=True.
        """
        if not await self._is_enabled_for(agent_id):
            return SafeguardResult(
                requires_confirmation=False,
                category=ActionCategory.SAFE,
                rationale="Safeguard deaktiviert — autonomer Modus aktiv.",
            )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.policy},
                    {"role": "user",   "content": user_input},
                ],
                temperature=0.0,   # deterministisch, kein kreatives Output
                max_tokens=150,    # Classifier braucht nicht mehr
                timeout=self.timeout,
            )

            raw = response.choices[0].message.content.strip()
            return self._parse(raw)

        except Exception as e:
            logger.warning(
                "[Safeguard] Classifier-Aufruf fehlgeschlagen: %s — fail-safe: Bestätigung erforderlich",
                e,
            )
            return SafeguardResult(
                requires_confirmation=True,
                category=ActionCategory.UNKNOWN,
                rationale=f"Classifier nicht erreichbar ({type(e).__name__}) — Bestätigung als Fallback erforderlich.",
                raw_response=str(e),
            )

    def _parse(self, raw: str) -> SafeguardResult:
        """
        Parst den JSON-Output des Classifiers.
        Robust gegen Markdown-Wrapping (```json ... ```) und Whitespace.
        """
        # Markdown-Fences entfernen falls Modell sie trotzdem setzt
        cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()

        try:
            data = json.loads(cleaned)
            violation = int(data.get("violation", 1))  # Default: Bestätigung erforderlich
            category_str = data.get("category", "UNKNOWN").upper()
            rationale = data.get("rationale", "Keine Begründung angegeben.")

            try:
                category = ActionCategory(category_str)
            except ValueError:
                category = ActionCategory.UNKNOWN

            return SafeguardResult(
                requires_confirmation=violation == 1,
                category=category,
                rationale=rationale,
                raw_response=raw,
            )

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("[Safeguard] Parse-Fehler: %s | raw='%s'", e, raw)
            return SafeguardResult(
                requires_confirmation=True,
                category=ActionCategory.UNKNOWN,
                rationale="Parse-Fehler — Bestätigung als Fallback erforderlich.",
                raw_response=raw,
            )


# ─── Bot-Confirmation Helper ──────────────────────────────────────────────────

# Schlüssel-Pattern für pending Bot-Nachrichten (TTL 300s)
SAFEGUARD_PENDING_KEY = "ninko:safeguard_pending:{session_id}"

# Bestätigungswörter (DE + EN)
_CONFIRMATION_WORDS: frozenset[str] = frozenset({
    "ja", "jo", "jep", "jup", "yes", "yep", "y",
    "bestätige", "bestätigen", "bestätigt",
    "confirm", "confirmed", "ok", "okay",
    "weiter", "ausführen", "run",
})


def is_bot_confirmation(text: str) -> bool:
    """
    Prüft ob der Text eine Bestätigung für eine pending Safeguard-Aktion ist.
    Unterstützt kurze Einzel-Wort-Antworten (DE + EN).
    """
    normalized = text.strip().lower().rstrip("!.")
    return normalized in _CONFIRMATION_WORDS


# ─── Type alias für Forward Reference ─────────────────────────────────────────
# (AgentConfigStore wird in agent_config_store.py definiert)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.agent_config_store import AgentConfigStore
