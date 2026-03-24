import logging
import asyncio
import os
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from pydantic import ValidationError

from modules.fritzbox.schemas import (
    FritzDevice, FritzWanStatus, FritzBandwidth, FritzWlanStatus,
    FritzSmartHomeDevice, FritzCallEntry, FritzSystemInfo
)

logger = logging.getLogger("kumio.modules.fritzbox")

# --- Helper ---

async def _get_fc(connection_id: str = "") -> Any:
    """Helper to initialize and return a FritzConnection instance."""
    from core.connections import ConnectionManager
    from core.vault import get_vault
    from fritzconnection import FritzConnection

    conn_data = await ConnectionManager.get_connection("fritzbox", connection_id)
    if not conn_data:
        conn_data = await ConnectionManager.get_default_connection("fritzbox")

    if conn_data:
        host = conn_data.config.get("host", conn_data.config.get("FRITZBOX_HOST", "192.168.178.1"))
        user = conn_data.config.get("user", conn_data.config.get("FRITZBOX_USER", ""))
        vault = get_vault()
        pwd_key = conn_data.vault_keys.get("password") or conn_data.vault_keys.get("FRITZBOX_PASSWORD")
        pwd = await vault.get_secret(pwd_key) if pwd_key else ""
    else:
        # Fallback: Env-Var (für k8s / docker-compose ohne UI-Konfiguration)
        host = os.getenv("FRITZBOX_HOST", "192.168.178.1")
        user = os.getenv("FRITZBOX_USER", "")
        pwd = os.getenv("FRITZBOX_PASSWORD", "")

    def _create():
        try:
            return FritzConnection(address=host, user=user, password=pwd, timeout=5)
        except Exception as e:
            raise ValueError(f"FritzBox nicht erreichbar ({host}): {e}")

    return await asyncio.to_thread(_create)

# --- Network Tools ---

@tool
async def get_fritz_devices(connection_id: str = "") -> List[Dict]:
    """Holt die Liste aller bekannten Geräte (Host, IP, MAC, Online-Status)."""
    def _fetch(fc):
        from fritzconnection.lib.fritzhosts import FritzHosts
        fh = FritzHosts(fc)
        hosts = fh.get_hosts_info()
        results = []
        for h in hosts:
            results.append(FritzDevice(
                name=h.get("name", "Unknown"),
                ip=h.get("ip", ""),
                mac=h.get("mac", ""),
                status="Online" if h.get("status") else "Offline",
                interface=h.get("interface_type", "")
            ).model_dump())
        return results

    try:
        fc = await _get_fc(connection_id)
        return await asyncio.to_thread(_fetch, fc)
    except Exception as e:
        logger.error(f"FritzBox (get_fritz_devices) Error: {e}")
        return [{"error": str(e)}]

@tool
async def get_fritz_wan_status(connection_id: str = "") -> Dict:
    """Prüft den WAN (Internet) Verbindungsstatus und die öffentliche IP."""
    def _fetch(fc):
        from fritzconnection.lib.fritzstatus import FritzStatus
        fs = FritzStatus(fc)
        return FritzWanStatus(
            connected=fs.is_connected,
            ip_address=getattr(fs, 'external_ip', None),
            uptime=None
        ).model_dump()

    try:
        fc = await _get_fc(connection_id)
        return await asyncio.to_thread(_fetch, fc)
    except Exception as e:
        logger.error(f"FritzBox (get_fritz_wan_status) Error: {e}")
        return {"error": str(e)}

@tool
async def get_fritz_bandwidth(connection_id: str = "") -> Dict:
    """Ermittelt die aktuell genutzte Bandbreite in bit/s."""
    
    def _fetch(fc):
        # Try to get transmission rate first, if available on newer fritzconnection
        # WANCommonInterfaceConfig1 / GetAddonInfos is often deprecated or blocked
        try:
            from fritzconnection.lib.fritzstatus import FritzStatus
            fs = FritzStatus(fc)
            if hasattr(fs, 'transmission_rate'):
                return FritzBandwidth(
                    ds_current=fs.transmission_rate[1] if fs.transmission_rate else 0,
                    us_current=fs.transmission_rate[0] if fs.transmission_rate else 0
                ).model_dump()
        except:
            pass

        try:
            result = fc.call_action("WANCommonInterfaceConfig1", "GetAddonInfos")
            return FritzBandwidth(
                ds_current=result.get("NewByteReceiveRate", 0) * 8, # byte/s to bit/s
                us_current=result.get("NewByteSendRate", 0) * 8
            ).model_dump()
        except Exception:
            return FritzBandwidth(ds_current=0, us_current=0).model_dump()
        
    try:
        fc = await _get_fc(connection_id)
        return await asyncio.to_thread(_fetch, fc)
    except Exception as e:
        logger.error(f"FritzBox (get_fritz_bandwidth) Error: {e}")
        return {"error": str(e)}

# --- WLAN Tools ---

@tool
async def get_fritz_wlan_status(connection_id: str = "") -> List[Dict]:
    """Ermittelt den Status aller WLAN-Netze (2.4GHz, 5GHz, Gastzugang)."""
    
    def _fetch(fc):
        from fritzconnection.lib.fritzwlan import FritzWLAN
        networks = []
        # Normalerweise gibt es Service 1 (2.4GHz), 2 (5GHz), 3 (Gast)
        for i in range(1, 4):
            try:
                fw = FritzWLAN(fc, service=i)
                ssid = fw.ssid
                networks.append(FritzWlanStatus(
                    enabled=fw.is_enabled,
                    ssid=ssid,
                    channel=fw.channel
                ).model_dump())
            except Exception:
                pass # Möglicherweise wird Service 3 (Gast) nicht vom Modell unterstützt
        return networks
        
    try:
        fc = await _get_fc(connection_id)
        return await asyncio.to_thread(_fetch, fc)
    except Exception as e:
        logger.error(f"FritzBox (get_fritz_wlan_status) Error: {e}")
        return [{"error": str(e)}]

@tool
async def set_fritz_wlan_state(state: bool, service: int = 1, connection_id: str = "") -> str:
    """Aktiviert oder deaktiviert das WLAN. service=1 (2.4GHz), service=2 (5GHz), service=3 (Gast)."""
    
    def _exec(fc):
        fc.call_action(f"WLANConfiguration:{service}", "SetEnable", Enable=int(state))
        return f"WLAN Service {service} wurde {'aktiviert' if state else 'deaktiviert'}."
        
    try:
        fc = await _get_fc(connection_id)
        return await asyncio.to_thread(_exec, fc)
    except Exception as e:
        logger.error(f"FritzBox (set_fritz_wlan_state) Error: {e}")
        return f"Fehler: {e}"

@tool
async def set_fritz_guest_wlan_state(state: bool, connection_id: str = "") -> str:
    """Aktiviert oder deaktiviert spezifisch das Gast-WLAN."""
    # Gast-WLAN ist meist Service 3
    return await set_fritz_wlan_state.ainvoke({"state": state, "service": 3, "connection_id": connection_id})

# --- Smart Home (AHA) Tools ---
# Benötigt pyfritzhome, optional, wenn fritzconnection es nicht nativ hergibt.
# Da pyfritzhome besser für AHA ist, holen wir es ebenfalls.

async def _get_fh(connection_id: str = "") -> Any:
    """Helper to initialize pyfritzhome Fritzhome instance."""
    from core.connections import ConnectionManager
    from core.vault import get_vault
    from pyfritzhome import Fritzhome

    conn_data = await ConnectionManager.get_connection("fritzbox", connection_id)
    if not conn_data:
        conn_data = await ConnectionManager.get_default_connection("fritzbox")

    if conn_data:
        host = conn_data.config.get("host", conn_data.config.get("FRITZBOX_HOST", "192.168.178.1"))
        user = conn_data.config.get("user", conn_data.config.get("FRITZBOX_USER", ""))
        vault = get_vault()
        pwd_key = conn_data.vault_keys.get("password") or conn_data.vault_keys.get("FRITZBOX_PASSWORD")
        pwd = await vault.get_secret(pwd_key) if pwd_key else ""
    else:
        # Fallback: Env-Var (für k8s / docker-compose ohne UI-Konfiguration)
        host = os.getenv("FRITZBOX_HOST", "192.168.178.1")
        user = os.getenv("FRITZBOX_USER", "")
        pwd = os.getenv("FRITZBOX_PASSWORD", "")

    def _init():
        fh = Fritzhome(host, user, pwd)
        fh.login()
        return fh

    return await asyncio.to_thread(_init)

@tool
async def get_fritz_smarthome_devices(connection_id: str = "") -> List[Dict]:
    """Listet alle bekannten Smart-Home-Geräte (DECT Schalter, Thermostate) auf."""
    
    def _fetch(fh):
        devs = fh.get_devices()
        results = []
        for d in devs:
            t_temp = d.target_temperature if d.has_thermostat else None
            if t_temp == 253.5: t_temp = "On" # Max
            if t_temp == 254.0: t_temp = "Off" # Min
            
            results.append(FritzSmartHomeDevice(
                ain=d.ain,
                name=d.name,
                present=d.present,
                device_type="thermostat" if d.has_thermostat else "switch",
                switch_state=d.switch_state if d.has_switch else None,
                temperature=d.temperature,
                target_temperature=t_temp if isinstance(t_temp, float) else None
            ).model_dump())
        fh.logout()
        return results
        
    try:
        fh = await _get_fh(connection_id)
        return await asyncio.to_thread(_fetch, fh)
    except Exception as e:
        logger.error(f"FritzBox (get_fritz_smarthome_devices) Error: {e}")
        return [{"error": str(e)}]

@tool
async def set_fritz_smarthome_switch(ain: str, state: bool, connection_id: str = "") -> str:
    """Schaltet ein Smart-Home-Gerät anhand seiner AIN ein oder aus."""
    def _exec(fh):
        dev = fh.get_device_by_ain(ain)
        if state:
            dev.set_switch_state_on()
        else:
            dev.set_switch_state_off()
        fh.logout()
        return f"Schalter '{dev.name}' auf {'AN' if state else 'AUS'} gesetzt."
        
    try:
        fh = await _get_fh(connection_id)
        return await asyncio.to_thread(_exec, fh)
    except Exception as e:
        logger.error(f"FritzBox (set_fritz_smarthome_switch) Error: {e}")
        return f"Fehler: {e}"

@tool
async def set_fritz_smarthome_temperature(ain: str, temperature: float, connection_id: str = "") -> str:
    """Setzt die Ziel-Temperatur (in °C) eines Heizkörperreglers anhand seiner AIN."""
    def _exec(fh):
        dev = fh.get_device_by_ain(ain)
        dev.set_target_temperature(temperature)
        fh.logout()
        return f"Thermostat '{dev.name}' auf {temperature}°C gesetzt."
        
    try:
        fh = await _get_fh(connection_id)
        return await asyncio.to_thread(_exec, fh)
    except Exception as e:
        logger.error(f"FritzBox (set_fritz_smarthome_temperature) Error: {e}")
        return f"Fehler: {e}"

# --- System Tools ---

@tool
async def get_fritz_call_list(connection_id: str = "") -> List[Dict]:
    """Holt die Anrufliste der FritzBox."""
    
    def _fetch(fc):
        from fritzconnection.lib.fritzcall import FritzCall
        fcall = FritzCall(fc)
        calls = fcall.get_calls()
        results = []
        # calls is a list of dictionaries with Type, Caller, Called, Date, Duration etc.
        # Limit to last 20 calls to not blow up context
        for idx, call in enumerate(calls[:20]):
            c_type = str(call.get("Type", "0"))
            results.append(FritzCallEntry(
                id=str(idx),
                type="Incoming" if c_type == "1" else "Missed" if c_type == "2" else "Outgoing" if c_type == "3" else "Unknown",
                caller=call.get("Caller", ""),
                called=call.get("Called", ""),
                date=call.get("Date", ""),
                duration=call.get("Duration", "0")
            ).model_dump())
        return results
        
    try:
        fc = await _get_fc(connection_id)
        return await asyncio.to_thread(_fetch, fc)
    except Exception as e:
        logger.error(f"FritzBox (get_fritz_call_list) Error: {e}")
        return [{"error": str(e)}]

@tool
async def get_fritz_system_info(connection_id: str = "") -> Dict:
    """Holt das FritzBox Modell und Firmware-Version sowie die Betriebszeit."""
    
    def _fetch(fc):
        dev_info = fc.call_action("DeviceInfo1", "GetInfo")
        # Extract Uptime from GetInfo if possible, else fall back to SystemTime
        up_info = fc.call_action("DeviceInfo1", "GetInfo", arguments=None) # Sometimes UpTime is present
        uptime = up_info.get("NewUpTime", 0)
        
        return FritzSystemInfo(
            model=dev_info.get("NewModelName", "FritzBox"),
            firmware_version=dev_info.get("NewSoftwareVersion", "Unknown"),
            uptime=int(uptime)
        ).model_dump()
        
    try:
        fc = await _get_fc(connection_id)
        return await asyncio.to_thread(_fetch, fc)
    except Exception as e:
        logger.error(f"FritzBox (get_fritz_system_info) Error: {e}")
        return {"error": str(e)}

@tool
async def reboot_fritzbox(connection_id: str = "") -> str:
    """Löst einen kompletten Neustart der FritzBox aus."""
    
    def _exec(fc):
        fc.call_action("DeviceConfig1", "Reboot")
        return "FritzBox Neustart initiiert. Router ist für ca. 3 Minuten offline."
        
    try:
        fc = await _get_fc(connection_id)
        return await asyncio.to_thread(_exec, fc)
    except Exception as e:
        logger.error(f"FritzBox (reboot_fritzbox) Error: {e}")
        return f"Fehler beim Neustart: {e}"
