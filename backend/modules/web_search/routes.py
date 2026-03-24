"""
Web Search Modul – API Endpunkte für das Dashboard.
"""

import os
import httpx
import logging
from fastapi import APIRouter

logger = logging.getLogger("kumio.modules.web_search")

router = APIRouter()


@router.get("")
async def plugin_root():
    return {"status": "ok", "module": "web_search"}


@router.get("/status")
async def get_status():
    """Gibt SearXNG-Status und aktive Engines zurück."""
    searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8080").rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{searxng_url}/search",
                params={"q": "test", "format": "json"},
                headers={"X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1"},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        return {"connected": False, "error": "Timeout", "engines": []}
    except Exception as exc:
        return {"connected": False, "error": str(exc), "engines": []}

    # Engines aus server-timing-Header: total_0_wikipedia;dur=137
    timing_header = resp.headers.get("server-timing", "")
    engine_names: list[str] = []
    for part in timing_header.split(","):
        part = part.strip()
        if part.startswith("total_") and not part.startswith("total;"):
            seg = part.split(";")[0]       # total_0_wikipedia
            name_parts = seg.split("_")[2:]  # ['wikipedia']
            engine_names.append("_".join(name_parts))

    unresponsive = {e[0]: e[1] for e in data.get("unresponsive_engines", [])}

    engines = []
    for name in engine_names:
        if name in unresponsive:
            engines.append({"name": name, "status": "error", "reason": unresponsive[name]})
        else:
            engines.append({"name": name, "status": "ok"})

    for name, reason in unresponsive.items():
        if not any(e["name"] == name for e in engines):
            engines.append({"name": name, "status": "error", "reason": reason})

    return {
        "connected": True,
        "searxng_url": searxng_url,
        "engines": engines,
        "result_count": len(data.get("results", [])),
    }
