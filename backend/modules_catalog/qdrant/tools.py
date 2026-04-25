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
from typing import Any, Optional, List

from langchain.tools import tool
from pydantic import BaseModel, field_validator

from agents.base_agent import _t

logger = logging.getLogger("ninko.modules.qdrant")

try:
    from qdrant_client.http.exceptions import (
        ResponseHandlingException,
        UnexpectedResponse,
    )
except ImportError:  # pragma: no cover - qdrant-client is optional in local dev
    class ResponseHandlingException(Exception):
        """Fallback when qdrant-client is unavailable."""

    class UnexpectedResponse(Exception):
        """Fallback when qdrant-client is unavailable."""

# ── Constants ─────────────────────────────────────────────────────────────────
CHUNK_SIZE = 800         # characters per chunk
CHUNK_OVERLAP = 150      # overlap between chunks
MAX_BULK_ENTRIES = 500   # hard DoS limit for add_knowledge_bulk
MAX_BULK_CONTENT_BYTES = 4 * 1024 * 1024  # ~4 MB request budget
QDRANT_VECTOR_SIZE_CACHE: dict[str, int] = {}  # collection → dimension
QDRANT_RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
QDRANT_RETRY_EXCEPTIONS = (
    OSError,
    ConnectionError,
    RuntimeError,
    ResponseHandlingException,
    UnexpectedResponse,
)
QDRANT_TOOL_EXCEPTIONS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    OSError,
    ResponseHandlingException,
    UnexpectedResponse,
)


# ── Pydantic schema for bulk entries (gives LLM proper JSON schema) ────────────
class KnowledgeEntry(BaseModel):
    content: str
    title: str = ""
    category: str = "general"
    tags: str = ""
    source: str = ""

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("content must not be empty")
        return v.strip()


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


def _qdrant_status_code(exc: Exception) -> int | None:
    """Extract an HTTP-like status code from qdrant-client exceptions when present."""
    for attr in ("status_code", "status"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    for attr in ("status_code", "status"):
        value = getattr(response, attr, None)
        if isinstance(value, int):
            return value
    return None


def _is_qdrant_not_found(exc: Exception) -> bool:
    """Return True only for Qdrant 404-style errors."""
    return isinstance(exc, UnexpectedResponse) and _qdrant_status_code(exc) == 404


def _is_retryable_qdrant_error(exc: Exception) -> bool:
    """Retry transient Qdrant client failures, but not auth/validation errors."""
    if isinstance(exc, ResponseHandlingException):
        return True
    if isinstance(exc, UnexpectedResponse):
        return (_qdrant_status_code(exc) or 0) in QDRANT_RETRYABLE_STATUSES
    return isinstance(exc, (OSError, ConnectionError, RuntimeError))


async def _with_retry(coro_factory, max_retries: int = 3, base_delay: float = 1.0):
    """
    Execute an async coroutine factory with exponential backoff retry.
    coro_factory must be a callable returning a new coroutine on each call.
    """
    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except QDRANT_RETRY_EXCEPTIONS as e:
            if not _is_retryable_qdrant_error(e):
                raise
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2**attempt)
            logger.warning(
                "Qdrant operation failed (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                max_retries,
                delay,
                e,
            )
            await asyncio.sleep(delay)


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
    except UnexpectedResponse as exc:
        if not _is_qdrant_not_found(exc):
            raise
        logger.debug("Collection '%s' not found, will create it.", collection)

    # Determine dimension via test embedding
    from core.llm_factory import get_embeddings

    embeddings = get_embeddings()
    test_vec = await asyncio.get_running_loop().run_in_executor(
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
    return await asyncio.get_running_loop().run_in_executor(
        None, embeddings.embed_query, text
    )


# ── LangChain Tools ────────────────────────────────────────────────────────────


@tool
async def search_knowledge(
    query: str,
    collection: str = "",
    top_k: int = 5,
    score_threshold: float = 0.0,
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
    - score_threshold: minimum relevance score 0.0–1.0 (default: 0.0 = no filter).
      Use 0.5 for moderate relevance, 0.7 for high relevance only.
    - category: optional category filter (e.g. "kubernetes", "network")
    - tags: comma-separated tags for filtering (e.g. "dns,firewall")

    Returns a list of knowledge entries with title, content, and score.
    """
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

        client, default_collection = await _get_qdrant_client(connection_id)
        target = collection or default_collection
        top_k = max(1, min(20, top_k))
        score_threshold = max(0.0, min(1.0, score_threshold))

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
        results = await _with_retry(
            lambda: client.search(
                collection_name=target,
                query_vector=vector,
                limit=top_k,
                score_threshold=score_threshold if score_threshold > 0.0 else None,
                query_filter=query_filter,
                with_payload=True,
            )
        )

        if not results:
            hint = (
                _t(
                    de=f" (score_threshold={score_threshold:.2f} — versuche einen niedrigeren Wert)",
                    en=f" (score_threshold={score_threshold:.2f} — try a lower value)",
                    fr=f" (score_threshold={score_threshold:.2f} — essayez une valeur plus basse)",
                    es=f" (score_threshold={score_threshold:.2f} — prueba un valor más bajo)",
                    it=f" (score_threshold={score_threshold:.2f} — prova un valore più basso)",
                    nl=f" (score_threshold={score_threshold:.2f} — probeer een lagere waarde)",
                    pl=f" (score_threshold={score_threshold:.2f} — spróbuj niższej wartości)",
                    pt=f" (score_threshold={score_threshold:.2f} — tente um valor menor)",
                    ja=f" (score_threshold={score_threshold:.2f} — より低い値を試してください)",
                    zh=f" (score_threshold={score_threshold:.2f} — 尝试较低的值)",
                )
                if score_threshold > 0.0
                else ""
            )
            return [
                {
                    "info": _t(
                        de=f"Keine Treffer in Collection '{target}' für: {query}{hint}",
                        en=f"No results in collection '{target}' for: {query}{hint}",
                        fr=f"Aucun résultat dans la collection '{target}' pour: {query}{hint}",
                        es=f"Sin resultados en la colección '{target}' para: {query}{hint}",
                        it=f"Nessun risultato nella raccolta '{target}' per: {query}{hint}",
                        nl=f"Geen resultaten in collectie '{target}' voor: {query}{hint}",
                        pl=f"Brak wyników w kolekcji '{target}' dla: {query}{hint}",
                        pt=f"Nenhum resultado na coleção '{target}' para: {query}{hint}",
                        ja=f"コレクション '{target}' に結果がありません: {query}{hint}",
                        zh=f"集合 '{target}' 中没有结果: {query}{hint}",
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

    except QDRANT_TOOL_EXCEPTIONS as e:
        logger.exception("Error in search_knowledge: %s", e)
        return [
            {
                "error": _t(
                    de="Suche fehlgeschlagen. Details im Server-Log.",
                    en="Search failed. See server log for details.",
                    fr="Échec de la recherche. Consultez le journal du serveur.",
                    es="Búsqueda fallida. Consulte el registro del servidor.",
                    it="Ricerca fallita. Vedere il registro del server.",
                    nl="Zoeken mislukt. Zie serverlog voor details.",
                    pl="Wyszukiwanie nie powiodło się. Szczegóły w logu serwera.",
                    pt="Pesquisa falhou. Veja o log do servidor.",
                    ja="検索に失敗しました。サーバーログを確認してください。",
                    zh="搜索失败。请查看服务器日志。",
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

        await _with_retry(lambda: client.upsert(collection_name=target, points=points))

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

    except QDRANT_TOOL_EXCEPTIONS as e:
        logger.exception("Error in add_knowledge: %s", e)
        return _t(
            de="Fehler beim Speichern. Details im Server-Log.",
            en="Storage error. See server log for details.",
            fr="Erreur de stockage. Consultez le journal du serveur.",
            es="Error de almacenamiento. Consulte el registro del servidor.",
            it="Errore di archiviazione. Vedere il registro del server.",
            nl="Opslagfout. Zie serverlog voor details.",
            pl="Błąd przechowywania. Szczegóły w logu serwera.",
            pt="Erro de armazenamento. Veja o log do servidor.",
            ja="保存エラー。サーバーログを確認してください。",
            zh="存储错误。请查看服务器日志。",
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

    except QDRANT_TOOL_EXCEPTIONS as e:
        logger.exception("Error in delete_knowledge_by_id: %s", e)
        return _t(
            de="Fehler beim Löschen. Details im Server-Log.",
            en="Delete error. See server log for details.",
            fr="Erreur de suppression. Consultez le journal du serveur.",
            es="Error de eliminación. Consulte el registro del servidor.",
            it="Errore di eliminazione. Vedere il registro del server.",
            nl="Verwijderingsfout. Zie serverlog voor details.",
            pl="Błąd usuwania. Szczegóły w logu serwera.",
            pt="Erro ao excluir. Veja o log do servidor.",
            ja="削除エラー。サーバーログを確認してください。",
            zh="删除错误。请查看服务器日志。",
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
            except QDRANT_TOOL_EXCEPTIONS:
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

    except QDRANT_TOOL_EXCEPTIONS as e:
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

    except QDRANT_TOOL_EXCEPTIONS as e:
        logger.exception("Error in get_collection_stats")
        return {"error": f"Error: {e}"}


@tool
async def add_knowledge_bulk(
    entries: List[KnowledgeEntry],
    collection: str = "",
    connection_id: str = "",
) -> str:
    """
    Add multiple knowledge entries to the Qdrant knowledge bank in a single batch.

    More efficient than calling add_knowledge repeatedly for many documents.
    Each entry is auto-chunked if the content is too long.
    Maximum 500 entries per call.

    Parameters:
    - entries: list of KnowledgeEntry objects, each with:
        - content (required): the text to store
        - title (optional): descriptive title
        - category (optional, default "general"): e.g. "kubernetes", "network"
        - tags (optional): comma-separated tags
        - source (optional): URL, filename, or author reference
    - collection: target collection (empty = default collection)
    """
    if not entries:
        return _t(
            de="Keine Einträge übergeben.",
            en="No entries provided.",
            fr="Aucune entrée fournie.",
            es="No se proporcionaron entradas.",
            it="Nessuna voce fornita.",
            nl="Geen items opgegeven.",
            pl="Nie podano żadnych wpisów.",
            pt="Nenhuma entrada fornecida.",
            ja="エントリーが指定されていません。",
            zh="未提供任何条目。",
        )

    if len(entries) > MAX_BULK_ENTRIES:
        return _t(
            de=f"Zu viele Einträge: {len(entries)} > {MAX_BULK_ENTRIES} (Limit). Bitte aufteilen.",
            en=f"Too many entries: {len(entries)} > {MAX_BULK_ENTRIES} (limit). Please split the batch.",
            fr=f"Trop d'entrées: {len(entries)} > {MAX_BULK_ENTRIES} (limite). Veuillez diviser le lot.",
            es=f"Demasiadas entradas: {len(entries)} > {MAX_BULK_ENTRIES} (límite). Divida el lote.",
            it=f"Troppe voci: {len(entries)} > {MAX_BULK_ENTRIES} (limite). Si prega di dividere il batch.",
            nl=f"Te veel items: {len(entries)} > {MAX_BULK_ENTRIES} (limiet). Splits de batch.",
            pl=f"Za dużo wpisów: {len(entries)} > {MAX_BULK_ENTRIES} (limit). Podziel partię.",
            pt=f"Entradas demais: {len(entries)} > {MAX_BULK_ENTRIES} (limite). Divida o lote.",
            ja=f"エントリー数超過: {len(entries)} > {MAX_BULK_ENTRIES}（上限）。バッチを分割してください。",
            zh=f"条目过多: {len(entries)} > {MAX_BULK_ENTRIES}（限制）。请分批处理。",
        )

    total_content_bytes = sum(len(entry.content.encode("utf-8")) for entry in entries)
    if total_content_bytes > MAX_BULK_CONTENT_BYTES:
        total_mb = total_content_bytes / (1024 * 1024)
        limit_mb = MAX_BULK_CONTENT_BYTES / (1024 * 1024)
        return _t(
            de=f"Batch zu groß: {total_mb:.2f} MB > {limit_mb:.0f} MB Limit. Bitte Inhalte aufteilen.",
            en=f"Batch too large: {total_mb:.2f} MB > {limit_mb:.0f} MB limit. Please split the content.",
            fr=f"Lot trop volumineux: {total_mb:.2f} MB > {limit_mb:.0f} MB. Veuillez le diviser.",
            es=f"Lote demasiado grande: {total_mb:.2f} MB > {limit_mb:.0f} MB. Divida el contenido.",
            it=f"Batch troppo grande: {total_mb:.2f} MB > {limit_mb:.0f} MB. Suddividere il contenuto.",
            nl=f"Batch te groot: {total_mb:.2f} MB > {limit_mb:.0f} MB limiet. Splits de inhoud.",
            pl=f"Partia jest zbyt duża: {total_mb:.2f} MB > {limit_mb:.0f} MB. Podziel zawartość.",
            pt=f"Lote grande demais: {total_mb:.2f} MB > {limit_mb:.0f} MB. Divida o conteúdo.",
            ja=f"バッチが大きすぎます: {total_mb:.2f} MB > {limit_mb:.0f} MB。内容を分割してください。",
            zh=f"批次过大: {total_mb:.2f} MB > {limit_mb:.0f} MB。请拆分内容。",
        )

    try:
        from qdrant_client.models import PointStruct

        client, default_collection = await _get_qdrant_client(connection_id)
        target = collection or default_collection

        await _ensure_collection(client, target)

        created_at = datetime.now(timezone.utc).isoformat()
        all_points: list = []
        total_chunks = 0

        for entry in entries:
            content = entry.content
            title = entry.title
            category = entry.category
            tags_raw = entry.tags
            source = entry.source
            tag_list = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
            chunks = _chunk_text(content)
            chunk_total = len(chunks)
            total_chunks += chunk_total

            for idx, chunk in enumerate(chunks):
                vector = await _embed(chunk)
                all_points.append(
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

        if not all_points:
            return _t(
                de="Alle Einträge waren leer — nichts gespeichert.",
                en="All entries were empty — nothing stored.",
                fr="Toutes les entrées étaient vides — rien n'a été enregistré.",
                es="Todas las entradas estaban vacías — nada almacenado.",
                it="Tutte le voci erano vuote — niente salvato.",
                nl="Alle items waren leeg — niets opgeslagen.",
                pl="Wszystkie wpisy były puste — nic nie zapisano.",
                pt="Todas as entradas estavam vazias — nada armazenado.",
                ja="すべてのエントリーが空でした — 何も保存されませんでした。",
                zh="所有条目均为空 — 未存储任何内容。",
            )

        # Upload in batches of 100 to avoid overloading the server
        batch_size = 100
        for i in range(0, len(all_points), batch_size):
            batch = all_points[i : i + batch_size]
            await _with_retry(lambda b=batch: client.upsert(collection_name=target, points=b))

        msg = _t(
            de=f"{len(entries)} Einträge ({total_chunks} Chunks) in Collection '{target}' gespeichert.",
            en=f"{len(entries)} entries ({total_chunks} chunks) stored in collection '{target}'.",
            fr=f"{len(entries)} entrées ({total_chunks} chunks) enregistrées dans la collection '{target}'.",
            es=f"{len(entries)} entradas ({total_chunks} chunks) almacenadas en la colección '{target}'.",
            it=f"{len(entries)} voci ({total_chunks} chunks) salvate nella raccolta '{target}'.",
            nl=f"{len(entries)} items ({total_chunks} chunks) opgeslagen in collectie '{target}'.",
            pl=f"{len(entries)} wpisów ({total_chunks} chunków) zapisanych w kolekcji '{target}'.",
            pt=f"{len(entries)} entradas ({total_chunks} chunks) armazenadas na coleção '{target}'.",
            ja=f"{len(entries)} 件のエントリー（{total_chunks} チャンク）をコレクション '{target}' に保存しました。",
            zh=f"已在集合 '{target}' 中存储 {len(entries)} 条条目（{total_chunks} 个块）。",
        )
        logger.info("Qdrant add_knowledge_bulk: %s", msg)
        return msg

    except QDRANT_TOOL_EXCEPTIONS as e:
        logger.exception("Error in add_knowledge_bulk: %s", e)
        return _t(
            de="Fehler beim Bulk-Speichern. Details im Server-Log.",
            en="Bulk storage error. See server log for details.",
            fr="Erreur de stockage en lot. Consultez le journal du serveur.",
            es="Error de almacenamiento masivo. Consulte el registro del servidor.",
            it="Errore di archiviazione in blocco. Vedere il registro del server.",
            nl="Bulk-opslagfout. Zie serverlog voor details.",
            pl="Błąd przechowywania zbiorczego. Szczegóły w logu serwera.",
            pt="Erro de armazenamento em massa. Veja o log do servidor.",
            ja="一括保存エラー。サーバーログを確認してください。",
            zh="批量存储错误。请查看服务器日志。",
        )


@tool
async def delete_by_filter(
    category: str = "",
    tags: str = "",
    collection: str = "",
    connection_id: str = "",
    confirm: bool = False,
) -> str:
    """
    Delete all knowledge entries matching a category and/or tag filter.

    Use this to clean up entire topic areas without knowing individual point IDs.
    At least one of category or tags must be provided.

    Parameters:
    - category: delete all entries with this category (e.g. "kubernetes")
    - tags: comma-separated — delete entries matching ANY of these tags
    - collection: target collection (empty = default collection)

    Warning: this operation is irreversible and requires confirm=True.
    """
    if not category and not tags:
        return _t(
            de="Mindestens category oder tags muss angegeben werden.",
            en="At least category or tags must be provided.",
            fr="Au moins category ou tags doit être fourni.",
            es="Se debe proporcionar al menos category o tags.",
            it="Almeno category o tags deve essere fornito.",
            nl="Minimaal category of tags moet worden opgegeven.",
            pl="Należy podać przynajmniej category lub tags.",
            pt="Pelo menos category ou tags deve ser fornecido.",
            ja="category または tags のいずれかを指定してください。",
            zh="必须提供至少 category 或 tags。",
        )

    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny, FilterSelector

        client, default_collection = await _get_qdrant_client(connection_id)
        target = collection or default_collection

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

        delete_filter = Filter(must=conditions)

        filter_desc = ", ".join(filter(None, [
            f"category='{category}'" if category else "",
            f"tags={tags}" if tags else "",
        ]))
        count_result = await _with_retry(
            lambda: client.count(
                collection_name=target,
                count_filter=delete_filter,
                exact=True,
            )
        )
        match_count = int(getattr(count_result, "count", 0) or 0)

        if match_count <= 0:
            result = _t(
                de=f"Keine Einträge mit {filter_desc} in Collection '{target}' gefunden.",
                en=f"No entries with {filter_desc} found in collection '{target}'.",
                fr=f"Aucune entrée avec {filter_desc} trouvée dans la collection '{target}'.",
                es=f"No se encontraron entradas con {filter_desc} en la colección '{target}'.",
                it=f"Nessuna voce con {filter_desc} trovata nella raccolta '{target}'.",
                nl=f"Geen items met {filter_desc} gevonden in collectie '{target}'.",
                pl=f"Nie znaleziono wpisów z {filter_desc} w kolekcji '{target}'.",
                pt=f"Nenhuma entrada com {filter_desc} encontrada na coleção '{target}'.",
                ja=f"コレクション '{target}' に {filter_desc} のエントリーは見つかりませんでした。",
                zh=f"集合 '{target}' 中未找到 {filter_desc} 的条目。",
            )
            logger.info("Qdrant delete_by_filter preview: %s", result)
            return result

        if not confirm:
            preview = _t(
                de=f"Vorschau: {match_count} Einträge mit {filter_desc} in Collection '{target}' würden gelöscht. Dieser Vorgang ist irreversibel. Nur nach ausdrücklicher Benutzerbestätigung mit confirm=True ausführen.",
                en=f"Preview: {match_count} entries with {filter_desc} in collection '{target}' would be deleted. This operation is irreversible. Only execute it after explicit user confirmation with confirm=True.",
                fr=f"Aperçu: {match_count} entrées avec {filter_desc} dans la collection '{target}' seraient supprimées. Cette opération est irréversible. N'exécutez qu'après confirmation explicite de l'utilisateur avec confirm=True.",
                es=f"Vista previa: se eliminarían {match_count} entradas con {filter_desc} de la colección '{target}'. Esta operación es irreversible. Ejecútela solo tras confirmación explícita del usuario con confirm=True.",
                it=f"Anteprima: verrebbero eliminate {match_count} voci con {filter_desc} dalla raccolta '{target}'. Questa operazione è irreversibile. Eseguirla solo dopo conferma esplicita dell'utente con confirm=True.",
                nl=f"Voorbeeld: {match_count} items met {filter_desc} in collectie '{target}' zouden worden verwijderd. Deze actie is onomkeerbaar. Alleen uitvoeren na expliciete gebruikersbevestiging met confirm=True.",
                pl=f"Podgląd: {match_count} wpisów z {filter_desc} w kolekcji '{target}' zostałoby usuniętych. Ta operacja jest nieodwracalna. Wykonuj ją tylko po wyraźnym potwierdzeniu użytkownika z confirm=True.",
                pt=f"Prévia: {match_count} entradas com {filter_desc} na coleção '{target}' seriam excluídas. Esta operação é irreversível. Execute apenas após confirmação explícita do usuário com confirm=True.",
                ja=f"プレビュー: コレクション '{target}' の {filter_desc} に一致する {match_count} 件が削除対象です。この操作は元に戻せません。明示的なユーザー確認後に confirm=True でのみ実行してください。",
                zh=f"预览：集合 '{target}' 中符合 {filter_desc} 的 {match_count} 条记录将被删除。此操作不可逆。只有在用户明确确认后，才可使用 confirm=True 执行。",
            )
            logger.warning("Qdrant delete_by_filter blocked pending confirmation: %s", preview)
            return preview

        await _with_retry(
            lambda: client.delete(
                collection_name=target,
                points_selector=FilterSelector(filter=delete_filter),
            )
        )

        result = _t(
            de=f"{match_count} Einträge mit {filter_desc} aus Collection '{target}' gelöscht.",
            en=f"Deleted {match_count} entries with {filter_desc} from collection '{target}'.",
            fr=f"{match_count} entrées avec {filter_desc} supprimées de la collection '{target}'.",
            es=f"Se eliminaron {match_count} entradas con {filter_desc} de la colección '{target}'.",
            it=f"Eliminate {match_count} voci con {filter_desc} dalla raccolta '{target}'.",
            nl=f"{match_count} items met {filter_desc} verwijderd uit collectie '{target}'.",
            pl=f"Usunięto {match_count} wpisów z {filter_desc} z kolekcji '{target}'.",
            pt=f"{match_count} entradas com {filter_desc} excluídas da coleção '{target}'.",
            ja=f"コレクション '{target}' から {filter_desc} に一致する {match_count} 件を削除しました。",
            zh=f"已从集合 '{target}' 中删除 {match_count} 条符合 {filter_desc} 的记录。",
        )
        logger.info("Qdrant delete_by_filter: %s", result)
        return result

    except QDRANT_TOOL_EXCEPTIONS as e:
        logger.exception("Error in delete_by_filter: %s", e)
        return _t(
            de="Fehler beim Filter-Löschen. Details im Server-Log.",
            en="Filter delete error. See server log for details.",
            fr="Erreur de suppression par filtre. Consultez le journal du serveur.",
            es="Error al eliminar por filtro. Consulte el registro del servidor.",
            it="Errore di eliminazione per filtro. Vedere il registro del server.",
            nl="Filterwissingsfout. Zie serverlog voor details.",
            pl="Błąd usuwania według filtra. Szczegóły w logu serwera.",
            pt="Erro ao excluir por filtro. Veja o log do servidor.",
            ja="フィルター削除エラー。サーバーログを確認してください。",
            zh="按过滤器删除错误。请查看服务器日志。",
        )
