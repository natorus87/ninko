"""
Pi-hole Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from modules.pihole.tools import (
    get_pihole_summary,
    get_query_log,
    get_top_domains,
    get_top_clients,
    toggle_blocking,
    get_blocklists,
    add_domain_to_list,
    remove_domain_from_list,
    get_pihole_system,
)

logger = logging.getLogger("ninko.modules.pihole.routes")
router = APIRouter()


def _error(msg: str, status: int = 502) -> JSONResponse:
    """Strukturierte Fehler-Antwort."""
    logger.warning("Pi-hole API Fehler: %s", msg)
    return JSONResponse({"error": str(msg)}, status_code=status)


@router.get("/summary")
async def summary(connection_id: str = ""):
    """Pi-hole Zusammenfassung."""
    try:
        return await get_pihole_summary.ainvoke({"connection_id": connection_id})
    except ValueError as e:
        return _error(str(e), 503)
    except Exception as e:
        return _error(str(e))


@router.get("/queries")
async def queries(count: int = 100, connection_id: str = ""):
    """Letzte DNS-Anfragen."""
    try:
        return await get_query_log.ainvoke({"count": count, "connection_id": connection_id})
    except ValueError as e:
        return _error(str(e), 503)
    except Exception as e:
        return _error(str(e))


@router.get("/top-domains")
async def top_domains(count: int = 10, connection_id: str = ""):
    """Top erlaubte und blockierte Domains."""
    try:
        return await get_top_domains.ainvoke({"count": count, "connection_id": connection_id})
    except ValueError as e:
        return _error(str(e), 503)
    except Exception as e:
        return _error(str(e))


@router.get("/top-clients")
async def top_clients(count: int = 10, connection_id: str = ""):
    """Top Clients."""
    try:
        return await get_top_clients.ainvoke({"count": count, "connection_id": connection_id})
    except ValueError as e:
        return _error(str(e), 503)
    except Exception as e:
        return _error(str(e))


@router.post("/blocking")
async def set_blocking(enable: bool = True, duration: int = 0, connection_id: str = ""):
    """DNS-Blocking aktivieren/deaktivieren."""
    try:
        msg = await toggle_blocking.ainvoke({"enable": enable, "duration": duration, "connection_id": connection_id})
        return {"message": msg}
    except ValueError as e:
        return _error(str(e), 503)
    except Exception as e:
        return _error(str(e))


@router.get("/blocklists")
async def blocklists(connection_id: str = ""):
    """Alle Blocklisten."""
    try:
        return await get_blocklists.ainvoke({"connection_id": connection_id})
    except ValueError as e:
        return _error(str(e), 503)
    except Exception as e:
        return _error(str(e))


@router.post("/domains/{list_type}/{kind}")
async def add_domain(list_type: str, kind: str, domain: str, comment: str = "", connection_id: str = ""):
    """Domain zur Whitelist/Blacklist hinzufügen."""
    try:
        msg = await add_domain_to_list.ainvoke({
            "domain": domain,
            "list_type": list_type,
            "kind": kind,
            "comment": comment,
            "connection_id": connection_id,
        })
        return {"message": msg}
    except ValueError as e:
        return _error(str(e), 503)
    except Exception as e:
        return _error(str(e))


@router.delete("/domains/{list_type}/{kind}")
async def remove_domain(list_type: str, kind: str, domain: str, connection_id: str = ""):
    """Domain von der Whitelist/Blacklist entfernen."""
    try:
        msg = await remove_domain_from_list.ainvoke({
            "domain": domain,
            "list_type": list_type,
            "kind": kind,
            "connection_id": connection_id,
        })
        return {"message": msg}
    except ValueError as e:
        return _error(str(e), 503)
    except Exception as e:
        return _error(str(e))


@router.get("/system")
async def system_info(connection_id: str = ""):
    """Pi-hole System-Informationen."""
    try:
        return await get_pihole_system.ainvoke({"connection_id": connection_id})
    except ValueError as e:
        return _error(str(e), 503)
    except Exception as e:
        return _error(str(e))
