"""
Agent Browser Modul – API-Endpunkte für Dashboard / externe Aufrufer.
"""

from __future__ import annotations

import logging
import shutil

from fastapi import APIRouter
from pydantic import BaseModel, HttpUrl

from modules.agent_browser.manifest import check_agent_browser_health
from modules.agent_browser.tools import (
    check_website as _check_website_tool,
    list_browser_sessions as _list_sessions_tool,
)

logger = logging.getLogger("ninko.modules.agent_browser")

router = APIRouter()


class CheckRequest(BaseModel):
    """Request body for the website-check endpoint."""

    url: HttpUrl


@router.get("")
async def plugin_root() -> dict:
    """Liefert Modul-Identifikation für Discovery."""
    return {"status": "ok", "module": "agent_browser"}


@router.get("/status")
async def get_status() -> dict:
    """Liefert Verfügbarkeit der Binary + Version."""
    health = await check_agent_browser_health()
    return {
        "connected": health.get("status") == "ok",
        "detail": health.get("detail", ""),
        "binary_path": shutil.which("agent-browser") or "",
    }


@router.get("/sessions")
async def list_sessions() -> dict:
    """Listet laufende agent-browser Sessions (über das gemeinsame Tool)."""
    raw = await _list_sessions_tool.ainvoke({})
    if raw.startswith("ERROR:"):
        return {"sessions": [], "error": raw.removeprefix("ERROR:").strip()}
    sessions = [
        line.strip()
        for line in raw.splitlines()
        if line.strip() and line.strip() != "(no sessions)"
    ]
    return {"sessions": sessions}


@router.post("/check")
async def check_endpoint(req: CheckRequest) -> dict:
    """
    Führt einen Quick-Check der Webseite durch (open + snapshot + close).

    SSRF-Filter im Tool selbst (loopback / link-local / metadata werden geblockt).
    """
    result = await _check_website_tool.ainvoke({"url": str(req.url)})
    return {"ok": not result.startswith("FAIL"), "result": result}
