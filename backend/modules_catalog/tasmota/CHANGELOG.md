# Changelog

All notable changes to this module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.4] - 2026-06-10

### Fixed
- Health checks now use the authenticated tenant context when loading connections.
- Tasmota health checks now handle HTTP connection failures without uncaught errors.
- Tasmota host values with or without URL scheme are normalized before probing.

## [1.1.1] - 2026-04-06

### Added
- Initial release of Tasmota module
- Tasmota device control via HTTP REST API
- ESP8266/ESP32 device support
- Sonoff device compatibility
- Smart home switch control
- Smart plug control
- Relay control
- Sensor monitoring (temperature, humidity)
- Power consumption monitoring
- Smart meter support
- MQTT integration capabilities
- Dashboard integration with SVG icon

## Module Information

- **Name**: tasmota
- **Description**: Steuerung und Monitoring von Tasmota-Geräten (ESP8266/ESP32) via HTTP REST API
- **Author**: Ninko
