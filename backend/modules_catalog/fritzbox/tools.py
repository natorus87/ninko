import logging
import asyncio
import os
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool
from pydantic import ValidationError

from agents.base_agent import _t
from .schemas import (
    FritzDevice,
    FritzWanStatus,
    FritzBandwidth,
    FritzWlanStatus,
    FritzSmartHomeDevice,
    FritzCallEntry,
    FritzSystemInfo,
)

logger = logging.getLogger("ninko.modules.fritzbox")

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
        host = conn_data.config.get(
            "host", conn_data.config.get("FRITZBOX_HOST", "192.168.178.1")
        )
        user = conn_data.config.get("user", conn_data.config.get("FRITZBOX_USER", ""))
        vault = get_vault()
        pwd_key = conn_data.vault_keys.get("password") or conn_data.vault_keys.get(
            "FRITZBOX_PASSWORD"
        )
        pwd = await vault.get_secret(pwd_key) if pwd_key else ""
    else:
        # Fallback: env var (for k8s / docker-compose without UI configuration)
        host = os.getenv("FRITZBOX_HOST", "192.168.178.1")
        user = os.getenv("FRITZBOX_USER", "")
        pwd = os.getenv("FRITZBOX_PASSWORD", "")

    def _create() -> object:
        try:
            return FritzConnection(address=host, user=user, password=pwd, timeout=5)
        except (RuntimeError, ValueError, TypeError, KeyError, OSError, ValidationError) as e:
            raise ValueError(
                _t(
                    de=f"FritzBox nicht erreichbar ({host}): {e}",
                    en=f"FritzBox unreachable ({host}): {e}",
                    fr=f"FritzBox inaccessible ({host}): {e}",
                    es=f"FritzBox no accesible ({host}): {e}",
                    it=f"FritzBox non raggiungibile ({host}): {e}",
                    nl=f"FritzBox niet bereikbaar ({host}): {e}",
                    pl=f"FritzBox nieosiągalny ({host}): {e}",
                    pt=f"FritzBox inacessível ({host}): {e}",
                    ja=f"FritzBox にアクセスできません（{host}）: {e}",
                    zh=f"FritzBox 无法访问（{host}）: {e}",
                )
            )

    return await asyncio.to_thread(_create)


# --- Network Tools ---


@tool
async def get_fritz_devices(connection_id: str = "") -> List[Dict]:
    """Retrieve the list of all known devices (host, IP, MAC, online status)."""

    def _fetch(fc) -> object:
        from fritzconnection.lib.fritzhosts import FritzHosts

        fh = FritzHosts(fc)
        hosts = fh.get_hosts_info()
        results = []
        for h in hosts:
            results.append(
                FritzDevice(
                    name=h.get("name", "Unknown"),
                    ip=h.get("ip", ""),
                    mac=h.get("mac", ""),
                    status="Online" if h.get("status") else "Offline",
                    interface=h.get("interface_type", ""),
                ).model_dump()
            )
        return results

    try:
        fc = await _get_fc(connection_id)
        return await asyncio.to_thread(_fetch, fc)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ValidationError) as e:
        logger.error("FritzBox (get_fritz_devices) error: %s", e)
        return [{"error": str(e)}]


@tool
async def get_fritz_wan_status(connection_id: str = "") -> Dict:
    """Check WAN (internet) connection status and public IP."""

    def _fetch(fc) -> object:
        from fritzconnection.lib.fritzstatus import FritzStatus

        fs = FritzStatus(fc)
        return FritzWanStatus(
            connected=fs.is_connected,
            ip_address=getattr(fs, "external_ip", None),
            uptime=None,
        ).model_dump()

    try:
        fc = await _get_fc(connection_id)
        return await asyncio.to_thread(_fetch, fc)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ValidationError) as e:
        logger.error("FritzBox (get_fritz_wan_status) error: %s", e)
        return {"error": str(e)}


@tool
async def get_fritz_bandwidth(connection_id: str = "") -> Dict:
    """Determine current bandwidth usage in bit/s."""

    def _fetch(fc) -> object:
        # Try to get transmission rate first, if available on newer fritzconnection
        # WANCommonInterfaceConfig1 / GetAddonInfos is often deprecated or blocked
        try:
            from fritzconnection.lib.fritzstatus import FritzStatus

            fs = FritzStatus(fc)
            if hasattr(fs, "transmission_rate"):
                return FritzBandwidth(
                    ds_current=fs.transmission_rate[1] if fs.transmission_rate else 0,
                    us_current=fs.transmission_rate[0] if fs.transmission_rate else 0,
                ).model_dump()
        except (ImportError, AttributeError, RuntimeError, ValueError, TypeError, OSError):
            pass

        try:
            result = fc.call_action("WANCommonInterfaceConfig1", "GetAddonInfos")
            return FritzBandwidth(
                ds_current=result.get("NewByteReceiveRate", 0) * 8,  # byte/s to bit/s
                us_current=result.get("NewByteSendRate", 0) * 8,
            ).model_dump()
        except (RuntimeError, ValueError, TypeError, KeyError, OSError, ValidationError):
            return FritzBandwidth(ds_current=0, us_current=0).model_dump()

    try:
        fc = await _get_fc(connection_id)
        return await asyncio.to_thread(_fetch, fc)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ValidationError) as e:
        logger.error("FritzBox (get_fritz_bandwidth) error: %s", e)
        return {"error": str(e)}


# --- WLAN Tools ---


@tool
async def get_fritz_wlan_status(connection_id: str = "") -> List[Dict]:
    """Determine status of all WLAN networks (2.4GHz, 5GHz, guest)."""

    def _fetch(fc) -> object:
        from fritzconnection.lib.fritzwlan import FritzWLAN

        networks = []
        # Normally there are service 1 (2.4GHz), 2 (5GHz), 3 (guest)
        for i in range(1, 4):
            try:
                fw = FritzWLAN(fc, service=i)
                ssid = fw.ssid
                networks.append(
                    FritzWlanStatus(
                        enabled=fw.is_enabled, ssid=ssid, channel=fw.channel
                    ).model_dump()
                )
            except (RuntimeError, ValueError, TypeError, KeyError, OSError, ValidationError):
                pass  # Service 3 (guest) may not be supported by the model
        return networks

    try:
        fc = await _get_fc(connection_id)
        return await asyncio.to_thread(_fetch, fc)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ValidationError) as e:
        logger.error("FritzBox (get_fritz_wlan_status) error: %s", e)
        return [{"error": str(e)}]


@tool
async def set_fritz_wlan_state(
    state: bool, service: int = 1, connection_id: str = ""
) -> str:
    """Enable or disable WLAN.

    Use for 'WLAN aktivieren/deaktivieren' or 'WLAN einschalten/ausschalten'.
    service=1 (2.4GHz), service=2 (5GHz), service=3 (guest).
    """

    def _exec(fc) -> object:
        fc.call_action(f"WLANConfiguration:{service}", "SetEnable", Enable=int(state))
        return _t(
            de=f"WLAN Service {service} wurde {'aktiviert' if state else 'deaktiviert'}.",
            en=f"WLAN service {service} has been {'enabled' if state else 'disabled'}.",
            fr=f"Service WLAN {service} a été {'activé' if state else 'désactivé'}.",
            es=f"Servicio WLAN {service} ha sido {'habilitado' if state else 'deshabilitado'}.",
            it=f"Servizio WLAN {service} è stato {'abilitato' if state else 'disabilitato'}.",
            nl=f"WLAN-service {service} is {'geactiveerd' if state else 'gedeactiveerd'}.",
            pl=f"Usługa WLAN {service} została {'włączona' if state else 'wyłączona'}.",
            pt=f"Serviço WLAN {service} foi {'ativado' if state else 'desativado'}.",
            ja=f"WLANサービス {service} が{'有効' if state else '無効'}になりました。",
            zh=f"WLAN服务 {service} 已{'启用' if state else '禁用'}。",
        )

    try:
        fc = await _get_fc(connection_id)
        return await asyncio.to_thread(_exec, fc)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ValidationError) as e:
        logger.error("FritzBox (set_fritz_wlan_state) error: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


@tool
async def set_fritz_guest_wlan_state(state: bool, connection_id: str = "") -> str:
    """Enable or disable the guest WLAN.

    Use for 'Gast-WLAN aktivieren/deaktivieren' or 'einschalten/ausschalten'.
    """
    # Guest WLAN is usually service 3
    return await set_fritz_wlan_state.ainvoke(
        {"state": state, "service": 3, "connection_id": connection_id}
    )


# --- Smart Home (AHA) Tools ---
# Requires pyfritzhome, optional if fritzconnection does not provide it natively.
# Since pyfritzhome is better for AHA, we use it as well.


async def _get_fh(connection_id: str = "") -> Any:
    """Helper to initialize pyfritzhome Fritzhome instance."""
    from core.connections import ConnectionManager
    from core.vault import get_vault
    from pyfritzhome import Fritzhome

    conn_data = await ConnectionManager.get_connection("fritzbox", connection_id)
    if not conn_data:
        conn_data = await ConnectionManager.get_default_connection("fritzbox")

    if conn_data:
        host = conn_data.config.get(
            "host", conn_data.config.get("FRITZBOX_HOST", "192.168.178.1")
        )
        user = conn_data.config.get("user", conn_data.config.get("FRITZBOX_USER", ""))
        vault = get_vault()
        pwd_key = conn_data.vault_keys.get("password") or conn_data.vault_keys.get(
            "FRITZBOX_PASSWORD"
        )
        pwd = await vault.get_secret(pwd_key) if pwd_key else ""
    else:
        # Fallback: env var (for k8s / docker-compose without UI configuration)
        host = os.getenv("FRITZBOX_HOST", "192.168.178.1")
        user = os.getenv("FRITZBOX_USER", "")
        pwd = os.getenv("FRITZBOX_PASSWORD", "")

    def _init() -> object:
        fh = Fritzhome(host, user, pwd)
        fh.login()
        return fh

    return await asyncio.to_thread(_init)


@tool
async def get_fritz_smarthome_devices(connection_id: str = "") -> List[Dict]:
    """List all known smart home devices (DECT switches, thermostats)."""

    def _fetch(fh) -> object:
        devs = fh.get_devices()
        results = []
        for d in devs:
            t_temp = d.target_temperature if d.has_thermostat else None
            if t_temp == 253.5:
                t_temp = "On"  # Max
            if t_temp == 254.0:
                t_temp = "Off"  # Min

            results.append(
                FritzSmartHomeDevice(
                    ain=d.ain,
                    name=d.name,
                    present=d.present,
                    device_type="thermostat" if d.has_thermostat else "switch",
                    switch_state=d.switch_state if d.has_switch else None,
                    temperature=d.temperature,
                    target_temperature=t_temp if isinstance(t_temp, float) else None,
                ).model_dump()
            )
        fh.logout()
        return results

    try:
        fh = await _get_fh(connection_id)
        return await asyncio.to_thread(_fetch, fh)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ValidationError) as e:
        logger.error("FritzBox (get_fritz_smarthome_devices) error: %s", e)
        return [{"error": str(e)}]


@tool
async def set_fritz_smarthome_switch(
    ain: str, state: bool, connection_id: str = ""
) -> str:
    """Switch a smart home device on or off by its AIN.

    Use for 'einschalten', 'ausschalten', or 'schalten'.
    """

    def _exec(fh) -> object:
        dev = fh.get_device_by_ain(ain)
        if state:
            dev.set_switch_state_on()
        else:
            dev.set_switch_state_off()
        fh.logout()
        return _t(
            de=f"Schalter '{dev.name}' auf {'AN' if state else 'AUS'} gesetzt.",
            en=f"Switch '{dev.name}' set to {'ON' if state else 'OFF'}.",
            fr=f"Interrupteur '{dev.name}' mis sur {'ON' if state else 'OFF'}.",
            es=f"Interruptor '{dev.name}' configurado en {'ENCENDIDO' if state else 'APAGADO'}.",
            it=f"Interruttore '{dev.name}' impostato su {'ON' if state else 'OFF'}.",
            nl=f"Schakelaar '{dev.name}' ingesteld op {'AAN' if state else 'UIT'}.",
            pl=f"Przełącznik '{dev.name}' ustawiony na {'WŁ' if state else 'WYŁ'}.",
            pt=f"Interruptor '{dev.name}' definido como {'LIGADO' if state else 'DESLIGADO'}.",
            ja=f"スイッチ '{dev.name}' を {'オン' if state else 'オフ'} に設定しました。",
            zh=f"开关 '{dev.name}' 已设置为 {'开' if state else '关'}。",
        )

    try:
        fh = await _get_fh(connection_id)
        return await asyncio.to_thread(_exec, fh)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ValidationError) as e:
        logger.error("FritzBox (set_fritz_smarthome_switch) error: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


@tool
async def set_fritz_smarthome_temperature(
    ain: str, temperature: float, connection_id: str = ""
) -> str:
    """Set the target temperature (in °C) of a radiator controller by its AIN.

    Use for 'Temperatur setzen' or 'Thermostat setzen'.
    """

    def _exec(fh) -> object:
        dev = fh.get_device_by_ain(ain)
        dev.set_target_temperature(temperature)
        fh.logout()
        return _t(
            de=f"Thermostat '{dev.name}' auf {temperature}°C gesetzt.",
            en=f"Thermostat '{dev.name}' set to {temperature}°C.",
            fr=f"Thermostat '{dev.name}' réglé à {temperature}°C.",
            es=f"Termostato '{dev.name}' configurado a {temperature}°C.",
            it=f"Termostato '{dev.name}' impostato a {temperature}°C.",
            nl=f"Thermostaat '{dev.name}' ingesteld op {temperature}°C.",
            pl=f"Termostat '{dev.name}' ustawiony na {temperature}°C.",
            pt=f"Termostato '{dev.name}' definido para {temperature}°C.",
            ja=f"サーモスタット '{dev.name}' を {temperature}°C に設定しました。",
            zh=f"恒温器 '{dev.name}' 已设置为 {temperature}°C。",
        )

    try:
        fh = await _get_fh(connection_id)
        return await asyncio.to_thread(_exec, fh)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ValidationError) as e:
        logger.error("FritzBox (set_fritz_smarthome_temperature) error: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


# --- System Tools ---


@tool
async def get_fritz_call_list(connection_id: str = "") -> List[Dict]:
    """Retrieve the FritzBox call log."""

    def _fetch(fc) -> object:
        from fritzconnection.lib.fritzcall import FritzCall

        fcall = FritzCall(fc)
        calls = fcall.get_calls()
        results = []
        # calls is a list of dictionaries with Type, Caller, Called, Date, Duration etc.
        # Limit to last 20 calls to not blow up context
        for idx, call in enumerate(calls[:20]):
            c_type = str(call.get("Type", "0"))
            results.append(
                FritzCallEntry(
                    id=str(idx),
                    type="Incoming"
                    if c_type == "1"
                    else "Missed"
                    if c_type == "2"
                    else "Outgoing"
                    if c_type == "3"
                    else "Unknown",
                    caller=call.get("Caller", ""),
                    called=call.get("Called", ""),
                    date=call.get("Date", ""),
                    duration=call.get("Duration", "0"),
                ).model_dump()
            )
        return results

    try:
        fc = await _get_fc(connection_id)
        return await asyncio.to_thread(_fetch, fc)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ValidationError) as e:
        logger.error("FritzBox (get_fritz_call_list) error: %s", e)
        return [{"error": str(e)}]


@tool
async def get_fritz_system_info(connection_id: str = "") -> Dict:
    """Retrieve the FritzBox model, firmware version and uptime."""

    def _fetch(fc) -> object:
        dev_info = fc.call_action("DeviceInfo1", "GetInfo")
        # Extract Uptime from GetInfo if possible, else fall back to SystemTime
        up_info = fc.call_action(
            "DeviceInfo1", "GetInfo", arguments=None
        )  # Sometimes UpTime is present
        uptime = up_info.get("NewUpTime", 0)

        return FritzSystemInfo(
            model=dev_info.get("NewModelName", "FritzBox"),
            firmware_version=dev_info.get("NewSoftwareVersion", "Unknown"),
            uptime=int(uptime),
        ).model_dump()

    try:
        fc = await _get_fc(connection_id)
        return await asyncio.to_thread(_fetch, fc)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ValidationError) as e:
        logger.error("FritzBox (get_fritz_system_info) error: %s", e)
        return {"error": str(e)}


@tool
async def reboot_fritzbox(connection_id: str = "") -> str:
    """Trigger a complete reboot/restart of the FritzBox.

    Use for 'FritzBox Neustart', 'neustarten', or 'neu starten'.
    """

    def _exec(fc) -> object:
        fc.call_action("DeviceConfig1", "Reboot")
        return _t(
            de="FritzBox Neustart initiiert. Router ist für ca. 3 Minuten offline.",
            en="FritzBox reboot initiated. Router will be offline for approximately 3 minutes.",
            fr="Redémarrage FritzBox initiated. Le routeur sera hors ligne pendant environ 3 minutes.",
            es="Reinicio de FritzBox iniciado. El router estará fuera de línea durante aproximadamente 3 minutos.",
            it="Riavvio FritzBox avviato. Il router sarà offline per circa 3 minuti.",
            nl="FritzBox herstart geïnitieerd. Router is ongeveer 3 minuten offline.",
            pl="Restart FritzBox zainicjowany. Router będzie offline przez około 3 minuty.",
            pt="Reinício do FritzBox iniciado. O router ficará offline por aproximadamente 3 minutos.",
            ja="FritzBoxの再起動を開始しました。路由器は3分程度オフラインになります。",
            zh="FritzBox重启已启动。路由器将在约3分钟内离线。",
        )

    try:
        fc = await _get_fc(connection_id)
        return await asyncio.to_thread(_exec, fc)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ValidationError) as e:
        logger.error("FritzBox (reboot_fritzbox) error: %s", e)
        return _t(
            de=f"Fehler beim Neustart: {e}",
            en=f"Error during reboot: {e}",
            fr=f"Erreur lors du redémarrage: {e}",
            es=f"Error durante el reinicio: {e}",
            it=f"Errore durante il riavvio: {e}",
            nl=f"Fout bij herstart: {e}",
            pl=f"Błąd podczas restartu: {e}",
            pt=f"Erro ao reiniciar: {e}",
            ja=f"再起動中のエラー: {e}",
            zh=f"重启时出错: {e}",
        )
