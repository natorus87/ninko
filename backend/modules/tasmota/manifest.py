"""
Tasmota Modul – Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations

import logging
import os

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.tasmota")


async def check_tasmota_health(connection_id: str = "") -> dict:
    """Health-Check für Tasmota-Geräte via HTTP."""
    from core.connections import ConnectionManager
    import httpx

    try:
        conn_data = await ConnectionManager.get_connection("tasmota", connection_id)
        if not conn_data:
            conn_data = await ConnectionManager.get_default_connection("tasmota")

        if not conn_data:
            return {"status": "error", "detail": "Keine Tasmota-Verbindung konfiguriert."}

        host = conn_data.config.get("host", "")
        if not host:
            return {"status": "error", "detail": "Keine Host-Adresse konfiguriert."}

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"http://{host}/cm?cmnd=Status")
            if resp.status_code == 200:
                return {"status": "ok", "detail": f"Tasmota unter {host} erreichbar"}
            return {"status": "error", "detail": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


module_manifest = ModuleManifest(
    name="tasmota",
    display_name="Tasmota",
    description="Steuerung und Monitoring von Tasmota-Geräten (ESP8266/ESP32) via HTTP REST API.",
    version="1.0.0",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="TASMOTA_",
    required_secrets=[],
    optional_secrets=[],

    routing_keywords=[
        "tasmota", "esp8266", "esp32", "sonoff", "smart home", "shelly",
        "schalter", "steckdose", "relais", "sensor", "temperatur", "feuchtigkeit",
        "leistung", "stromverbrauch", "mqtt", "smartmeter"
    ],

    api_prefix="/api/tasmota",

    dashboard_tab={
        "id": "tasmota",
        "label": "Tasmota",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"></path><path d="M2 17l10 5 10-5"></path><path d="M2 12l10 5 10-5"></path></svg>',
    },

    health_check=check_tasmota_health,
)
