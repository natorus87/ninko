import logging
from fastapi import APIRouter
from modules.ionos.tools import _ionos_request

logger = logging.getLogger("kumio.modules.ionos.routes")
router = APIRouter()

@router.get("/status")
async def get_status(connection_id: str = ""):
    """
    Healthcheck und Status für das IONOS DNS Modul.
    Testet die Verbindung zur API.
    """
    try:
        zones = await _ionos_request("GET", "zones", connection_id=connection_id)
        zone_count = len(zones) if isinstance(zones, list) else 0
        return {"status": "ok", "message": f"Verbunden. {zone_count} Zonen gefunden."}
    except Exception as e:
        logger.warning("IONOS API Fehler: %s", str(e))
        return {"status": "error", "message": str(e)}
