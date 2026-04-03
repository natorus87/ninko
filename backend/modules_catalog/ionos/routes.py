"""IONOS DNS Module — FastAPI Router for Dashboard API."""
import logging
from fastapi import APIRouter
from .tools import _ionos_request

logger = logging.getLogger("ninko.modules.ionos.routes")
router = APIRouter()

@router.get("/status")
async def get_status(connection_id: str = ""):
    """
    Health check and status for the IONOS DNS module.
    Tests the API connection.
    """
    try:
        zones = await _ionos_request("GET", "zones", connection_id=connection_id)
        zone_count = len(zones) if isinstance(zones, list) else 0
        return {"status": "ok", "message": f"Connected. {zone_count} zones found."}
    except Exception as e:
        logger.warning("IONOS API error: %s", str(e))
        return {"status": "error", "message": str(e)}
