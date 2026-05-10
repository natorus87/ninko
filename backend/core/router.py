"""
Ninko Keyword-Router – Isolierte Routing-Logik (R10).

Enthält alle Konstanten, Pure Functions und die KeywordRouter-Klasse
für das 4-Tier-Routing. Keine Abhängigkeiten zu LangChain / BaseAgent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields as _dc_fields
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# ── Token-Normalisierung ──────────────────────────────────────────────────────

_GERMAN_SEPARABLE_PREFIXES: tuple[str, ...] = (
    "zurueck",
    "zurück",
    "ab",
    "an",
    "auf",
    "aus",
    "ein",
    "mit",
    "nach",
    "vor",
    "weg",
    "zu",
)

_ROUTING_SUFFIXES: tuple[str, ...] = (
    "ung",
    "en",
    "es",
    "e",
    "n",
    "s",
)


def normalize_routing_token(token: str) -> str:
    """Normalize one token for conservative keyword routing."""
    normalized = token.lower()
    for prefix in _GERMAN_SEPARABLE_PREFIXES:
        marker = f"{prefix}zu"
        if normalized.startswith(marker) and len(normalized) > len(marker) + 3:
            normalized = f"{prefix}{normalized[len(marker):]}"
            break
    if normalized.endswith("ungen"):
        return normalized
    if normalized.endswith("ern") and len(normalized) > 6:
        return normalized[:-1]
    for suffix in _ROUTING_SUFFIXES:
        if normalized.endswith(suffix) and len(normalized) > len(suffix) + 4:
            return normalized[: -len(suffix)]
    return normalized


def count_normalized_keyword_matches(keyword: str, text: str) -> int:
    """Count single-token keyword matches after conservative token normalization."""
    if not re.fullmatch(r"[\wäöüÄÖÜß-]+", keyword):
        return 0
    keyword_tokens = re.findall(r"[\wäöüÄÖÜß]+", keyword.lower())
    if len(keyword_tokens) != 1:
        return 0
    normalized_keyword = normalize_routing_token(keyword_tokens[0])
    if len(normalized_keyword) < 5:
        return 0
    tokens = re.findall(r"[\wäöüÄÖÜß]+", text.lower())
    return sum(1 for token in tokens if normalize_routing_token(token) == normalized_keyword)


# ── Routing-Konstanten ────────────────────────────────────────────────────────

_CORE_ALWAYS_MODULES: frozenset[str] = frozenset(
    {
        "web_search",
        "image_gen",
        "codelab",
        "dataviz",
    }
)

_UTILITY_MODULES: frozenset[str] = frozenset(
    {
        "web_search",
        "image_gen",
        "telegram",
        "email",
        "teams",
    }
)

_MULTISTEP_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bund\s+dann\b",
        r"\bund\s+danach\b",
        r"\bdanach\b",
        r"\banschlie[ßs]end\b",
        r"\bals\s+n[äa]chstes\b",
        r"\bzuerst\b.{1,80}\bdann\b",
        r"\berst\b.{1,80}\bdann\b",
        r"\bnachdem\b",
        r"\bwenn\s+fertig\b",
        r"\bim\s+anschluss\b",
        r"\bthen\b",
        r"\bafter\s+that\b",
        r"\bfollowed\s+by\b",
        r"\bwhen\s+done\b",
    ]
]

ROUTING_MIN_CONFIDENT_SCORE: int = 2
ROUTING_MIN_CONFIDENT_MARGIN: int = 2
ROUTING_COMPOUND_BALANCE_RATIO: float = 0.4

# ── Routing-Konfiguration ─────────────────────────────────────────────────────


@dataclass
class RoutingConfig:
    """Routing-Konfiguration des Orchestrators (session-scoped).

    Zwei Pfade:
    - Tier 2 (keyword fast-path): Einzelnes Modul eindeutig erkannt → direkt delegieren.
    - Tier 1 (invoke): Alles andere → Orchestrator-ReAct-Loop entscheidet selbst
      via call_module_agent / run_pipeline / create_custom_agent / direkte Antwort.
    """

    tier1_enabled: bool = True
    tier2_enabled: bool = True
    tier4_enabled: bool = True
    preset: str = "default"

    @classmethod
    def from_dict(cls, d: dict) -> "RoutingConfig":
        known = {f.name for f in _dc_fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in _dc_fields(self)}


ROUTING_PRESETS: dict[str, dict] = {
    "default": {},
    "fast": {"preset": "fast", "tier4_enabled": False},
    "module-only": {
        "preset": "module-only",
        "tier1_enabled": False,
        "tier4_enabled": False,
    },
}

# Session-Routing-State (Redis-TTL und Schlüssel)
SESSION_ROUTING_TTL: float = 86400.0

_SPEED_SIGNALS: frozenset[str] = frozenset(
    {
        "schnell",
        "schnelle",
        "schneller",
        "schnelles",
        "quick",
        "fast",
        "kurz",
        "kurze",
        "kurzer",
        "kurzes",
        "brief",
        "knapp",
        "simplified",
        "einfach",
        "kürzer",
        "kürze",
    }
)


def routing_config_key(session_id: str) -> str:
    return f"ninko:orchestrator:routing:{session_id}"


def routing_stats_key(session_id: str) -> str:
    return f"ninko:orchestrator:routing_stats:{session_id}"


# ── KeywordRouter ─────────────────────────────────────────────────────────────

_BOT_CONTEXT_RE = re.compile(
    r"^\[(?:Telegram Chat-ID|Teams User|Erkannte Sprache):[^\]]+\]\n?",
)

_CORE_OVERRIDE_PATTERNS: list[re.Pattern] = [
    re.compile(p)
    for p in [
        r"\bwork?flows?\b",
        r"\bworflows?\b",
        r"\bagenten?\b",
        r"\bagent\s*erstellen\b",
        r"\bneuen?\s*agent\b",
        r"\bcreate\s*agent\b",
        r"\bnew\s*agent\b",
        r"\bcli\s*befehl\b",
        r"\blokales?\s*kommando\b",
        r"\bskript\s*ausführen\b",
        r"\bcli\s*command\b",
        r"\brun\s*script\b",
        r"\bshell\s*command\b",
        r"\bterminal\b",
        r"\bsystembefehl\b",
        r"\bping\b",
        r"\buptime\b",
    ]
]


class KeywordRouter:
    """Zustandsbehafteter Keyword-Router für das 4-Tier-Routing.

    Kapselt Scoring, Compound-Erkennung und Tier-Klassifikation.
    Keine Abhängigkeiten zu LangChain oder BaseAgent.
    """

    def __init__(self, routing_map: dict[str, str]) -> None:
        self._routing_map = routing_map
        self.last_confidence: float | None = None

    def update_routing_map(self, routing_map: dict[str, str]) -> None:
        self._routing_map = routing_map

    @staticmethod
    def strip_bot_context(message: str) -> str:
        """Entfernt Bot-Kontext-Präfixe vor dem Keyword-Routing."""
        return _BOT_CONTEXT_RE.sub("", message).strip()

    def get_scores(self, text: str) -> dict[str, int]:
        """Keyword-Scoring für einen Text. Gibt Module → Score zurück."""
        text_lower = text.lower()
        scores: dict[str, int] = {}
        for keyword, module_name in self._routing_map.items():
            kw_lower = keyword.lower()
            matches = len(re.findall(r"\b" + re.escape(kw_lower) + r"\b", text_lower))
            if matches == 0:
                matches = count_normalized_keyword_matches(kw_lower, text_lower)
            module_aliases = {
                module_name.lower(),
                module_name.lower().replace("_", " "),
                module_name.lower().replace("_", ""),
                module_name.lower().replace("-", " "),
                module_name.lower().replace("-", ""),
            }
            weight = 5 if kw_lower in module_aliases else 1
            if matches > 0:
                scores[module_name] = scores.get(module_name, 0) + (matches * weight)
        return scores

    def has_multistep_indicators(
        self,
        message: str,
        current_scores: dict[str, int],
    ) -> bool:
        """Erkennt explizite sequentielle Multi-Modul-Anfragen."""
        msg_lower = message.lower()
        has_multistep = any(p.search(msg_lower) for p in _MULTISTEP_PATTERNS)

        qualified = []
        for mod, score in current_scores.items():
            if score >= 2:
                qualified.append(mod)
                continue
            if mod in _UTILITY_MODULES and score >= 1:
                qualified.append(mod)

        if len(qualified) >= 2:
            return has_multistep

        if not has_multistep:
            return False
        weak_hits = [mod for mod, score in current_scores.items() if score >= 1]
        has_utility = any(mod in _UTILITY_MODULES for mod in weak_hits)
        has_other = any(mod not in _UTILITY_MODULES for mod in weak_hits)
        return has_utility and has_other

    @staticmethod
    def has_confident_top_module(top_score: int, second_score: int) -> bool:
        """Return True when score and margin make the top module unambiguous."""
        return (
            top_score >= ROUTING_MIN_CONFIDENT_SCORE
            and top_score >= second_score + ROUTING_MIN_CONFIDENT_MARGIN
        )

    def detect_module(
        self,
        message: str,
        chat_history: list[dict] | None = None,
    ) -> tuple[str | None, bool, float | None]:
        """Keyword-Fast-Path. Gibt (modul, is_compound, confidence) zurück.

        - (modul, False, conf): genau ein eindeutiges Modul → Tier 2
        - (None, True, None):   mehrere Module → Compound → Tier 4
        - (None, False, None):  kein Treffer oder Tier-4-Guard → Tier 1

        Setzt self.last_confidence nach jedem Aufruf (Rückwärtskompatibilität).
        """
        current_scores = self.get_scores(message)
        msg_lower = message.lower()

        if not current_scores:
            for pattern in _CORE_OVERRIDE_PATTERNS:
                if re.search(pattern, msg_lower):
                    self.last_confidence = None
                    return None, False, None

        if not current_scores and chat_history:
            history_text = " ".join(
                m.get("content", "").strip()
                for m in chat_history[-3:]
                if m.get("content")
            )
            if not history_text:
                self.last_confidence = None
                return None, False, None
            history_scores = self.get_scores(history_text)
            if len(history_scores) == 1:
                self.last_confidence = 0.5
                return next(iter(history_scores)), False, 0.5
            self.last_confidence = None
            return None, False, None

        if not current_scores:
            self.last_confidence = None
            return None, False, None

        if len(current_scores) == 1:
            self.last_confidence = 1.0
            return next(iter(current_scores)), False, 1.0

        filtered: dict[str, int] = {}
        for mod, score in current_scores.items():
            if mod in _UTILITY_MODULES:
                if mod in _CORE_ALWAYS_MODULES:
                    filtered[mod] = score
                    continue
                if (
                    mod in msg_lower
                    or mod.replace("_", " ") in msg_lower
                    or mod.replace("_", "") in msg_lower
                ):
                    filtered[mod] = score
            else:
                filtered[mod] = score

        if len(filtered) <= 1:
            if filtered:
                self.last_confidence = 1.0
                return next(iter(filtered)), False, 1.0
            self.last_confidence = None
            return None, False, None

        sorted_f = sorted(filtered.items(), key=lambda x: x[1], reverse=True)
        top_score = sorted_f[0][1]
        second_score = sorted_f[1][1]

        if (
            top_score >= 2
            and second_score >= 2
            and second_score >= (ROUTING_COMPOUND_BALANCE_RATIO * top_score)
            and self.has_multistep_indicators(message, filtered)
        ):
            self.last_confidence = None
            return None, True, None

        if not self.has_confident_top_module(top_score, second_score):
            self.last_confidence = None
            return None, False, None

        conf = top_score / (top_score + second_score)
        self.last_confidence = conf
        return sorted_f[0][0], False, conf

    def classify_tier(
        self,
        message: str,
        chat_history: list[dict] | None = None,
        cfg: RoutingConfig | None = None,
    ) -> tuple[int, str | None, float | None]:
        """3-Tier-Routing. Gibt (tier, target_module_or_None, confidence) zurück."""
        if cfg is None:
            cfg = RoutingConfig()

        routing_message = self.strip_bot_context(message)
        target_module, is_compound, confidence = self.detect_module(routing_message, chat_history)

        if cfg.tier4_enabled:
            if is_compound:
                return 4, None, None
            current_scores = self.get_scores(routing_message)
            if self.has_multistep_indicators(routing_message, current_scores):
                return 4, None, None

        if cfg.tier2_enabled and target_module:
            return 2, target_module, confidence

        return 1, None, None
