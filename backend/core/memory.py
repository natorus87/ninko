"""
Kumio Semantic Memory – ChromaDB-basiert.
Speichert Incidents, Runbooks und Chat-Kontext als Embeddings.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

import chromadb
from chromadb.config import Settings as ChromaSettings

from core.config import get_settings
from core.llm_factory import get_embeddings

logger = logging.getLogger("kumio.memory")


class SemanticMemory:
    """ChromaDB Semantic Memory für Kumio."""

    COLLECTION_NAME = "kumio_memory"

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
    ) -> str:
        """
        Speichert einen Eintrag im Semantic Memory.
        Gibt die generierte ID zurück.
        """
        doc_id = str(uuid.uuid4())
        meta = {
            "category": category,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
        }

        # Embedding generieren
        embedding = await self._embeddings.aembed_query(content)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: self._collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[meta],
            ),
        )

        logger.debug("Memory gespeichert: id=%s, category=%s", doc_id, category)
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
        results = await loop.run_in_executor(
            None,
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
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "distance": results["distances"][0][i] if results["distances"] else None,
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
        await loop.run_in_executor(None, lambda: self._collection.delete(ids=[doc_id]))
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
                logger.info("Memory per Content gelöscht: id=%s, dist=%.3f", hit["id"], dist)
        return deleted

    def get_stats(self) -> dict:
        """Statistiken der Collection."""
        count = self._collection.count()
        return {"collection": self.COLLECTION_NAME, "document_count": count}


# Singleton
_memory: SemanticMemory | None = None


def get_memory() -> SemanticMemory:
    """Gibt die globale Memory-Instanz zurück (lazy init)."""
    global _memory
    if _memory is None:
        _memory = SemanticMemory()
    return _memory
