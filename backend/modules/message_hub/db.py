"""
Message Hub — SQLite Routing-Tabelle.

Mappt (channel_type, channel_id) → (session_id, permission_cap, label).
Wird von allen Background-Workern zum Lookup genutzt.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path

import aiosqlite

from .schemas import PermissionCap, RouteCreate, RouteEntry, RouteUpdate

logger = logging.getLogger("ninko.modules.message_hub.db")

# SQLite-Datei im persistenten /data-Verzeichnis (wie Knowledge Graph)
_DB_PATH = Path("/data/message_hub_routes.db")
_FALLBACK_DB_PATH = Path("data/message_hub_routes.db")

_db_path: Path = _DB_PATH
_db_lock = asyncio.Lock()
_init_event: asyncio.Event | None = None


def get_db_path() -> Path:
    return _db_path


async def _ensure_db() -> None:
    """Stellt sicher, dass die DB und Tabelle existieren (idempotent, race-safe)."""
    global _db_path, _init_event

    # _init_event wird beim ersten Aufruf unter Lock erstellt
    if _init_event is None:
        async with _db_lock:
            if _init_event is None:
                _init_event = asyncio.Event()
            else:
                # Anderer Aufruf hat Event gerade erstellt — warten
                await _init_event.wait()
                return

    if _init_event.is_set():
        return

    # /data bevorzugen, aber Fallback auf data/ im Projekt-Root
    if not _DB_PATH.parent.exists():
        logger.warning("Message Hub: /data nicht verfügbar, nutze data/ als Fallback")
        _db_path = _FALLBACK_DB_PATH

    async with aiosqlite.connect(str(_db_path)) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS routes (
                id          TEXT PRIMARY KEY,
                channel_type TEXT NOT NULL,
                channel_id  TEXT NOT NULL,
                session_id  TEXT NOT NULL,
                permission_cap TEXT NOT NULL DEFAULT 'WRITE_DATA',
                label       TEXT NOT NULL DEFAULT '',
                enabled     INTEGER NOT NULL DEFAULT 1,
                created_at  REAL NOT NULL,
                UNIQUE(channel_type, channel_id)
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_channel ON routes (channel_type, enabled)"
        )
        await db.commit()

    _init_event.set()
    logger.info("Message Hub DB bereit: %s", _db_path)


# ── CRUD ───────────────────────────────────────────────────────────────


async def list_routes(channel_type: str | None = None) -> list[RouteEntry]:
    """Gibt alle Routing-Einträge zurück, optional nach channel_type gefiltert."""
    await _ensure_db()
    async with _db_lock:
        async with aiosqlite.connect(str(_db_path)) as db:
            db.row_factory = aiosqlite.Row
            if channel_type:
                cur = await db.execute(
                    "SELECT * FROM routes WHERE channel_type = ? ORDER BY created_at DESC",
                    (channel_type,),
                )
            else:
                cur = await db.execute(
                    "SELECT * FROM routes ORDER BY channel_type, created_at DESC"
                )
            rows = await cur.fetchall()
            return [_row_to_entry(r) for r in rows]


async def get_route(route_id: str) -> RouteEntry | None:
    """Gibt einen Eintrag nach ID zurück."""
    await _ensure_db()
    async with _db_lock:
        async with aiosqlite.connect(str(_db_path)) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM routes WHERE id = ?", (route_id,))
            row = await cur.fetchone()
            return _row_to_entry(row) if row else None


async def lookup_route(channel_type: str, channel_id: str) -> RouteEntry | None:
    """Lookup für eingehende Nachrichten: gibt aktiven Eintrag zurück oder None."""
    await _ensure_db()
    async with _db_lock:
        async with aiosqlite.connect(str(_db_path)) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM routes WHERE channel_type = ? AND channel_id = ? AND enabled = 1",
                (channel_type, channel_id),
            )
            row = await cur.fetchone()
            return _row_to_entry(row) if row else None


async def create_route(data: RouteCreate) -> RouteEntry:
    """Legt einen neuen Routing-Eintrag an."""
    await _ensure_db()
    entry = RouteEntry(
        id=str(uuid.uuid4()),
        channel_type=data.channel_type,
        channel_id=data.channel_id.strip(),
        session_id=data.session_id.strip(),
        permission_cap=data.permission_cap,
        label=data.label.strip(),
        enabled=data.enabled,
        created_at=time.time(),
    )
    async with _db_lock:
        async with aiosqlite.connect(str(_db_path)) as db:
            await db.execute(
                """INSERT INTO routes (id, channel_type, channel_id, session_id,
                   permission_cap, label, enabled, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.id,
                    entry.channel_type,
                    entry.channel_id,
                    entry.session_id,
                    entry.permission_cap.value,
                    entry.label,
                    int(entry.enabled),
                    entry.created_at,
                ),
            )
            await db.commit()
    logger.info(
        "Route erstellt: %s → session=%s (%s/%s)",
        entry.id,
        entry.session_id,
        entry.channel_type,
        entry.channel_id,
    )
    return entry


ALLOWED_ROUTE_UPDATE_FIELDS = frozenset({
    "session_id",
    "permission_cap",
    "label",
    "enabled",
})


_UPDATE_ROUTE_SQL: dict[frozenset[str], str] = {
    frozenset({"session_id"}): "UPDATE routes SET session_id = ? WHERE id = ?",
    frozenset({"permission_cap"}): "UPDATE routes SET permission_cap = ? WHERE id = ?",
    frozenset({"label"}): "UPDATE routes SET label = ? WHERE id = ?",
    frozenset({"enabled"}): "UPDATE routes SET enabled = ? WHERE id = ?",
    frozenset({"session_id", "permission_cap"}): "UPDATE routes SET session_id = ?, permission_cap = ? WHERE id = ?",
    frozenset({"session_id", "label"}): "UPDATE routes SET session_id = ?, label = ? WHERE id = ?",
    frozenset({"session_id", "enabled"}): "UPDATE routes SET session_id = ?, enabled = ? WHERE id = ?",
    frozenset({"permission_cap", "label"}): "UPDATE routes SET permission_cap = ?, label = ? WHERE id = ?",
    frozenset({"permission_cap", "enabled"}): "UPDATE routes SET permission_cap = ?, enabled = ? WHERE id = ?",
    frozenset({"label", "enabled"}): "UPDATE routes SET label = ?, enabled = ? WHERE id = ?",
    frozenset({"session_id", "permission_cap", "label"}): "UPDATE routes SET session_id = ?, permission_cap = ?, label = ? WHERE id = ?",
    frozenset({"session_id", "permission_cap", "enabled"}): "UPDATE routes SET session_id = ?, permission_cap = ?, enabled = ? WHERE id = ?",
    frozenset({"session_id", "label", "enabled"}): "UPDATE routes SET session_id = ?, label = ?, enabled = ? WHERE id = ?",
    frozenset({"permission_cap", "label", "enabled"}): "UPDATE routes SET permission_cap = ?, label = ?, enabled = ? WHERE id = ?",
    frozenset({"session_id", "permission_cap", "label", "enabled"}): "UPDATE routes SET session_id = ?, permission_cap = ?, label = ?, enabled = ? WHERE id = ?",
}


async def update_route(route_id: str, data: RouteUpdate) -> RouteEntry | None:
    """Aktualisiert einen Routing-Eintrag."""
    await _ensure_db()

    fields: dict[str, object] = {}
    if data.session_id is not None:
        fields["session_id"] = data.session_id.strip()
    if data.permission_cap is not None:
        fields["permission_cap"] = data.permission_cap.value
    if data.label is not None:
        fields["label"] = data.label.strip()
    if data.enabled is not None:
        fields["enabled"] = int(data.enabled)

    invalid = set(fields) - ALLOWED_ROUTE_UPDATE_FIELDS
    if invalid:
        raise ValueError(f"Unbekannte Felder: {sorted(invalid)}")

    async with _db_lock:
        async with aiosqlite.connect(str(_db_path)) as db:
            db.row_factory = aiosqlite.Row
            # Existenz-Check + Update innerhalb desselben Locks (kein TOCTOU)
            cur = await db.execute("SELECT * FROM routes WHERE id = ?", (route_id,))
            row = await cur.fetchone()
            if not row:
                return None
            if not fields:
                return _row_to_entry(row)
            sql = _UPDATE_ROUTE_SQL[frozenset(fields)]
            values = list(fields.values()) + [route_id]
            await db.execute(sql, values)
            await db.commit()
            cur2 = await db.execute("SELECT * FROM routes WHERE id = ?", (route_id,))
            updated = await cur2.fetchone()
            return _row_to_entry(updated) if updated else None


async def delete_route(route_id: str) -> bool:
    """Löscht einen Routing-Eintrag."""
    await _ensure_db()
    async with _db_lock:
        async with aiosqlite.connect(str(_db_path)) as db:
            cur = await db.execute("DELETE FROM routes WHERE id = ?", (route_id,))
            await db.commit()
            return cur.rowcount > 0


# ── Helpers ────────────────────────────────────────────────────────────


def _row_to_entry(row: aiosqlite.Row) -> RouteEntry:
    return RouteEntry(
        id=row["id"],
        channel_type=row["channel_type"],
        channel_id=row["channel_id"],
        session_id=row["session_id"],
        permission_cap=PermissionCap(row["permission_cap"]),
        label=row["label"] or "",
        enabled=bool(row["enabled"]),
        created_at=float(row["created_at"]),
    )
