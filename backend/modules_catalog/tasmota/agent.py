"""Tasmota module — specialist agent."""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

from .tools import (
    control_tasmota_device,
    discover_tasmota_devices,
    get_tasmota_group_devices,
    get_tasmota_power,
    get_tasmota_sensors,
    get_tasmota_status,
    get_tasmota_wifi_info,
    send_tasmota_command,
    set_tasmota_group_power,
    set_tasmota_power,
)

logger = logging.getLogger("ninko.modules.tasmota.agent")

TASMOTA_SYSTEM_PROMPT = """You are Ninko's Tasmota specialist.

Capabilities:
- Control Tasmota devices (ESP8266/ESP32) via HTTP REST API
- Query sensor data (temperature, humidity, power, current, voltage)
- Switch relays and outlets
- Monitor WiFi status
- Multi-device management (group broadcast, device discovery via MQTT)
- Control individual devices by topic

Tool execution rules:
- Ask for the host address first if no connection is configured.
- Use the available Tasmota tools before answering live device questions.
- Use discovery or group-device tools when the target device is unclear.

Output format:
- For lists (Devices, Sensors): ALWAYS use Markdown tables
- Example: | Device | Status | Temperature | Power |
- NEVER return raw JSON or Python repr as the final answer
- Always include units for sensor values (°C, W, V, mA)
- Color-code on/off status when helpful

Behavior rules:
- Respond in clear, structured sentences

Safety and confirmation rules:
- Do not execute dangerous commands without confirmation.

Error handling:
- On errors, explain the problem and suggest a concrete next step."""


class TasmotaAgent(BaseAgent):
    """Tasmota specialist with Tasmota tools."""

    def __init__(self) -> None:
        """Initialize the Tasmota agent."""
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
                get_tasmota_group_devices,
                set_tasmota_group_power,
                discover_tasmota_devices,
                control_tasmota_device,
            ],
        )
