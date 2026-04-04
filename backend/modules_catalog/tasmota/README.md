# Tasmota Module

Control and monitor Tasmota (ESP8266/ESP32) devices over HTTP API.

## Features
- Device status and power state
- Power switching (including multi-relay support)
- Sensor and Wi-Fi information
- Raw command execution for advanced use cases

## Connection
Configure in **Settings -> Modules -> Tasmota**.

Typical fields:
- `host`
- optional auth fields (if your firmware requires them)

## Main Tools
- `get_tasmota_status`
- `get_tasmota_power`
- `set_tasmota_power`
- `get_tasmota_sensors`
- `get_tasmota_wifi_info`
- `send_tasmota_command`

## Safety
- `send_tasmota_command` is intentionally powerful; keep Safeguard enabled for this module.
