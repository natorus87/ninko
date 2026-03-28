from fastapi import APIRouter, HTTPException
import logging
from .tools import (
    get_fritz_devices,
    get_fritz_wan_status,
    get_fritz_bandwidth,
    get_fritz_wlan_status,
    get_fritz_system_info
)

logger = logging.getLogger("ninko.modules.fritzbox")

router = APIRouter(tags=["FritzBox"])

@router.get("/status")
async def get_status(connection_id: str = ""):
    """Holt WAN-Status, WLAN-Status, Systeminfos und Bandbreite für das Dashboard."""
    try:
        wan = await get_fritz_wan_status.ainvoke({"connection_id": connection_id})
        wlan = await get_fritz_wlan_status.ainvoke({"connection_id": connection_id})
        bw = await get_fritz_bandwidth.ainvoke({"connection_id": connection_id})
        sys = await get_fritz_system_info.ainvoke({"connection_id": connection_id})
        
        # Merge dictionary objects
        return {
            "wan": wan if "error" not in wan else {"connected": False, "ip_address": "N/A"},
            "wlan": wlan if not (isinstance(wlan, list) and wlan and "error" in wlan[0]) else [],
            "bandwidth": bw if "error" not in bw else {"ds_current": 0, "us_current": 0},
            "system": sys if "error" not in sys else {"model": "Fehler / Nicht Erreichbar", "firmware_version": "-", "uptime": 0}
        }
    except Exception as e:
        logger.error(f"Error fetching FritzBox status: {e}")
        return {
            "wan": {"connected": False, "ip_address": "N/A"},
            "wlan": [],
            "bandwidth": {"ds_current": 0, "us_current": 0},
            "system": {"model": "FritzBox nicht konfiguriert oder offline", "firmware_version": "-", "uptime": 0}
        }

@router.get("/devices")
async def get_devices(connection_id: str = ""):
    """Holt die Liste aller Geräte im Heimnetz."""
    try:
        devices = await get_fritz_devices.ainvoke({"connection_id": connection_id})
        # devices is either a list of dicts or [{"error": "..."}]
        if devices and isinstance(devices, list) and "error" in devices[0]:
            return [] # gracefully return empty list to frontend
        return devices
    except Exception as e:
        logger.error(f"Error fetching FritzBox devices: {e}")
        return []
