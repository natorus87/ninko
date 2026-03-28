"""
Qdrant Modul – LangChain Tools für die KI-Wissensbank.

Design-Prinzipien:
- Embeddings via globalen get_embeddings() aus llm_factory (einheitlich mit ChromaDB)
- ConnectionManager für Multi-Instanz-Support
- Auto-Chunking: Lange Texte werden automatisch geteilt
- Payload-Filterung: Kategorie, Tags, Quelle
- Fallback auf QDRANT_URL / QDRANT_API_KEY Env-Vars
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from langchain.tools import tool

logger = logging.getLogger("ninko.modules.qdrant")

# ── Chunking-Konstanten ────────────────────────────────────────────────────────
CHUNK_SIZE = 800       # Zeichen pro Chunk
CHUNK_OVERLAP = 150    # Überlappung zwischen Chunks
QDRANT_VECTOR_SIZE_CACHE: dict[str, int] = {}   # collection → dimension


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _chunk_text(text: str) -> list[str]:
    """
    Teilt langen Text in überlappende Chunks auf Wort-Grenzen.
    Gibt Liste von mindestens einem Chunk zurück.
    """
    if len(text) <= CHUNK_SIZE:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            space = text.rfind(" ", start, end)
            if space > start:
                end = space
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - CHUNK_OVERLAP
        if start >= len(text):
            break

    return chunks or [text]


async def _get_qdrant_client(connection_id: str = "") -> tuple[Any, str]:
    """
    Gibt (AsyncQdrantClient, default_collection) zurück.
    Nutzt ConnectionManager wenn connection_id angegeben, sonst Env-Vars.
    """
    try:
        from qdrant_client import AsyncQdrantClient
    except ImportError:
        raise RuntimeError(
            "qdrant-client ist nicht installiert. "
            "Bitte 'qdrant-client' zu requirements.txt hinzufügen und neu bauen."
        )

    from core.connections import ConnectionManager

    url: str = ""
    api_key: Optional[str] = None
    default_collection: str = ""

    if connection_id:
        conn = await ConnectionManager.get_connection("qdrant", connection_id)
    else:
        conn = await ConnectionManager.get_default_connection("qdrant")

    if conn:
        url = conn.config.get("url", "").rstrip("/")
        default_collection = conn.config.get("default_collection", "ninko_knowledge")
        # API-Key aus Vault holen
        if "api_key" in conn.vault_keys:
            from core.vault import get_vault
            vault = get_vault()
            api_key = await vault.get_secret(conn.vault_keys["api_key"])
    else:
        # Env-Var-Fallback
        url = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")
        api_key = os.getenv("QDRANT_API_KEY") or None
        default_collection = os.getenv("QDRANT_DEFAULT_COLLECTION", "ninko_knowledge")

    if not url:
        raise ValueError("Keine Qdrant-URL konfiguriert (ConnectionManager oder QDRANT_URL Env-Var).")

    client = AsyncQdrantClient(url=url, api_key=api_key, timeout=10.0)
    return client, default_collection


async def _ensure_collection(client: Any, collection: str) -> int:
    """
    Erstellt die Collection falls sie nicht existiert.
    Gibt die Vektor-Dimension zurück.
    """
    from qdrant_client.models import Distance, VectorParams

    if collection in QDRANT_VECTOR_SIZE_CACHE:
        return QDRANT_VECTOR_SIZE_CACHE[collection]

    try:
        info = await client.get_collection(collection)
        size = info.config.params.vectors.size
        QDRANT_VECTOR_SIZE_CACHE[collection] = size
        return size
    except Exception:
        pass  # Collection existiert noch nicht — erstellen

    # Dimension via Test-Embedding ermitteln
    from core.llm_factory import get_embeddings
    embeddings = get_embeddings()
    test_vec = await asyncio.get_event_loop().run_in_executor(
        None, embeddings.embed_query, "dimension probe"
    )
    size = len(test_vec)

    await client.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=size, distance=Distance.COSINE),
    )
    QDRANT_VECTOR_SIZE_CACHE[collection] = size
    logger.info("Qdrant Collection '%s' erstellt (dim=%d).", collection, size)
    return size


async def _embed(text: str) -> list[float]:
    """Generiert Embedding via globalem get_embeddings()."""
    from core.llm_factory import get_embeddings
    embeddings = get_embeddings()
    return await asyncio.get_event_loop().run_in_executor(
        None, embeddings.embed_query, text
    )


# ── LangChain Tools ────────────────────────────────────────────────────────────

@tool
async def search_knowledge(
    query: str,
    collection: str = "",
    top_k: int = 5,
    category: str = "",
    tags: str = "",
    connection_id: str = "",
) -> list[dict]:
    """
    Durchsucht die Qdrant-Wissensbank semantisch nach relevantem Fachwissen.

    Verwende dieses Tool wenn der Benutzer nach IT-Prozessen, Dokumentation,
    Runbooks, Anleitungen oder gespeichertem Fachwissen fragt.

    Parameter:
    - query: Suchanfrage in natürlicher Sprache
    - collection: Name der Collection (leer = Standard-Collection)
    - top_k: Anzahl der Ergebnisse (1–20, Standard: 5)
    - category: Optionaler Filter für eine Kategorie (z.B. "kubernetes", "netzwerk")
    - tags: Komma-getrennte Tags zum Filtern (z.B. "dns,firewall")

    Gibt eine Liste von Wissens-Einträgen mit Titel, Inhalt und Score zurück.
    """
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

        client, default_collection = await _get_qdrant_client(connection_id)
        target = collection or default_collection
        top_k = max(1, min(20, top_k))

        # Payload-Filter aufbauen
        conditions = []
        if category:
            conditions.append(FieldCondition(key="category", match=MatchValue(value=category)))
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            if tag_list:
                conditions.append(FieldCondition(key="tags", match=MatchAny(any=tag_list)))

        query_filter = Filter(must=conditions) if conditions else None

        vector = await _embed(query)
        results = await client.search(
            collection_name=target,
            query_vector=vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )

        if not results:
            return [{"info": f"Keine Treffer in Collection '{target}' für: {query}"}]

        return [
            {
                "id": str(r.id),
                "title": r.payload.get("title", ""),
                "content": r.payload.get("content", ""),
                "category": r.payload.get("category", ""),
                "tags": r.payload.get("tags", []),
                "source": r.payload.get("source", ""),
                "score": round(r.score, 4),
                "chunk_index": r.payload.get("chunk_index", 0),
                "chunk_total": r.payload.get("chunk_total", 1),
            }
            for r in results
        ]

    except Exception as e:
        logger.exception("Fehler bei search_knowledge")
        return [{"error": f"Suche fehlgeschlagen: {e}"}]


@tool
async def add_knowledge(
    content: str,
    title: str = "",
    category: str = "general",
    tags: str = "",
    source: str = "",
    collection: str = "",
    connection_id: str = "",
) -> str:
    """
    Fügt Fachwissen zur Qdrant-Wissensbank hinzu.

    Langer Text wird automatisch in überlappende Chunks aufgeteilt.
    Jeder Chunk erhält Metadaten (Kategorie, Tags, Quelle) für spätere Filterung.

    Parameter:
    - content: Der Wissens-Inhalt (Text, Dokumentation, Runbook, etc.)
    - title: Aussagekräftiger Titel
    - category: Kategorie (z.B. "kubernetes", "netzwerk", "sicherheit", "allgemein")
    - tags: Komma-getrennte Tags (z.B. "dns,troubleshooting,fritzbox")
    - source: Quellenangabe (URL, Dateiname, Autor)
    - collection: Ziel-Collection (leer = Standard-Collection)
    """
    try:
        from qdrant_client.models import PointStruct

        client, default_collection = await _get_qdrant_client(connection_id)
        target = collection or default_collection

        await _ensure_collection(client, target)

        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        chunks = _chunk_text(content)
        chunk_total = len(chunks)
        created_at = datetime.now(timezone.utc).isoformat()

        points = []
        for idx, chunk in enumerate(chunks):
            vector = await _embed(chunk)
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload={
                        "content": chunk,
                        "title": title or f"{category} – Eintrag",
                        "category": category,
                        "tags": tag_list,
                        "source": source,
                        "chunk_index": idx,
                        "chunk_total": chunk_total,
                        "created_at": created_at,
                    },
                )
            )

        await client.upsert(collection_name=target, points=points)

        msg = (
            f"{chunk_total} Chunk(s) erfolgreich in Collection '{target}' gespeichert."
            if chunk_total > 1
            else f"Eintrag in Collection '{target}' gespeichert."
        )
        logger.info("Qdrant add_knowledge: %s (title=%r)", msg, title)
        return msg

    except Exception as e:
        logger.exception("Fehler bei add_knowledge")
        return f"Fehler beim Speichern: {e}"


@tool
async def delete_knowledge_by_id(
    point_id: str,
    collection: str = "",
    connection_id: str = "",
) -> str:
    """
    Löscht einen einzelnen Wissens-Eintrag aus der Qdrant-Wissensbank anhand seiner ID.

    Parameter:
    - point_id: Die UUID des zu löschenden Eintrags (aus search_knowledge erhalten)
    - collection: Collection (leer = Standard-Collection)
    """
    try:
        from qdrant_client.models import PointIdsList

        client, default_collection = await _get_qdrant_client(connection_id)
        target = collection or default_collection

        await client.delete(
            collection_name=target,
            points_selector=PointIdsList(points=[point_id]),
        )
        logger.info("Qdrant: Punkt %s aus '%s' gelöscht.", point_id, target)
        return f"Eintrag {point_id} erfolgreich gelöscht."

    except Exception as e:
        logger.exception("Fehler bei delete_knowledge_by_id")
        return f"Fehler beim Löschen: {e}"


@tool
async def list_knowledge_collections(connection_id: str = "") -> list[dict]:
    """
    Listet alle verfügbaren Wissens-Collections in Qdrant auf.

    Gibt Name, Anzahl der Vektoren und Status jeder Collection zurück.
    Nützlich um zu sehen welche Wissensbereiche vorhanden sind.
    """
    try:
        client, _ = await _get_qdrant_client(connection_id)
        result = await client.get_collections()

        collections = []
        for c in result.collections:
            try:
                info = await client.get_collection(c.name)
                collections.append({
                    "name": c.name,
                    "vectors_count": info.vectors_count or 0,
                    "points_count": info.points_count or 0,
                    "status": info.status.value if hasattr(info.status, "value") else str(info.status),
                    "vector_size": info.config.params.vectors.size if info.config.params.vectors else 0,
                })
            except Exception:
                collections.append({"name": c.name, "status": "unbekannt"})

        return collections if collections else [{"info": "Keine Collections vorhanden."}]

    except Exception as e:
        logger.exception("Fehler bei list_knowledge_collections")
        return [{"error": f"Fehler: {e}"}]


@tool
async def get_collection_stats(
    collection: str = "",
    connection_id: str = "",
) -> dict:
    """
    Gibt detaillierte Statistiken einer Qdrant-Collection zurück.

    Parameter:
    - collection: Name der Collection (leer = Standard-Collection)

    Zeigt Anzahl Vektoren, Dimension, Status und Speicherinformationen.
    """
    try:
        client, default_collection = await _get_qdrant_client(connection_id)
        target = collection or default_collection

        info = await client.get_collection(target)
        return {
            "name": target,
            "vectors_count": info.vectors_count or 0,
            "points_count": info.points_count or 0,
            "status": info.status.value if hasattr(info.status, "value") else str(info.status),
            "vector_size": info.config.params.vectors.size if info.config.params.vectors else 0,
            "distance": (
                info.config.params.vectors.distance.value
                if info.config.params.vectors
                else "Cosine"
            ),
            "segments_count": info.segments_count or 0,
        }

    except Exception as e:
        logger.exception("Fehler bei get_collection_stats")
        return {"error": f"Fehler: {e}"}
