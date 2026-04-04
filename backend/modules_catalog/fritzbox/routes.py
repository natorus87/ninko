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
async def get_status(connection_id: str = "") -> object:
    """Fetch WAN status, WLAN status, system info and bandwidth for the dashboard."""
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
            "system": sys if "error" not in sys else {"model": "Error / Unreachable", "firmware_version": "-", "uptime": 0}
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        logger.error("Error fetching FritzBox status: %s", e)
        return {
            "wan": {"connected": False, "ip_address": "N/A"},
            "wlan": [],
            "bandwidth": {"ds_current": 0, "us_current": 0},
            "system": {"model": "FritzBox not configured or offline", "firmware_version": "-", "uptime": 0}
        }

@router.get("/devices")
async def get_devices(connection_id: str = "") -> object:
    """Retrieve the list of all devices on the home network."""
    try:
        devices = await get_fritz_devices.ainvoke({"connection_id": connection_id})
        # devices is either a list of dicts or [{"error": "..."}]
        if devices and isinstance(devices, list) and "error" in devices[0]:
            return [] # gracefully return empty list to frontend
        return devices
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        logger.error("Error fetching FritzBox devices: %s", e)
        return []
