"""
Ninko Semantic Memory – ChromaDB-basiert.
Speichert Incidents, Runbooks und Chat-Kontext als Embeddings.

ABGRENZUNG zu den anderen Kontextsystemen:
  Memory   = WAS wurde in der Vergangenheit erlebt/gelernt?
             Semantische Fakten aus Chat-Interaktionen werden als Vektor-Embeddings
             in ChromaDB gespeichert und per RAG-Suche (top-k) pro Request abgerufen.
             Enthält Fakten über Systeme, Vorfälle, Konfigurationen.

  Soul     = WER ist der Agent? Charakter, dauerhafter Stil (soul_manager.py).

  Skills   = WIE löst der Agent Aufgaben? Prozedurales Wissen (skills_manager.py).
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import uuid
from datetime import datetime, timezone

import chromadb
from chromadb import Settings as ChromaSettings

from core.config import get_settings
from core.llm_factory import get_embeddings

logger = logging.getLogger("ninko.memory")

_CHROMA_MAX_RETRIES = 3
_CHROMA_RETRY_DELAY_SECS = 0.5


async def _run_with_retry(
    loop: asyncio.AbstractEventLoop,
    fn,
    max_retries: int = _CHROMA_MAX_RETRIES,
    delay: float = _CHROMA_RETRY_DELAY_SECS,
):
    """Führt eine sync ChromaDB-Operation mit Retry aus.

    Retry bei transienten Fehlern (Connection, Timeout) mit exponentiellem Backoff.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return await loop.run_in_executor(None, fn)
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                wait = delay * (2 ** attempt)
                logger.warning(
                    "ChromaDB-Operation fehlgeschlagen (Versuch %d/%d), "
                    "retry in %.1fs: %s",
                    attempt + 1,
                    max_retries,
                    wait,
                    exc,
                )
                await asyncio.sleep(wait)
    raise last_exc  # type: ignore[misc]


class SemanticMemory:
    """ChromaDB Semantic Memory für Ninko."""

    COLLECTION_NAME = "ninko_memory"

    def __init__(self) -> None:
        settings = get_settings()
        self._client = chromadb.HttpClient(
            host=settings.CHROMA_HOST,
            port=settings.CHROMA_PORT,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._embeddings = get_embeddings()
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "Semantic Memory initialisiert (ChromaDB %s:%s, Collection=%s)",
            settings.CHROMA_HOST,
            settings.CHROMA_PORT,
            self.COLLECTION_NAME,
        )

    async def store(
        self,
        content: str,
        metadata: dict | None = None,
        category: str = "general",
        importance: float = 0.5,
    ) -> str:
        """
        Speichert einen Eintrag im Semantic Memory.
        Gibt die generierte ID zurück.

        Args:
            content: Der zu speichernde Text
            metadata: Zusätzliche Metadaten
            category: Kategorie für Filterung
            importance: Wichtigkeit 0.0-1.0 (1.0 = kritisch)
        """
        doc_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        meta = {
            "category": category,
            "timestamp": now.isoformat(),
            "stored_at": now.isoformat(),  # Für Composite Scoring
            "importance": max(0.0, min(1.0, importance)),  # Clamp 0-1
            **(metadata or {}),
        }

        # Embedding generieren
        embedding = await self._embeddings.aembed_query(content)

        loop = asyncio.get_running_loop()
        await _run_with_retry(
            loop,
            lambda: self._collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[meta],
            ),
        )

        logger.debug(
            "Memory gespeichert: id=%s, category=%s, importance=%.2f",
            doc_id,
            category,
            meta["importance"],
        )
        return doc_id

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        category: str | None = None,
    ) -> list[dict]:
        """
        Semantische Suche im Memory.
        Gibt eine Liste von Treffern zurück.
        """
        settings = get_settings()
        k = top_k or settings.RAG_TOP_K

        # Query-Embedding
        query_embedding = await self._embeddings.aembed_query(query)

        where_filter = {"category": category} if category else None

        loop = asyncio.get_running_loop()
        results = await _run_with_retry(
            loop,
            lambda: self._collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            ),
        )

        hits: list[dict] = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                hits.append(
                    {
                        "id": results["ids"][0][i],
                        "content": doc,
                        "metadata": results["metadatas"][0][i]
                        if results["metadatas"]
                        else {},
                        "distance": results["distances"][0][i]
                        if results["distances"]
                        else None,
                    }
                )

        logger.debug("Memory-Suche: query='%s…', treffer=%d", query[:50], len(hits))
        return hits

    async def store_incident(
        self,
        module: str,
        summary: str,
        details: str,
        severity: str = "info",
    ) -> str:
        """Speichert einen Incident im Memory."""
        content = f"[{module.upper()}] {severity.upper()}: {summary}\n\n{details}"
        return await self.store(
            content=content,
            metadata={"module": module, "severity": severity, "type": "incident"},
            category="incident",
        )

    async def get_recent_incidents(
        self, query: str = "Letzte Incidents", top_k: int = 10
    ) -> list[dict]:
        """Gibt die letzten Incidents zurück."""
        return await self.search(query=query, top_k=top_k, category="incident")

    async def delete(self, doc_id: str) -> None:
        """Löscht einen Eintrag anhand seiner ID."""
        loop = asyncio.get_running_loop()
        await _run_with_retry(loop, lambda: self._collection.delete(ids=[doc_id]))
        logger.debug("Memory-Eintrag gelöscht: id=%s", doc_id)

    async def delete_by_content(
        self,
        query: str,
        category: str | None = None,
        threshold: float = 0.25,
    ) -> list[str]:
        """
        Semantische Suche + Löschen aller Einträge, deren Ähnlichkeit
        zum Query-Embedding unterhalb des Schwellenwerts liegt (d.h. sehr ähnlich).
        Gibt die Liste der gelöschten IDs zurück.
        """
        hits = await self.search(query=query, top_k=5, category=category)
        deleted: list[str] = []
        for hit in hits:
            dist = hit.get("distance")
            # Bei cosine-Distanz: 0 = identisch, 1 = komplett verschieden
            if dist is not None and dist <= threshold:
                await self.delete(hit["id"])
                deleted.append(hit["id"])
                logger.info(
                    "Memory per Content gelöscht: id=%s, dist=%.3f", hit["id"], dist
                )
        return deleted

    def get_stats(self) -> dict:
        """Statistiken der Collection."""
        count = self._collection.count()
        return {"collection": self.COLLECTION_NAME, "document_count": count}

    @staticmethod
    def _composite_score(
        distance: float,
        stored_at_iso: str,
        importance: float = 0.5,
        alpha: float = 0.5,
        beta: float = 0.3,
        gamma: float = 0.2,
        decay_lambda: float = 0.05,
    ) -> float:
        """
        Berechnet einen gewichteten Composite Score für Memory-Re-Ranking.

        Args:
            distance: ChromaDB Cosine-Distanz (0.0 = identisch, 2.0 = maximal verschieden)
            stored_at_iso: ISO-8601 Timestamp wann der Eintrag gespeichert wurde
            importance: Wichtigkeit 0.0-1.0 (1.0 = kritisch, 0.5 = normal, 0.2 = trivial)
            alpha: Gewicht für Semantic Similarity (default: 0.5)
            beta: Gewicht für Recency (default: 0.3)
            gamma: Gewicht für Importance (default: 0.2)
            decay_lambda: Zerfallsrate für Recency (Halbwertszeit ~14 Tage bei 0.05)

        Returns:
            Gewichteter Score (höher = besser)
        """
        # Semantic: 0 = identisch, 2 = verschieden → normalisiere zu 0-1
        semantic = 1.0 - (distance / 2.0)

        # Recency: Exponentieller Zerfall mit Alter
        try:
            stored = datetime.fromisoformat(stored_at_iso.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - stored).days
        except (ValueError, TypeError):
            age_days = 0
        recency = math.exp(-decay_lambda * max(age_days, 0))

        # Gewichtete Summe
        return alpha * semantic + beta * recency + gamma * importance

    async def query(
        self,
        text: str,
        top_k: int = 5,
        category: str | None = None,
    ) -> list[str]:
        """
        Semantische Suche mit Composite Scoring (Semantic + Recency + Importance).

        Args:
            text: Suchquery
            top_k: Anzahl der gewünschten Top-Ergebnisse
            category: Optionale Kategorie-Filterung

        Returns:
            Liste der Top-K Dokument-Inhalte (beste Kombination aus Ähnlichkeit, Aktualität, Wichtigkeit)
        """
        # Schritt 1: Mehr Ergebnisse von ChromaDB holen für Re-Ranking
        raw_results = await self.search(
            query=text,
            top_k=min(top_k * 4, 20),  # Max 20 für Re-Ranking
            category=category,
        )

        # Schritt 2: Composite Score für jedes Ergebnis berechnen
        scored: list[tuple[float, str]] = []
        for hit in raw_results:
            dist = hit.get("distance")
            if dist is None:
                continue
            meta = hit.get("metadata", {})
            score = self._composite_score(
                distance=dist,
                stored_at_iso=meta.get(
                    "stored_at", datetime.now(timezone.utc).isoformat()
                ),
                importance=float(meta.get("importance", 0.5)),
            )
            scored.append((score, hit.get("content", "")))

        # Schritt 3: Nach Score sortieren und Top-K zurückgeben
        scored.sort(key=lambda x: x[0], reverse=True)
        return [content for _, content in scored[:top_k]]


# Singleton
_memory: SemanticMemory | None = None
_memory_lock = threading.Lock()


def get_memory() -> SemanticMemory:
    """Gibt die globale Memory-Instanz zurück (lazy init, thread-safe)."""
    global _memory
    if _memory is None:
        with _memory_lock:
            if _memory is None:
                _memory = SemanticMemory()
    return _memory
