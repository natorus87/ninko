"""
Tasmota Modul – Pydantic Schemas für API-Antworten.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class TasmotaStatus(BaseModel):
    """Allgemeiner Status eines Tasmota-Geräts."""
    hostname: str
    ip_address: str
    uptime: int
    load: float
    wifi_rssi: int


class TasmotaPower(BaseModel):
    """Power-Status der Relais."""
    power1: Optional[bool] = None
    power2: Optional[bool] = None
    power3: Optional[bool] = None
    power4: Optional[bool] = None


class TasmotaSensor(BaseModel):
    """Sensor-Daten (Temperatur, Feuchtigkeit, etc.)."""
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    pressure: Optional[float] = None
    power: Optional[float] = None
    current: Optional[float] = None
    voltage: Optional[float] = None


class TasmotaDevice(BaseModel):
    """Vollständiges Tasmota-Gerät mit allen Daten."""
    host: str
    name: str
    model: Optional[str] = None
    firmware_version: Optional[str] = None
    online: bool
    power: Optional[TasmotaPower] = None
    sensor: Optional[TasmotaSensor] = None
    wifi_rssi: Optional[int] = None


class TasmotaCommandResult(BaseModel):
    """Ergebnis eines Tasmota-Befehls."""
    command: str
    result: Dict[str, Any]
    success: bool
