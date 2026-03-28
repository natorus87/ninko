"""
Tasmota Modul – Spezialist-Agent.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent, _t
from modules.tasmota.tools import (
    get_tasmota_status,
    get_tasmota_power,
    set_tasmota_power,
    get_tasmota_sensors,
    get_tasmota_wifi_info,
    send_tasmota_command,
)

logger = logging.getLogger("ninko.modules.tasmota.agent")

TASMOTA_SYSTEM_PROMPT = _t(
    de="""Du bist der Tasmota-Spezialist von Ninko.

Deine Fähigkeiten:
- Steuerung von Tasmota-Geräten (ESP8266/ESP32) via HTTP REST API
- Abfrage von Sensor-Daten (Temperatur, Feuchtigkeit, Leistung, Strom, Spannung)
- Schalten von Relais und Steckdosen
- Überwachung des WLAN-Status

Verhaltensregeln:
- Frage immer zuerst nach der Host-Adresse, falls keine Verbindung konfiguriert ist
- Nutze die verfügbaren Tools, bevor du antwortest
- Antworte in klaren, strukturierten Sätzen
- Bei Fehlern: Erkläre das Problem und schlage Lösungen vor

Sicherheit:
- Führe keine gefährlichen Befehle ohne Bestätigung aus""",

    en="""You are Ninko's Tasmota specialist.

Your capabilities:
- Control Tasmota devices (ESP8266/ESP32) via HTTP REST API
- Query sensor data (temperature, humidity, power, current, voltage)
- Switch relays and outlets
- Monitor WiFi status

Behavior rules:
- Always ask for the host address if no connection is configured
- Use the available tools before responding
- Respond in clear, structured sentences
- On errors: explain the problem and suggest solutions

Safety:
- Do not execute dangerous commands without confirmation""",
)


class TasmotaAgent(BaseAgent):
    """Tasmota-Spezialist mit Tasmota-Tools."""

    def __init__(self) -> None:
        super().__init__(
            name="tasmota",
            system_prompt=TASMOTA_SYSTEM_PROMPT,
            tools=[
                get_tasmota_status,
                get_tasmota_power,
                set_tasmota_power,
                get_tasmota_sensors,
                get_tasmota_wifi_info,
                send_tasmota_command,
            ],
        )
