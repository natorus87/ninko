"""
Qdrant Module — LangChain Tools for the AI Knowledge Bank.

Design principles:
- Embeddings via global get_embeddings() from llm_factory (uniform with ChromaDB)
- ConnectionManager for multi-instance support
- Auto-chunking: long texts are split automatically
- Payload filtering: category, tags, source
- Fallback to QDRANT_URL / QDRANT_API_KEY env vars
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from langchain.tools import tool

from agents.base_agent import _t

logger = logging.getLogger("ninko.modules.qdrant")

# ── Chunking constants ─────────────────────────────────────────────────────────
CHUNK_SIZE = 800  # characters per chunk
CHUNK_OVERLAP = 150  # overlap between chunks
QDRANT_VECTOR_SIZE_CACHE: dict[str, int] = {}  # collection → dimension


# ── Helper functions ───────────────────────────────────────────────────────────


def _chunk_text(text: str) -> list[str]:
    """
    Split long text into overlapping chunks at word boundaries.
    Returns a list of at least one chunk.
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
    Return (AsyncQdrantClient, default_collection).
    Uses ConnectionManager when connection_id is given, otherwise env vars.
    """
    try:
        from qdrant_client import AsyncQdrantClient
    except ImportError:
        raise RuntimeError(
            "qdrant-client is not installed. "
            "Please add 'qdrant-client' to requirements.txt and rebuild."
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
        # Fetch API key from Vault
        if "api_key" in conn.vault_keys:
            from core.vault import get_vault

            vault = get_vault()
            api_key = await vault.get_secret(conn.vault_keys["api_key"])
    else:
        # Env var fallback
        url = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")
        api_key = os.getenv("QDRANT_API_KEY") or None
        default_collection = os.getenv("QDRANT_DEFAULT_COLLECTION", "ninko_knowledge")

    if not url:
        raise ValueError(
            _t(
                de="Keine Qdrant-URL konfiguriert (ConnectionManager oder QDRANT_URL Env-Var).",
                en="No Qdrant URL configured (ConnectionManager or QDRANT_URL env var).",
                fr="Aucune URL Qdrant configurée (ConnectionManager ou variable d'environnement QDRANT_URL).",
                es="No hay URL de Qdrant configurada (ConnectionManager o variable de entorno QDRANT_URL).",
                it="Nessun URL Qdrant configurato (ConnectionManager o variabile di ambiente QDRANT_URL).",
                nl="Geen Qdrant-URL geconfigureerd (ConnectionManager of QDRANT_URL omgevingsvariabele).",
                pl="Nie skonfigurowano adresu URL Qdrant (ConnectionManager lub zmienna środowiskowa QDRANT_URL).",
                pt="Nenhuma URL Qdrant configurada (ConnectionManager ou variável de ambiente QDRANT_URL).",
                ja="Qdrant URLが設定されていません（ConnectionManagerまたはQDRANT_URL環境変数）。",
                zh="未配置Qdrant URL（ConnectionManager或QDRANT_URL环境变量）。",
            )
        )

    client = AsyncQdrantClient(url=url, api_key=api_key, timeout=10.0)
    return client, default_collection


async def _ensure_collection(client: Any, collection: str) -> int:
    """
    Create the collection if it does not exist.
    Returns the vector dimension.
    """
    from qdrant_client.models import Distance, VectorParams

    if collection in QDRANT_VECTOR_SIZE_CACHE:
        return QDRANT_VECTOR_SIZE_CACHE[collection]

    try:
        info = await client.get_collection(collection)
        size = info.config.params.vectors.size
        QDRANT_VECTOR_SIZE_CACHE[collection] = size
        return size
    except (RuntimeError, ValueError, TypeError, KeyError, OSError):
        pass  # Collection does not exist yet — create it

    # Determine dimension via test embedding
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
    logger.info("Qdrant collection '%s' created (dim=%d).", collection, size)
    return size


async def _embed(text: str) -> list[float]:
    """Generate embedding via global get_embeddings()."""
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
    Search the Qdrant knowledge bank semantically for relevant expertise.

    Use this tool when the user asks about IT processes, documentation,
    runbooks, guides, or stored expertise.

    Parameters:
    - query: natural language search query
    - collection: collection name (empty = default collection)
    - top_k: number of results (1–20, default: 5)
    - category: optional category filter (e.g. "kubernetes", "network")
    - tags: comma-separated tags for filtering (e.g. "dns,firewall")

    Returns a list of knowledge entries with title, content, and score.
    """
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

        client, default_collection = await _get_qdrant_client(connection_id)
        target = collection or default_collection
        top_k = max(1, min(20, top_k))

        # Build payload filter
        conditions = []
        if category:
            conditions.append(
                FieldCondition(key="category", match=MatchValue(value=category))
            )
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            if tag_list:
                conditions.append(
                    FieldCondition(key="tags", match=MatchAny(any=tag_list))
                )

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
            return [
                {
                    "info": _t(
                        de=f"Keine Treffer in Collection '{target}' für: {query}",
                        en=f"No results in collection '{target}' for: {query}",
                        fr=f"Aucun résultat dans la collection '{target}' pour: {query}",
                        es=f"Sin resultados en la colección '{target}' para: {query}",
                        it=f"Nessun risultato nella raccolta '{target}' per: {query}",
                        nl=f"Geen resultaten in collectie '{target}' voor: {query}",
                        pl=f"Brak wyników w kolekcji '{target}' dla: {query}",
                        pt=f"Nenhum resultado na coleção '{target}' para: {query}",
                        ja=f"コレクション '{target}' に結果がありません: {query}",
                        zh=f"集合 '{target}' 中没有结果: {query}",
                    )
                }
            ]

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

    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.exception("Error in search_knowledge")
        return [
            {
                "error": _t(
                    de=f"Suche fehlgeschlagen: {e}",
                    en=f"Search failed: {e}",
                    fr=f"Échec de la recherche: {e}",
                    es=f"Búsqueda fallida: {e}",
                    it=f"Ricerca fallita: {e}",
                    nl=f"Zoeken mislukt: {e}",
                    pl=f"Wyszukiwanie nie powiodło się: {e}",
                    pt=f"Pesquisa falhou: {e}",
                    ja=f"検索に失敗しました: {e}",
                    zh=f"搜索失败: {e}",
                )
            }
        ]


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
    Add expertise to the Qdrant knowledge bank.

    Long text is automatically split into overlapping chunks.
    Each chunk receives metadata (category, tags, source) for later filtering.

    Parameters:
    - content: the knowledge content (text, documentation, runbook, etc.)
    - title: descriptive title
    - category: category (e.g. "kubernetes", "network", "security", "general")
    - tags: comma-separated tags (e.g. "dns,troubleshooting,fritzbox")
    - source: source reference (URL, filename, author)
    - collection: target collection (empty = default collection)
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
                        "title": title or f"{category} — entry",
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
            _t(
                de=f"{chunk_total} Chunk(s) erfolgreich in Collection '{target}' gespeichert.",
                en=f"{chunk_total} chunk(s) stored successfully in collection '{target}'.",
                fr=f"{chunk_total} chunk(s) enregistré(s) avec succès dans la collection '{target}'.",
                es=f"{chunk_total} chunk(s) almacenado(s) con éxito en la colección '{target}'.",
                it=f"{chunk_total} chunk(s) salvato(i) con successo nella raccolta '{target}'.",
                nl=f"{chunk_total} chunk(s) succesvol opgeslagen in collectie '{target}'.",
                pl=f"{chunk_total} chunk(ów) pomyślnie zapisanych w kolekcji '{target}'.",
                pt=f"{chunk_total} chunk(s) armazenado(s) com sucesso na coleção '{target}'.",
                ja=f"{chunk_total} 件のチャンクをコレクション '{target}' に保存しました。",
                zh=f"已成功在集合 '{target}' 中存储 {chunk_total} 个块。",
            )
            if chunk_total > 1
            else _t(
                de=f"Eintrag in Collection '{target}' gespeichert.",
                en=f"Entry stored in collection '{target}'.",
                fr=f"Entrée enregistrée dans la collection '{target}'.",
                es=f"Entrada almacenada en la colección '{target}'.",
                it=f"Voce salvata nella raccolta '{target}'.",
                nl=f"Invoer opgeslagen in collectie '{target}'.",
                pl=f"Wpis zapisany w kolekcji '{target}'.",
                pt=f"Entrada armazenada na coleção '{target}'.",
                ja=f"コレクション '{target}' にエントリーを保存しました。",
                zh=f"已将在集合 '{target}' 中存储条目。",
            )
        )
        logger.info("Qdrant add_knowledge: %s (title=%r)", msg, title)
        return msg

    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.exception("Error in add_knowledge")
        return _t(
            de=f"Fehler beim Speichern: {e}",
            en=f"Storage error: {e}",
            fr=f"Erreur de stockage: {e}",
            es=f"Error de almacenamiento: {e}",
            it=f"Errore di archiviazione: {e}",
            nl=f"Opslagfout: {e}",
            pl=f"Błąd przechowywania: {e}",
            pt=f"Erro de armazenamento: {e}",
            ja=f"保存エラー: {e}",
            zh=f"存储错误: {e}",
        )


@tool
async def delete_knowledge_by_id(
    point_id: str,
    collection: str = "",
    connection_id: str = "",
) -> str:
    """
    Delete a single knowledge entry from the Qdrant knowledge bank by ID.

    Parameters:
    - point_id: UUID of the entry to delete (obtained from search_knowledge)
    - collection: collection (empty = default collection)
    """
    try:
        from qdrant_client.models import PointIdsList

        client, default_collection = await _get_qdrant_client(connection_id)
        target = collection or default_collection

        await client.delete(
            collection_name=target,
            points_selector=PointIdsList(points=[point_id]),
        )
        logger.info("Qdrant: deleted point %s from '%s'.", point_id, target)
        return _t(
            de=f"Eintrag {point_id} erfolgreich gelöscht.",
            en=f"Entry {point_id} deleted successfully.",
            fr=f"Entrée {point_id} supprimée avec succès.",
            es=f"Entrada {point_id} eliminada con éxito.",
            it=f"Voce {point_id} eliminata con successo.",
            nl=f"Invoer {point_id} succesvol verwijderd.",
            pl=f"Wpis {point_id} pomyślnie usunięty.",
            pt=f"Entrada {point_id} excluída com sucesso.",
            ja=f"エントリー {point_id} を削除しました。",
            zh=f"已成功删除条目 {point_id}。",
        )

    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.exception("Error in delete_knowledge_by_id")
        return _t(
            de=f"Fehler beim Löschen: {e}",
            en=f"Delete error: {e}",
            fr=f"Erreur de suppression: {e}",
            es=f"Error de eliminación: {e}",
            it=f"Errore di eliminazione: {e}",
            nl=f"Verwijderingsfout: {e}",
            pl=f"Błąd usuwania: {e}",
            pt=f"Erro ao excluir: {e}",
            ja=f"削除エラー: {e}",
            zh=f"删除错误: {e}",
        )


@tool
async def list_knowledge_collections(connection_id: str = "") -> list[dict]:
    """
    List all available knowledge collections in Qdrant.

    Returns name, vector count, and status of each collection.
    Useful for seeing which knowledge areas exist.
    """
    try:
        client, _ = await _get_qdrant_client(connection_id)
        result = await client.get_collections()

        collections = []
        for c in result.collections:
            try:
                info = await client.get_collection(c.name)
                collections.append(
                    {
                        "name": c.name,
                        "vectors_count": info.vectors_count or 0,
                        "points_count": info.points_count or 0,
                        "status": info.status.value
                        if hasattr(info.status, "value")
                        else str(info.status),
                        "vector_size": info.config.params.vectors.size
                        if info.config.params.vectors
                        else 0,
                    }
                )
            except (RuntimeError, ValueError, TypeError, KeyError, OSError):
                collections.append({"name": c.name, "status": "unknown"})

        return (
            collections
            if collections
            else [
                {
                    "info": _t(
                        de="Keine Collections vorhanden.",
                        en="No collections available.",
                        fr="Aucune collection disponible.",
                        es="No hay colecciones disponibles.",
                        it="Nessuna raccolta disponibile.",
                        nl="Geen collecties beschikbaar.",
                        pl="Brak dostępnych kolekcji.",
                        pt="Nenhuma coleção disponível.",
                        ja="コレクションがありません。",
                        zh="没有可用的集合。",
                    )
                }
            ]
        )

    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.exception("Error in list_knowledge_collections")
        return [{"error": f"Error: {e}"}]


@tool
async def get_collection_stats(
    collection: str = "",
    connection_id: str = "",
) -> dict:
    """
    Return detailed statistics for a Qdrant collection.

    Parameters:
    - collection: collection name (empty = default collection)

    Shows vector count, dimension, status, and storage information.
    """
    try:
        client, default_collection = await _get_qdrant_client(connection_id)
        target = collection or default_collection

        info = await client.get_collection(target)
        return {
            "name": target,
            "vectors_count": info.vectors_count or 0,
            "points_count": info.points_count or 0,
            "status": info.status.value
            if hasattr(info.status, "value")
            else str(info.status),
            "vector_size": info.config.params.vectors.size
            if info.config.params.vectors
            else 0,
            "distance": (
                info.config.params.vectors.distance.value
                if info.config.params.vectors
                else "Cosine"
            ),
            "segments_count": info.segments_count or 0,
        }

    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.exception("Error in get_collection_stats")
        return {"error": f"Error: {e}"}
