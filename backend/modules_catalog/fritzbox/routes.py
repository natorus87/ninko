import ast
import json
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


def _normalize_tool_output(value: object) -> object:
    if isinstance(value, str):
        text = value.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(text)
            except (SyntaxError, ValueError):
                return value
    return value

@router.get("/status")
async def get_status(connection_id: str = "") -> object:
    """Fetch WAN status, WLAN status, system info and bandwidth for the dashboard."""
    async def _safe_call(tool, payload: dict, fallback):
        try:
            result = await tool.ainvoke(payload)
            return _normalize_tool_output(result)
        except Exception as exc:
            logger.warning("FritzBox status partial failure (%s): %s", tool.name, exc)
            return fallback

    wan_fallback = {"connected": False, "ip_address": "N/A"}
    wlan_fallback: list[dict] = []
    bw_fallback = {"ds_current": 0, "us_current": 0}
    sys_fallback = {
        "model": "Error / Unreachable",
        "firmware_version": "-",
        "uptime": 0,
    }

    wan = await _safe_call(get_fritz_wan_status, {"connection_id": connection_id}, wan_fallback)
    wlan = await _safe_call(get_fritz_wlan_status, {"connection_id": connection_id}, wlan_fallback)
    bw = await _safe_call(get_fritz_bandwidth, {"connection_id": connection_id}, bw_fallback)
    sys = await _safe_call(get_fritz_system_info, {"connection_id": connection_id}, sys_fallback)

    # Merge dictionary objects with defensive fallbacks
    return {
        "wan": wan if isinstance(wan, dict) and "error" not in wan else wan_fallback,
        "wlan": wlan if isinstance(wlan, list) and not (wlan and isinstance(wlan[0], dict) and "error" in wlan[0]) else wlan_fallback,
        "bandwidth": bw if isinstance(bw, dict) and "error" not in bw else bw_fallback,
        "system": sys if isinstance(sys, dict) and "error" not in sys else sys_fallback,
    }

@router.get("/devices")
async def get_devices(connection_id: str = "") -> object:
    """Retrieve the list of all devices on the home network."""
    try:
        devices = await get_fritz_devices.ainvoke({"connection_id": connection_id})
        devices = _normalize_tool_output(devices)
        # devices is either a list of dicts or [{"error": "..."}]
        if devices and isinstance(devices, list) and "error" in devices[0]:
            return [] # gracefully return empty list to frontend
        return devices
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        logger.error("Error fetching FritzBox devices: %s", exc)
        return []
