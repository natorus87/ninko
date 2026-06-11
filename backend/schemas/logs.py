"""
Ninko Logs Schemas – Struktur für Log-Einträge aus dem Redis-Log-Store.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    """Ein einzelner Log-Eintrag aus dem Redis-Log-Store."""

    timestamp: str = Field("", description="Formatierter Zeitstempel (YYYY-MM-DD HH:MM:SS)")
    timestamp_unix: float = Field(0.0, description="Unix-Timestamp")
    level: str = Field("INFO", description="Log-Level (INFO, WARN, ERROR, CRIT)")
    logger: str = Field("", description="Logger-Name (z.B. ninko.api.logs)")
    category: str = Field("system", description="Kategorie (agent, workflow, module, system, llm)")
    source: str = Field("", description="Quell-Agent oder Workflow-Name")
    message: str = Field("", description="Log-Message")
    session_id: Optional[str] = Field(None, description="Optional: Session-ID")
    tenant_id: Optional[str] = Field(None, description="Tenant-ID")
    traceback: Optional[str] = Field(None, description="Optional: Traceback bei Exceptions")


class LogListResponse(BaseModel):
    """Response: Liste von Log-Einträgen."""

    entries: list[LogEntry]
    total: int


class LogClearResponse(BaseModel):
    """Response: Log-Clear-Operation."""

    cleared: bool
    removed: int
