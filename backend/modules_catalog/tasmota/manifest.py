"""Tasmota module — manifest with metadata and health check."""

from __future__ import annotations

import logging
import os
from urllib.parse import quote_plus

import httpx

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.tasmota")


def _build_tasmota_command_url(host: str, command: str) -> str:
    base = host.strip().rstrip("/")
    if not base:
        raise ValueError("No host address configured.")
    if not base.startswith(("http://", "https://")):
        base = f"http://{base}"
    return f"{base}/cm?cmnd={quote_plus(command)}"


async def check_tasmota_health(connection_id: str = "") -> dict:
    """Health check for Tasmota devices via HTTP."""
    from core.connections import ConnectionManager

    try:
        if connection_id:
            conn_data = await ConnectionManager.get_connection("tasmota", connection_id)
        else:
            conn_data = await ConnectionManager.get_default_connection("tasmota")

        host = ""
        source = "connection"
        if conn_data:
            host = conn_data.config.get("host", "")
        if not host:
            host = os.environ.get("TASMOTA_HOST", "")
            source = "env"
        if not conn_data:
            source = "env" if host else "none"

        if not host:
            return {"status": "error", "detail": "No host address configured."}

        url = _build_tasmota_command_url(host, "Status")
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return {
                    "status": "ok",
                    "detail": f"Tasmota at {host} reachable ({source})",
                }
            return {"status": "error", "detail": f"HTTP {resp.status_code}"}
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        httpx.HTTPError,
    ) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="tasmota",
    display_name="Tasmota",
    description=(
        "Tasmota smart home devices on ESP8266 / ESP32 (Sonoff, Shelly): "
        "switches, plugs, relays, sensors. Read temperature, humidity, power "
        "and energy consumption; MQTT, smart meters. Switch relays/devices on "
        "or off."
    ),
    version="1.1.4",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="TASMOTA_",
    required_secrets=[],
    optional_secrets=[],

    routing_keywords=[
        "tasmota", "esp8266", "esp32", "sonoff", "smart home", "shelly",
        "schalter", "steckdose", "relais", "sensor", "temperatur", "feuchtigkeit",
        "leistung", "stromverbrauch", "mqtt", "smartmeter",
        "einschalten", "ausschalten", "schalten", "gerät einschalten",
        "gerät ausschalten", "gruppe einschalten", "gruppe ausschalten",
    ],

    api_prefix="/api/tasmota",

    dashboard_tab={
        "id": "tasmota",
        "label": "Tasmota",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"></path><path d="M2 17l10 5 10-5"></path><path d="M2 12l10 5 10-5"></path></svg>',
    },

    health_check=check_tasmota_health,
)
