"""
Ninko Embedding-Router – Semantische Tie-Breaker-Stufe (R11).

Tritt in Kraft, wenn Keyword-Scoring zwei oder mehr Module mit gleichen Scores
liefert (kein klarer Gewinner). Nutzt die konfigurierte Embedding-Infrastruktur
(EMBED_MODEL / EMBED_BACKEND) und fällt auf TF-IDF zurück falls der
Embedding-Endpoint nicht verfügbar ist.

Keine neuen Abhängigkeiten — nutzt nur die bereits vorhandene LangChain-
Embedding-Konfiguration aus `core.llm_factory`.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
from collections import Counter
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ── TF-IDF Hilfsfunktionen (reines Python + numpy) ───────────────────────────

_TOKEN_RE = re.compile(r"[\wäöüÄÖÜß]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _bow(text: str) -> dict[str, float]:
    """Normierter Bag-of-Words (TF, max-normiert)."""
    tokens = _tokenize(text)
    if not tokens:
        return {}
    counts = Counter(tokens)
    max_count = max(counts.values())
    return {t: c / max_count for t, c in counts.items()}


def _cosine_dict(a: dict[str, float], b: dict[str, float]) -> float:
    """Kosinus-Ähnlichkeit zweier BOW-Vektoren."""
    if not a or not b:
        return 0.0
    dot = sum(a[t] * b[t] for t in a if t in b)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    return dot / (norm_a * norm_b) if norm_a * norm_b > 0.0 else 0.0


def _cosine_vec(a: list[float], b: list[float]) -> float:
    """Kosinus-Ähnlichkeit zweier dense Vektoren (numpy)."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    norm = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / norm) if norm > 0.0 else 0.0


# Mindest-Confidence, damit ein Embedding-Ergebnis akzeptiert wird.
# best/(best+second) >= Schwelle → klarer Gewinner.
_EMBED_MIN_CONFIDENCE: float = 0.54
_TFIDF_MAX_CONFIDENCE: float = 0.80  # TF-IDF-Ergebnisse werden nach oben begrenzt


# ── EmbeddingRouter ───────────────────────────────────────────────────────────


class EmbeddingRouter:
    """Semantischer Tie-Breaker auf Basis der konfigurierten Embedding-Infrastruktur.

    Lebenszyklus:
    1. Instanziierung (kein I/O).
    2. `update_module_descriptions()` wenn sich die Routing-Map ändert.
    3. `arank()` bei jedem Tie — gibt (modul, confidence) oder None zurück.
    """

    def __init__(self) -> None:
        self._embeddings = None  # LangChain Embeddings – lazy loaded
        self._embed_unavailable: bool = False  # gesetzt nach erstem Fehler
        self._module_vecs: dict[str, list[float]] = {}  # pre-computed dense vecs
        self._module_bow: dict[str, dict[str, float]] = {}  # TF-IDF fallback

    # ── Öffentliche Verwaltungs-API ───────────────────────────────────────────

    def update_module_descriptions(self, descriptions: dict[str, str]) -> None:
        """TF-IDF-Fallback neu aufbauen; dense Vektoren invalidieren.

        `descriptions` bildet Modulname → raumgetrennter Keyword-String.
        Wird synchron von `_refresh_routing_map()` aufgerufen.
        """
        self._module_bow = {name: _bow(text) for name, text in descriptions.items()}
        self._module_vecs.clear()
        logger.debug("EmbeddingRouter: %d Modul-Beschreibungen aktualisiert.", len(descriptions))

    # ── Kern-API ──────────────────────────────────────────────────────────────

    async def arank(
        self,
        message: str,
        candidates: list[str],
    ) -> tuple[str, float] | None:
        """Ranke Kandidaten nach semantischer Ähnlichkeit.

        Gibt (bestes_modul, confidence) oder None zurück.
        confidence ist top/(top+second) ∈ (0.5, 1.0].
        """
        if len(candidates) < 2:
            return None

        # 1. Embedding-basiert (primär)
        if not self._embed_unavailable:
            result = await self._embed_rank(message, candidates)
            if result is not None:
                return result

        # 2. TF-IDF-Fallback
        return self._tfidf_rank(message, candidates)

    # ── Embedding-Logik ───────────────────────────────────────────────────────

    async def _get_embeddings(self):
        if self._embeddings is None:
            from core.llm_factory import get_embeddings

            self._embeddings = get_embeddings()
        return self._embeddings

    async def _ensure_module_vecs(self, candidates: list[str]) -> bool:
        """Sicherstellen, dass alle Kandidaten-Vektoren vorhanden sind."""
        missing = [c for c in candidates if c not in self._module_vecs]
        if not missing:
            return True
        try:
            emb = await self._get_embeddings()
            texts = [
                " ".join(self._module_bow.get(c, {}).keys()) or c
                for c in missing
            ]
            loop = asyncio.get_running_loop()
            vecs: list[list[float]] = await loop.run_in_executor(
                None, lambda: emb.embed_documents(texts)
            )
            for name, vec in zip(missing, vecs):
                self._module_vecs[name] = vec
            return True
        except Exception as exc:
            logger.warning(
                "EmbeddingRouter: Embedding-Precompute fehlgeschlagen (%s). "
                "Nutze TF-IDF-Fallback für zukünftige Anfragen.",
                exc,
            )
            self._embed_unavailable = True
            return False

    async def _embed_rank(
        self,
        message: str,
        candidates: list[str],
    ) -> tuple[str, float] | None:
        if not await self._ensure_module_vecs(candidates):
            return None
        try:
            emb = await self._get_embeddings()
            loop = asyncio.get_event_loop()
            query_vec: list[float] = await loop.run_in_executor(
                None, lambda: emb.embed_query(message)
            )
            sims = {c: _cosine_vec(query_vec, self._module_vecs[c]) for c in candidates}
            sorted_sims = sorted(sims.items(), key=lambda x: x[1], reverse=True)
            best_mod, best_sim = sorted_sims[0]
            second_sim = sorted_sims[1][1]
            total = best_sim + second_sim
            confidence = best_sim / total if total > 0.0 else 0.5
            if confidence < _EMBED_MIN_CONFIDENCE:
                logger.debug(
                    "EmbeddingRouter: Embedding-Confidence %.2f zu niedrig (Schwelle %.2f) → kein Treffer.",
                    confidence,
                    _EMBED_MIN_CONFIDENCE,
                )
                return None
            logger.debug(
                "EmbeddingRouter: Embedding-Winner=%s (conf=%.2f) über %s",
                best_mod,
                confidence,
                candidates,
            )
            return best_mod, confidence
        except Exception as exc:
            logger.warning("EmbeddingRouter: Embedding-Ranking fehlgeschlagen: %s", exc)
            self._embed_unavailable = True
            return None

    # ── Soft-Learning via Korrektur-Beispiele (R12) ──────────────────────────

    def incorporate_corrections(self, module: str, examples: list[str]) -> None:
        """Blended Korrektur-Beispiele in das Modul-BOW ein (Soft-Learning).

        Tokens aus Nachrichten, die der User zu `module` korrigiert hat, werden
        mit Gewicht 0.3/N in das BOW addiert und re-normiert. Der gecachte dense
        Vektor wird invalidiert.
        """
        if not examples or module not in self._module_bow:
            return
        base = dict(self._module_bow[module])
        weight_per_msg = 0.3 / len(examples)
        for msg in examples:
            for token in _tokenize(msg):
                if len(token) >= 4:
                    base[token] = base.get(token, 0.0) + weight_per_msg
        max_val = max(base.values()) if base else 1.0
        self._module_bow[module] = {t: v / max_val for t, v in base.items()}
        self._module_vecs.pop(module, None)
        logger.debug(
            "EmbeddingRouter: Correction-Learning für %s mit %d Beispielen.",
            module,
            len(examples),
        )

    # ── TF-IDF-Fallback ───────────────────────────────────────────────────────

    def _tfidf_rank(
        self,
        message: str,
        candidates: list[str],
    ) -> tuple[str, float] | None:
        query_bow = _bow(message)
        if not query_bow:
            return None
        sims = {
            c: _cosine_dict(query_bow, self._module_bow.get(c, {}))
            for c in candidates
        }
        sorted_sims = sorted(sims.items(), key=lambda x: x[1], reverse=True)
        best_mod, best_sim = sorted_sims[0]
        if best_sim == 0.0:
            return None
        second_sim = sorted_sims[1][1]
        total = best_sim + second_sim
        raw_confidence = best_sim / total if total > 0.0 else 0.5
        confidence = min(raw_confidence, _TFIDF_MAX_CONFIDENCE)
        logger.debug(
            "EmbeddingRouter: TF-IDF-Winner=%s (conf=%.2f) über %s",
            best_mod,
            confidence,
            candidates,
        )
        return best_mod, confidence
