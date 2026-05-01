"""
Licium module — LangGraph @tool-Funktionen.

Implementiert das Karpathy LLM-Wiki-Pattern:
  - Ingest: Quelle analysieren, in Wiki integrieren, Index + Log aktualisieren
  - Query:  Semantisch suchen, relevante Notizen lesen, Antwort synthetisieren
  - Lint:   Wiki-Gesundheit prüfen (Orphans, Widersprüche, fehlende Verlinkungen)

Session-Management:
  Jeder API-Aufruf nutzt _licium_session() als asynccontextmanager.
  Login per Email+Password → Session-Cookie wird im httpx.AsyncClient gehalten.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

import httpx
from langchain_core.tools import tool

from agents.base_agent import _t
from core.tls import get_connection_verify_arg

logger = logging.getLogger("ninko.modules.licium.tools")

WIKI_ROOT_NAME = "Ninko Wiki"
WIKI_META_FOLDER = "_meta"
WIKI_SOURCES_FOLDER = "sources"
WIKI_WIKI_FOLDER = "wiki"
WIKI_QUERIES_FOLDER = "queries"
INDEX_NOTE_TITLE = "_index"
LOG_NOTE_TITLE = "_log"

# Tools, die nicht get_*/list_*/search_*/check_* heißen, aber readonly sind:
TOOL_REGISTRY_OVERRIDES = {
    "get_licium_wiki_meta": {"readonly": True},
}


# ── Session Context Manager ────────────────────────────────────────────────────

@asynccontextmanager
async def _licium_session(connection_id: str = "") -> AsyncGenerator[tuple[httpx.AsyncClient, str], None]:
    """Login bei Licium und gibt (client, base_url) zurück."""
    from core.connections import ConnectionManager
    from core.vault import get_vault

    if connection_id:
        conn = await ConnectionManager.get_connection("licium", connection_id)
        if not conn:
            raise ValueError(_t(
                de=f"Licium-Verbindung '{connection_id}' nicht gefunden.",
                en=f"Licium connection '{connection_id}' not found.",
            ))
    else:
        conn = await ConnectionManager.get_default_connection("licium")
        if not conn:
            import os
            base_url = os.environ.get("LICIUM_BASE_URL", "").rstrip("/")
            username = os.environ.get("LICIUM_USERNAME", "")
            password = os.environ.get("LICIUM_PASSWORD", "")
            if not base_url or not username or not password:
                raise ValueError(_t(
                    de="Licium nicht konfiguriert. Bitte Verbindung in Einstellungen hinterlegen.",
                    en="Licium not configured. Please set up a connection in Settings.",
                ))
            verify_arg = True
            async with httpx.AsyncClient(base_url=base_url, verify=verify_arg, timeout=30.0) as client:
                resp = await client.post("/api/login", json={"username": username, "password": password})
                resp.raise_for_status()
                yield client, base_url
            return

    vault = get_vault()
    base_url = conn.config.get("base_url", "").rstrip("/")
    username = conn.config.get("username", "")
    pw_key = conn.vault_keys.get("LICIUM_PASSWORD", "")
    password = await vault.get_secret(pw_key) if pw_key else ""

    if not base_url or not username or not password:
        raise ValueError(_t(
            de="Licium-Verbindung unvollständig: base_url, username und LICIUM_PASSWORD erforderlich.",
            en="Licium connection incomplete: base_url, username and LICIUM_PASSWORD required.",
        ))

    verify_arg = await get_connection_verify_arg(conn, "licium", default_verify=True)
    async with httpx.AsyncClient(base_url=base_url, verify=verify_arg, timeout=30.0) as client:
        resp = await client.post("/api/login", json={"username": username, "password": password})
        if resp.status_code != 200:
            raise ValueError(_t(
                de=f"Licium-Login fehlgeschlagen: HTTP {resp.status_code}",
                en=f"Licium login failed: HTTP {resp.status_code}",
            ))
        yield client, base_url


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _flatten_tree(nodes: list[dict], result: Optional[list] = None) -> list[dict]:
    """Rekursiv den Notizbaum in eine flache Liste umwandeln."""
    if result is None:
        result = []
    for node in nodes:
        result.append({
            "id": node.get("id"),
            "title": node.get("title"),
            "type": node.get("type"),
            "parent_id": node.get("parent_id"),
        })
        if node.get("children"):
            _flatten_tree(node["children"], result)
    return result


def _find_node_by_title(nodes: list[dict], title: str, node_type: str = "folder") -> Optional[dict]:
    """Sucht rekursiv einen Knoten nach Titel und Typ."""
    for node in nodes:
        if node.get("title") == title and node.get("type") == node_type:
            return node
        if node.get("children"):
            found = _find_node_by_title(node["children"], title, node_type)
            if found:
                return found
    return None


def _find_children_of(nodes: list[dict], parent_id: str) -> list[dict]:
    """Gibt direkte Kinder eines Knotens zurück."""
    all_nodes = _flatten_tree(nodes)
    return [n for n in all_nodes if n.get("parent_id") == parent_id]


async def _find_note_in_folder(client: httpx.AsyncClient, folder_id: str, title: str) -> Optional[str]:
    """Findet eine Notiz-ID nach Titel in einem Ordner. Gibt None zurück wenn nicht gefunden."""
    resp = await client.get("/api/tree")
    if resp.status_code != 200:
        return None
    tree = resp.json()
    nodes = tree if isinstance(tree, list) else tree.get("children", [])
    all_nodes = _flatten_tree(nodes)
    for node in all_nodes:
        if node.get("parent_id") == folder_id and node.get("title") == title:
            return node.get("id")
    return None


async def _get_or_create_folder(client: httpx.AsyncClient, name: str, parent_id: Optional[str] = None) -> str:
    """Findet oder erstellt einen Ordner. Gibt die ID zurück."""
    resp = await client.get("/api/tree")
    resp.raise_for_status()
    tree = resp.json()
    nodes = tree if isinstance(tree, list) else tree.get("children", [])

    all_nodes = _flatten_tree(nodes)
    for node in all_nodes:
        if node.get("title") == name and node.get("type") == "folder":
            if parent_id is None or node.get("parent_id") == parent_id:
                return node["id"]

    payload: dict = {"title": name, "type": "folder"}
    if parent_id:
        payload["parent_id"] = parent_id
    create_resp = await client.post("/api/notes", json=payload)
    create_resp.raise_for_status()
    return create_resp.json()["id"]


async def _get_or_create_note(
    client: httpx.AsyncClient,
    title: str,
    parent_id: str,
    initial_content: str = "",
) -> tuple[str, bool]:
    """Findet oder erstellt eine Notiz. Gibt (id, created) zurück."""
    note_id = await _find_note_in_folder(client, parent_id, title)
    if note_id:
        return note_id, False

    payload = {"title": title, "type": "note", "parent_id": parent_id, "content": initial_content}
    resp = await client.post("/api/notes", json=payload)
    resp.raise_for_status()
    return resp.json()["id"], True


# ── Read-only Tools ────────────────────────────────────────────────────────────

@tool("search_licium")
async def search_licium(query: str, connection_id: str = "") -> str:
    """Semantisch in der Licium-Wissensdatenbank suchen.

    Nutzt pgvector-RAG (Cosine Similarity) um die 5 relevantesten Notiz-Abschnitte
    zur Anfrage zu finden. Ideal für Fragen, die durch vorhandenes Wissen beantwortet werden sollen.

    Args:
        query: Suchanfrage in natürlicher Sprache.
        connection_id: Optional — ID einer bestimmten Licium-Verbindung.

    Returns:
        JSON-Liste der Treffer mit note_id, chunk_content und Titel.
    """
    async with _licium_session(connection_id) as (client, _):
        resp = await client.post("/api/rag/search", json={"query": query})
        resp.raise_for_status()
        results = resp.json()

        if not results:
            return _t(
                de="Keine relevanten Einträge gefunden.",
                en="No relevant entries found.",
            )

        lines = [_t(de=f"Suchergebnisse für: {query}", en=f"Search results for: {query}"), ""]
        for i, r in enumerate(results[:5], 1):
            lines.append(f"[{i}] Note-ID: {r.get('note_id', '?')}")
            lines.append(f"    Titel: {r.get('title', 'Unbekannt')}")
            lines.append(f"    Auszug: {r.get('chunk_content', '')[:300]}")
            lines.append("")
        return "\n".join(lines)


@tool("list_licium_tree")
async def list_licium_tree(connection_id: str = "") -> str:
    """Gibt die vollständige Ordner- und Notiz-Struktur der Licium-Instanz zurück.

    Zeigt alle Ordner und Notizen hierarchisch als Text. Nützlich um die aktuelle
    Wiki-Struktur zu verstehen bevor neue Inhalte eingepflegt werden.

    Args:
        connection_id: Optional — ID einer bestimmten Licium-Verbindung.

    Returns:
        Hierarchischer Baum als Text mit IDs und Titeln.
    """
    async with _licium_session(connection_id) as (client, _):
        resp = await client.get("/api/tree")
        resp.raise_for_status()
        tree = resp.json()
        nodes = tree if isinstance(tree, list) else tree.get("children", [])

        lines: list[str] = []

        def render(items: list[dict], depth: int = 0) -> None:
            indent = "  " * depth
            for item in items:
                icon = "📁" if item.get("type") == "folder" else "📄"
                lines.append(f"{indent}{icon} [{item.get('id', '?')}] {item.get('title', '?')}")
                if item.get("children"):
                    render(item["children"], depth + 1)

        render(nodes)
        if not lines:
            return _t(de="Keine Notizen gefunden.", en="No notes found.")
        return "\n".join(lines)


@tool("get_licium_note")
async def get_licium_note(note_id: str, connection_id: str = "") -> str:
    """Liest den vollständigen Inhalt einer Licium-Notiz anhand ihrer ID.

    Args:
        note_id: Die UUID der Notiz.
        connection_id: Optional — ID einer bestimmten Licium-Verbindung.

    Returns:
        Titel und Markdown-Inhalt der Notiz.
    """
    async with _licium_session(connection_id) as (client, _):
        resp = await client.get(f"/api/notes/{note_id}")
        if resp.status_code == 404:
            return _t(de=f"Notiz '{note_id}' nicht gefunden.", en=f"Note '{note_id}' not found.")
        resp.raise_for_status()
        note = resp.json()
        title = note.get("title", "Unbekannt")
        content = note.get("content_markdown", "") or note.get("content", "")
        return f"# {title}\n\nID: {note_id}\n\n{content}"


@tool("get_licium_wiki_meta")
async def get_licium_wiki_meta(connection_id: str = "") -> str:
    """Gibt die Metadaten der Ninko-Wiki-Struktur zurück (Ordner-IDs, Index- und Log-Notiz-IDs).

    Muss vor allen Schreiboperationen aufgerufen werden, um die korrekten parent_id-Werte
    für neue Notizen zu erhalten. Falls das Wiki noch nicht initialisiert ist, wird
    setup_licium_wiki() empfohlen.

    Args:
        connection_id: Optional — ID einer bestimmten Licium-Verbindung.

    Returns:
        JSON mit allen relevanten Ordner- und Notiz-IDs.
    """
    async with _licium_session(connection_id) as (client, _):
        resp = await client.get("/api/tree")
        resp.raise_for_status()
        tree = resp.json()
        nodes = tree if isinstance(tree, list) else tree.get("children", [])
        all_nodes = _flatten_tree(nodes)

        def find_id(title: str, ntype: str, parent: Optional[str] = None) -> Optional[str]:
            for n in all_nodes:
                if n.get("title") == title and n.get("type") == ntype:
                    if parent is None or n.get("parent_id") == parent:
                        return n.get("id")
            return None

        root_id = find_id(WIKI_ROOT_NAME, "folder")
        meta_id = find_id(WIKI_META_FOLDER, "folder", root_id) if root_id else None
        sources_id = find_id(WIKI_SOURCES_FOLDER, "folder", root_id) if root_id else None
        wiki_id = find_id(WIKI_WIKI_FOLDER, "folder", root_id) if root_id else None
        queries_id = find_id(WIKI_QUERIES_FOLDER, "folder", root_id) if root_id else None
        index_id = find_id(INDEX_NOTE_TITLE, "note", meta_id) if meta_id else None
        log_id = find_id(LOG_NOTE_TITLE, "note", meta_id) if meta_id else None

        initialized = all([root_id, meta_id, sources_id, wiki_id, index_id, log_id])

        result = {
            "initialized": initialized,
            "root_folder_id": root_id,
            "meta_folder_id": meta_id,
            "sources_folder_id": sources_id,
            "wiki_folder_id": wiki_id,
            "queries_folder_id": queries_id,
            "index_note_id": index_id,
            "log_note_id": log_id,
        }
        if not initialized:
            result["hint"] = _t(
                de="Wiki noch nicht vollständig initialisiert. Bitte setup_licium_wiki() aufrufen.",
                en="Wiki not yet fully initialized. Please call setup_licium_wiki() first.",
            )
        return json.dumps(result, ensure_ascii=False, indent=2)


# ── Write Tools ────────────────────────────────────────────────────────────────

@tool("setup_licium_wiki")
async def setup_licium_wiki(connection_id: str = "") -> str:
    """Initialisiert die Ninko-Wiki-Ordnerstruktur in Licium (idempotent).

    Erstellt folgende Struktur falls nicht vorhanden:
      📁 Ninko Wiki/
        📁 _meta/
          📄 _index   ← Katalog aller Wiki-Seiten
          📄 _log     ← Append-only Operationsprotokoll
        📁 sources/   ← Rohdaten-Zusammenfassungen
        📁 wiki/      ← Synthetisierte Wissenspages
        📁 queries/   ← Gespeicherte Query-Ergebnisse

    Kann mehrfach aufgerufen werden – bestehende Strukturen bleiben unverändert.

    Args:
        connection_id: Optional — ID einer bestimmten Licium-Verbindung.

    Returns:
        Bestätigung mit allen erstellten/gefundenen Ordner- und Notiz-IDs.
    """
    async with _licium_session(connection_id) as (client, _):
        root_id = await _get_or_create_folder(client, WIKI_ROOT_NAME)
        meta_id = await _get_or_create_folder(client, WIKI_META_FOLDER, root_id)
        sources_id = await _get_or_create_folder(client, WIKI_SOURCES_FOLDER, root_id)
        wiki_id = await _get_or_create_folder(client, WIKI_WIKI_FOLDER, root_id)
        queries_id = await _get_or_create_folder(client, WIKI_QUERIES_FOLDER, root_id)

        index_initial = "# Ninko Wiki — Index\n\nDiese Seite wird automatisch von Ninko gepflegt.\n\n| Titel | Zusammenfassung | Note-ID | Datum |\n|-------|-----------------|---------|-------|\n"
        log_initial = "# Ninko Wiki — Operationsprotokoll\n\nDieses Protokoll wird automatisch von Ninko geführt.\n\n"

        index_id, index_created = await _get_or_create_note(client, INDEX_NOTE_TITLE, meta_id, index_initial)
        log_id, log_created = await _get_or_create_note(client, LOG_NOTE_TITLE, meta_id, log_initial)

        return _t(
            de=(
                f"Wiki-Struktur bereit.\n"
                f"  Ninko Wiki: {root_id}\n"
                f"  _meta:     {meta_id}\n"
                f"  sources:   {sources_id}\n"
                f"  wiki:      {wiki_id}\n"
                f"  queries:   {queries_id}\n"
                f"  _index:    {index_id} ({'neu' if index_created else 'vorhanden'})\n"
                f"  _log:      {log_id} ({'neu' if log_created else 'vorhanden'})"
            ),
            en=(
                f"Wiki structure ready.\n"
                f"  Ninko Wiki: {root_id}\n"
                f"  _meta:     {meta_id}\n"
                f"  sources:   {sources_id}\n"
                f"  wiki:      {wiki_id}\n"
                f"  queries:   {queries_id}\n"
                f"  _index:    {index_id} ({'created' if index_created else 'exists'})\n"
                f"  _log:      {log_id} ({'created' if log_created else 'exists'})"
            ),
        )


@tool("create_licium_note")
async def create_licium_note(
    title: str,
    content: str,
    parent_id: str = "",
    note_type: str = "note",
    connection_id: str = "",
) -> str:
    """Erstellt eine neue Notiz oder einen Ordner in Licium.

    Args:
        title: Titel der Notiz oder des Ordners.
        content: Markdown-Inhalt der Notiz (leer für Ordner).
        parent_id: ID des übergeordneten Ordners. Leer = Root-Ebene.
        note_type: 'note' oder 'folder'.
        connection_id: Optional — ID einer bestimmten Licium-Verbindung.

    Returns:
        ID und Titel der neu erstellten Notiz.
    """
    async with _licium_session(connection_id) as (client, _):
        payload: dict = {"title": title, "type": note_type}
        if parent_id:
            payload["parent_id"] = parent_id
        if content and note_type == "note":
            payload["content"] = content

        resp = await client.post("/api/notes", json=payload)
        resp.raise_for_status()
        note = resp.json()
        note_id = note.get("id", "?")
        return _t(
            de=f"Notiz erstellt: '{title}' (ID: {note_id})",
            en=f"Note created: '{title}' (ID: {note_id})",
        )


@tool("update_licium_note")
async def update_licium_note(
    note_id: str,
    title: str,
    content: str,
    connection_id: str = "",
) -> str:
    """Aktualisiert Titel und Inhalt einer bestehenden Licium-Notiz.

    Wird beim Karpathy-Ingest genutzt um bestehende Wiki-Seiten mit neuen
    Informationen anzureichern (Verlinkungen ergänzen, Infos hinzufügen, etc.).

    Args:
        note_id: ID der zu aktualisierenden Notiz.
        title: Neuer (oder unveränderter) Titel.
        content: Neuer Markdown-Inhalt.
        connection_id: Optional — ID einer bestimmten Licium-Verbindung.

    Returns:
        Bestätigung der Aktualisierung.
    """
    async with _licium_session(connection_id) as (client, _):
        resp = await client.put(f"/api/notes/{note_id}", json={"title": title, "content": content})
        if resp.status_code == 404:
            return _t(de=f"Notiz '{note_id}' nicht gefunden.", en=f"Note '{note_id}' not found.")
        resp.raise_for_status()
        return _t(
            de=f"Notiz '{title}' (ID: {note_id}) aktualisiert.",
            en=f"Note '{title}' (ID: {note_id}) updated.",
        )


@tool("update_licium_wiki_index")
async def update_licium_wiki_index(
    title: str,
    summary: str,
    note_id: str,
    connection_id: str = "",
) -> str:
    """Fügt einen neuen Eintrag zur _index-Seite des Ninko-Wikis hinzu.

    Wird nach jedem Ingest-Vorgang aufgerufen um den zentralen Katalog aktuell zu halten.
    Der Index ist die primäre Navigationsseite für den LLM-Agenten.

    Args:
        title: Titel der neuen Wiki-Seite oder Quelle.
        summary: Kurze Beschreibung (1 Satz) des Inhalts.
        note_id: Licium Note-ID der zugehörigen Notiz.
        connection_id: Optional — ID einer bestimmten Licium-Verbindung.

    Returns:
        Bestätigung dass der Index aktualisiert wurde.
    """
    async with _licium_session(connection_id) as (client, _):
        meta_json = await _get_wiki_meta_raw(client)
        index_id = meta_json.get("index_note_id")
        if not index_id:
            return _t(
                de="Wiki-Index nicht gefunden. Bitte setup_licium_wiki() aufrufen.",
                en="Wiki index not found. Please call setup_licium_wiki() first.",
            )

        note_resp = await client.get(f"/api/notes/{index_id}")
        note_resp.raise_for_status()
        current = note_resp.json()
        current_content = current.get("content_markdown", "") or current.get("content", "")

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        new_row = f"| {title} | {summary} | {note_id} | {date_str} |"
        updated_content = current_content.rstrip() + "\n" + new_row + "\n"

        put_resp = await client.put(f"/api/notes/{index_id}", json={
            "title": INDEX_NOTE_TITLE,
            "content": updated_content,
        })
        put_resp.raise_for_status()
        return _t(
            de=f"Wiki-Index aktualisiert: '{title}' hinzugefügt.",
            en=f"Wiki index updated: '{title}' added.",
        )


@tool("append_licium_log")
async def append_licium_log(
    operation: str,
    title: str,
    connection_id: str = "",
) -> str:
    """Fügt einen Eintrag zum Wiki-Operationsprotokoll (_log) hinzu.

    Jede Ingest-, Query- und Lint-Operation wird hier protokolliert.
    Format: ## [DATUM] operation | titel

    Args:
        operation: Art der Operation ('ingest', 'query', 'lint', 'update').
        title: Titel der verarbeiteten Quelle oder Beschreibung der Operation.
        connection_id: Optional — ID einer bestimmten Licium-Verbindung.

    Returns:
        Bestätigung dass der Log-Eintrag hinzugefügt wurde.
    """
    async with _licium_session(connection_id) as (client, _):
        meta_json = await _get_wiki_meta_raw(client)
        log_id = meta_json.get("log_note_id")
        if not log_id:
            return _t(
                de="Wiki-Log nicht gefunden. Bitte setup_licium_wiki() aufrufen.",
                en="Wiki log not found. Please call setup_licium_wiki() first.",
            )

        note_resp = await client.get(f"/api/notes/{log_id}")
        note_resp.raise_for_status()
        current = note_resp.json()
        current_content = current.get("content_markdown", "") or current.get("content", "")

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        log_entry = f"\n## [{timestamp}] {operation} | {title}\n"
        updated_content = current_content.rstrip() + log_entry

        put_resp = await client.put(f"/api/notes/{log_id}", json={
            "title": LOG_NOTE_TITLE,
            "content": updated_content,
        })
        put_resp.raise_for_status()
        return _t(
            de=f"Log-Eintrag hinzugefügt: [{timestamp}] {operation} | {title}",
            en=f"Log entry added: [{timestamp}] {operation} | {title}",
        )


@tool("lint_licium_wiki")
async def lint_licium_wiki(connection_id: str = "") -> str:
    """Analysiert den Gesundheitszustand des Ninko-Wikis (Karpathy Lint-Operation).

    Prüft auf:
    - Orphan-Seiten (keine eingehenden Verlinkungen)
    - Seiten ohne Inhalt oder mit sehr wenig Text
    - Im Index aufgeführte Seiten die nicht (mehr) existieren
    - Fehlende queries/-Ordner oder _meta/-Dateien

    Args:
        connection_id: Optional — ID einer bestimmten Licium-Verbindung.

    Returns:
        Lint-Report als Markdown-Text mit Befunden und Empfehlungen.
    """
    async with _licium_session(connection_id) as (client, _):
        meta_json = await _get_wiki_meta_raw(client)
        if not meta_json.get("initialized"):
            return _t(
                de="Wiki nicht initialisiert. Bitte zuerst setup_licium_wiki() aufrufen.",
                en="Wiki not initialized. Please call setup_licium_wiki() first.",
            )

        resp = await client.get("/api/tree")
        resp.raise_for_status()
        tree = resp.json()
        nodes = tree if isinstance(tree, list) else tree.get("children", [])
        all_nodes = _flatten_tree(nodes)

        wiki_folder_id = meta_json.get("wiki_folder_id")
        sources_folder_id = meta_json.get("sources_folder_id")
        index_note_id = meta_json.get("index_note_id")

        wiki_notes = [n for n in all_nodes if n.get("parent_id") == wiki_folder_id and n.get("type") == "note"]
        source_notes = [n for n in all_nodes if n.get("parent_id") == sources_folder_id and n.get("type") == "note"]

        all_note_ids = {n["id"] for n in all_nodes if n.get("id")}

        index_resp = await client.get(f"/api/notes/{index_note_id}")
        index_resp.raise_for_status()
        index_content = index_resp.json().get("content_markdown", "") or ""

        import re
        index_ids = set(re.findall(r'\b([0-9a-f-]{36})\b', index_content))
        orphan_in_index = index_ids - all_note_ids

        issues: list[str] = []
        if orphan_in_index:
            issues.append(f"**Tote Index-Links** ({len(orphan_in_index)}):")
            for nid in orphan_in_index:
                issues.append(f"  - {nid} (im Index referenziert, Notiz nicht gefunden)")

        empty_wiki_pages = []
        for note in wiki_notes[:20]:
            nr = await client.get(f"/api/notes/{note['id']}")
            if nr.status_code == 200:
                content = nr.json().get("content_markdown", "") or ""
                if len(content.strip()) < 50:
                    empty_wiki_pages.append(note["title"])

        if empty_wiki_pages:
            issues.append(f"\n**Leere/kurze Wiki-Seiten** ({len(empty_wiki_pages)}):")
            for t in empty_wiki_pages:
                issues.append(f"  - {t}")

        all_content_ids: set[str] = set()
        for note in wiki_notes[:15]:
            nr = await client.get(f"/api/notes/{note['id']}")
            if nr.status_code == 200:
                content = nr.json().get("content_markdown", "") or ""
                found = re.findall(r'\b([0-9a-f-]{36})\b', content)
                all_content_ids.update(found)

        orphan_wiki = [n["title"] for n in wiki_notes if n["id"] not in all_content_ids and n["id"] not in index_ids]
        if orphan_wiki:
            issues.append(f"\n**Orphan Wiki-Seiten** (kein Inbound-Link, {len(orphan_wiki)}):")
            for t in orphan_wiki[:10]:
                issues.append(f"  - {t}")

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        summary = _t(
            de=(
                f"## Lint-Report — {date_str}\n\n"
                f"Wiki-Seiten: {len(wiki_notes)} | Quellen: {len(source_notes)}\n\n"
            ),
            en=(
                f"## Lint Report — {date_str}\n\n"
                f"Wiki pages: {len(wiki_notes)} | Sources: {len(source_notes)}\n\n"
            ),
        )

        if not issues:
            summary += _t(de="Keine Probleme gefunden. Wiki ist in gutem Zustand.", en="No issues found. Wiki is in good shape.")
        else:
            summary += "\n".join(issues)

        return summary


# ── Interne Hilfsfunktion (kein @tool) ─────────────────────────────────────────

async def _get_wiki_meta_raw(client: httpx.AsyncClient) -> dict:
    """Interne Version von get_licium_wiki_meta ohne Session-Overhead."""
    resp = await client.get("/api/tree")
    if resp.status_code != 200:
        return {}
    tree = resp.json()
    nodes = tree if isinstance(tree, list) else tree.get("children", [])
    all_nodes = _flatten_tree(nodes)

    def find_id(title: str, ntype: str, parent: Optional[str] = None) -> Optional[str]:
        for n in all_nodes:
            if n.get("title") == title and n.get("type") == ntype:
                if parent is None or n.get("parent_id") == parent:
                    return n.get("id")
        return None

    root_id = find_id(WIKI_ROOT_NAME, "folder")
    meta_id = find_id(WIKI_META_FOLDER, "folder", root_id) if root_id else None
    sources_id = find_id(WIKI_SOURCES_FOLDER, "folder", root_id) if root_id else None
    wiki_id = find_id(WIKI_WIKI_FOLDER, "folder", root_id) if root_id else None
    queries_id = find_id(WIKI_QUERIES_FOLDER, "folder", root_id) if root_id else None
    index_id = find_id(INDEX_NOTE_TITLE, "note", meta_id) if meta_id else None
    log_id = find_id(LOG_NOTE_TITLE, "note", meta_id) if meta_id else None

    return {
        "initialized": all([root_id, meta_id, sources_id, wiki_id, index_id, log_id]),
        "root_folder_id": root_id,
        "meta_folder_id": meta_id,
        "sources_folder_id": sources_id,
        "wiki_folder_id": wiki_id,
        "queries_folder_id": queries_id,
        "index_note_id": index_id,
        "log_note_id": log_id,
    }
