from pydantic import BaseModel, Field
from typing import List, Optional

class FritzDevice(BaseModel):
    name: str = Field(..., description="Hostname of the device")
    ip: str = Field(..., description="IP address")
    mac: str = Field(..., description="MAC address")
    status: str = Field(..., description="Connection status (Online/Offline)")
    interface: str = Field("", description="Connection type (Ethernet/WiFi)")

class FritzWanStatus(BaseModel):
    connected: bool = Field(..., description="WAN Connection Status")
    ip_address: Optional[str] = Field(None, description="External IPv4 Address")
    uptime: Optional[int] = Field(None, description="Uptime of connection in seconds")

class FritzBandwidth(BaseModel):
    ds_current: int = Field(..., description="Current downstream bandwidth (bps)")
    us_current: int = Field(..., description="Current upstream bandwidth (bps)")

class FritzWlanStatus(BaseModel):
    enabled: bool = Field(..., description="Is WLAN enabled")
    ssid: str = Field(..., description="Network SSID")
    channel: int = Field(..., description="Current Channel")

class FritzSmartHomeDevice(BaseModel):
    ain: str = Field(..., description="Actor Identification Number")
    name: str = Field(..., description="Device name")
    present: bool = Field(..., description="Is device reachable")
    device_type: str = Field(..., description="Type of the device (switch, thermostat, etc.)")
    switch_state: Optional[bool] = Field(None, description="On/Off state if switch")
    temperature: Optional[float] = Field(None, description="Current temperature if available")
    target_temperature: Optional[float] = Field(None, description="Target temperature if thermostat")

class FritzCallEntry(BaseModel):
    id: str
    type: str = Field(..., description="Type of call (1: incoming, 2: missed, 3: outgoing)")
    caller: str
    called: str
    date: str
    duration: str

class FritzSystemInfo(BaseModel):
    model: str = Field(..., description="FritzBox Model Name")
    firmware_version: str = Field(..., description="Installed Firmware (FRITZ!OS)")
    uptime: int = Field(..., description="Device uptime in seconds")
