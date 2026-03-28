"""
Tasmota Modul – LangGraph @tool-Funktionen.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import tool

from core.connections import ConnectionManager

logger = logging.getLogger("ninko.modules.tasmota.tools")


async def _get_tasmota_host(connection_id: str = "") -> str:
    """
    Hilfsfunktion: Lädt die Host-Adresse aus dem ConnectionManager oder Env-Variablen.
    """
    if connection_id:
        conn = await ConnectionManager.get_connection("tasmota", connection_id)
        if not conn:
            raise ValueError(f"Tasmota-Verbindung mit ID '{connection_id}' nicht gefunden.")
    else:
        conn = await ConnectionManager.get_default_connection("tasmota")

    if conn:
        return conn.config.get("host", "")

    return os.environ.get("TASMOTA_HOST", "")


async def _tasmota_request(host: str, command: str, timeout: float = 5.0) -> Dict:
    """
    Sendet einen HTTP-Befehl an ein Tasmota-Gerät.
    Tasmota API: http://<host>/cm?cmnd=<command>
    """
    if not host:
        raise ValueError("Keine Tasmota-Host-Adresse angegeben.")

    url = f"http://{host}/cm?cmnd={command}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


@tool
async def get_tasmota_status(connection_id: str = "") -> Dict:
    """
    Ruft den allgemeinen Status eines Tasmota-Geräts ab (Hostname, IP, Uptime, Last, WLAN-RSSI).
    Benutze dieses Tool, um Informationen über ein Tasmota-Gerät zu erhalten.
    Use this tool to get general information about a Tasmota device.
    """
    try:
        host = await _get_tasmota_host(connection_id)
        if not host:
            raise ValueError(
                "Keine Tasmota-Verbindung konfiguriert. "
                "Bitte im Dashboard unter Einstellungen → Modul → Zahnrad eine Verbindung anlegen, "
                "oder die Env-Variable TASMOTA_HOST setzen."
            )

        result = await _tasmota_request(host, "Status")
        status = result.get("Status", {})

        return {
            "hostname": status.get("Hostname", ""),
            "ip_address": status.get("IPAddress", ""),
            "uptime": status.get("Uptime", 0),
            "load": status.get("Load", 0),
            "wifi_rssi": status.get("Wifi", {}).get("RSSI", 0) if isinstance(status.get("Wifi"), dict) else 0,
            "model": status.get("Module", ""),
            "firmware": status.get("Version", ""),
        }
    except Exception as e:
        logger.error("Fehler beim Abrufen des Tasmota-Status: %s", e)
        return {"error": str(e)}


@tool
async def get_tasmota_power(connection_id: str = "") -> Dict:
    """
    Ruft den Power-Status aller Relais eines Tasmota-Geräts ab.
    Zeigt, welche Schalter ein- oder ausgeschaltet sind.
    Use this tool to check which switches are on or off.
    """
    try:
        host = await _get_tasmota_host(connection_id)
        if not host:
            raise ValueError("Keine Tasmota-Host-Adresse konfiguriert.")

        result = await _tasmota_request(host, "Power")
        power_state = result.get("POWER1", result.get("POWER", "OFF"))

        return {
            "power1": power_state.upper() == "ON" if isinstance(power_state, str) else None,
            "raw": result,
        }
    except Exception as e:
        logger.error("Fehler beim Abrufen des Power-Status: %s", e)
        return {"error": str(e)}


@tool
async def set_tasmota_power(state: bool, relay: int = 1, connection_id: str = "") -> str:
    """
    Schaltet ein Relais eines Tasmota-Geräts ein oder aus.
    state: True = einschalten, False = ausschalten.
    relay: Relais-Nummer (1-4), Standard ist 1.
    Benutze dieses Tool, um Steckdosen, Lichter oder andere Schalter zu steuern.
    Use this tool to turn switches or outlets on or off.
    """
    try:
        host = await _get_tasmota_host(connection_id)
        if not host:
            return "Fehler: Keine Tasmota-Host-Adresse konfiguriert."

        command = f"Power{relay}" if relay > 1 else "Power"
        value = "ON" if state else "OFF"

        result = await _tasmota_request(host, f"{command} {value}")
        actual = result.get(command, result.get("POWER", ""))

        return f"Relais {relay} wurde auf {'AN' if actual.upper() == 'ON' else 'AUS'} gesetzt."
    except Exception as e:
        logger.error("Fehler beim Schalten des Tasmota-Relais: %s", e)
        return f"Fehler: {e}"


@tool
async def get_tasmota_sensors(connection_id: str = "") -> Dict:
    """
    Ruft alle verfügbaren Sensor-Daten eines Tasmota-Geräts ab.
    Einschließlich Temperatur, Feuchtigkeit, Luftdruck, Leistung, Strom, Spannung.
    Benutze dieses Tool, um Messwerte wie Temperatur oder Stromverbrauch zu erhalten.
    Use this tool to get sensor readings like temperature, humidity, or power consumption.
    """
    try:
        host = await _get_tasmota_host(connection_id)
        if not host:
            raise ValueError("Keine Tasmota-Host-Adresse konfiguriert.")

        result = await _tasmota_request(host, "StatusSNS")
        sensors = result.get("StatusSNS", {})

        data = {}
        for key, val in sensors.items():
            if isinstance(val, dict):
                data.update(val)
            else:
                data[key] = val

        return {
            "temperature": data.get("Temperature"),
            "humidity": data.get("Humidity"),
            "pressure": data.get("Pressure"),
            "power": data.get("Power"),
            "current": data.get("Current"),
            "voltage": data.get("Voltage"),
            "energy_today": data.get("ENERGY", {}).get("Today") if isinstance(data.get("ENERGY"), dict) else None,
            "energy_yesterday": data.get("ENERGY", {}).get("Yesterday") if isinstance(data.get("ENERGY"), dict) else None,
            "raw": result,
        }
    except Exception as e:
        logger.error("Fehler beim Abrufen der Sensor-Daten: %s", e)
        return {"error": str(e)}


@tool
async def get_tasmota_wifi_info(connection_id: str = "") -> Dict:
    """
    Ruft WLAN-Informationen eines Tasmota-Geräts ab (SSID, RSSI, Signal in dBm).
    Benutze dieses Tool, um die WLAN-Qualität des Geräts zu überprüfen.
    Use this tool to check the WiFi signal strength of the device.
    """
    try:
        host = await _get_tasmota_host(connection_id)
        if not host:
            raise ValueError("Keine Tasmota-Host-Adresse konfiguriert.")

        result = await _tasmota_request(host, "Status 5")
        status5 = result.get("StatusNET", {})

        return {
            "hostname": status5.get("Hostname", ""),
            "ip": status5.get("IPAddress", ""),
            "ssid": status5.get("SSId", ""),
            "rssi": status5.get("RSSI", 0),
            "signal_dbm": status5.get("Signal", 0),
        }
    except Exception as e:
        logger.error("Fehler beim Abrufen der WLAN-Info: %s", e)
        return {"error": str(e)}


@tool
async def send_tasmota_command(command: str, connection_id: str = "") -> Dict:
    """
    Sendet einen beliebigen Tasmota-Befehl an das Gerät.
    Nutze dies für fortgeschrittene Befehle wie Restart, Reset, Rule-Ausführung.
    Use this tool to send custom Tasmota commands (e.g., Restart, Reset).
    """
    try:
        host = await _get_tasmota_host(connection_id)
        if not host:
            raise ValueError("Keine Tasmota-Host-Adresse konfiguriert.")

        result = await _tasmota_request(host, command)
        return {
            "command": command,
            "result": result,
            "success": True,
        }
    except Exception as e:
        logger.error("Fehler beim Senden des Tasmota-Befehls: %s", e)
        return {
            "command": command,
            "error": str(e),
            "success": False,
        }
