"""Tasmota module — LangGraph @tool functions."""

from __future__ import annotations

import logging
import os
import asyncio
from typing import Dict, List

import httpx
from langchain_core.tools import tool

from core.connections import ConnectionManager
from agents.base_agent import _t

logger = logging.getLogger("ninko.modules.tasmota.tools")


async def _get_tasmota_host(connection_id: str = "") -> str:
    """
    Helper: loads the host address from ConnectionManager or environment variables.
    """
    if connection_id:
        conn = await ConnectionManager.get_connection("tasmota", connection_id)
        if not conn:
            raise ValueError(f"Tasmota connection with ID '{connection_id}' not found.")
    else:
        conn = await ConnectionManager.get_default_connection("tasmota")

    if conn:
        return conn.config.get("host", "")

    return os.environ.get("TASMOTA_HOST", "")


async def _tasmota_request(host: str, command: str, timeout: float = 5.0) -> Dict:
    """
    Sends an HTTP command to a Tasmota device.
    Tasmota API: http://<host>/cm?cmnd=<command>
    """
    if not host:
        raise ValueError("No Tasmota host address provided.")

    url = f"http://{host}/cm?cmnd={command}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()


@tool
async def get_tasmota_status(connection_id: str = "") -> Dict:
    """
    Retrieves the general status of a Tasmota device (hostname, IP, uptime, firmware, model).
    Use this tool to get general information about a Tasmota device.
    """
    try:
        host = await _get_tasmota_host(connection_id)
        if not host:
            raise ValueError(
                _t(
                    de="Keine Tasmota-Verbindung konfiguriert. Bitte im Dashboard unter Einstellungen → Modul → Zahnrad eine Verbindung anlegen, oder die Env-Variable TASMOTA_HOST setzen.",
                    en="No Tasmota connection configured. Please create a connection in the dashboard under Settings → Module → gear icon, or set the environment variable TASMOTA_HOST.",
                    fr="Aucune connexion Tasmota configurée. Veuillez créer une connexion dans le tableau de bord sous Paramètres → Module → icône d'engrenage, ou définir la variable d'environnement TASMOTA_HOST.",
                    es="No hay conexión Tasmota configurada. Por favor cree una conexión en el panel bajo Configuración → Módulo → icono de engranaje, o establezca la variable de entorno TASMOTA_HOST.",
                    it="Nessuna connessione Tasmota configurata. Per favore crea una connessione nel cruscotto sotto Impostazioni → Modulo → icona ingranaggio, o imposta la variabile di ambiente TASMOTA_HOST.",
                    nl="Geen Tasmota-verbinding geconfigureerd. Maak een verbinding aan in het dashboard onder Instellingen → Module → tandwielpictogram, of stel de omgevingsvariabele TASMOTA_HOST in.",
                    pl="Nie skonfigurowano połączenia Tasmota. Utwórz połączenie w panelu w sekcji Ustawienia → Moduł → ikona koła zębatego lub ustaw zmienną środowiskową TASMOTA_HOST.",
                    pt="Nenhuma conexão Tasmota configurada. Por favor crie uma conexão no painel em Configurações → Módulo → ícone de engrenagem, ou defina a variável de ambiente TASMOTA_HOST.",
                    ja="Tasmota接続が設定されていません。ダッシュボードで設定→モジュール→歯車アイコンから接続を作成するか、環境変数TASMOTA_HOSTを設定してください。",
                    zh="未配置Tasmota连接。请在仪表板中的设置→模块→齿轮图标下创建连接，或设置环境变量TASMOTA_HOST。",
                )
            )

        # Fetch Status + Status 2 (firmware) in parallel
        status_result, fw_result = await asyncio.gather(
            _tasmota_request(host, "Status"),
            _tasmota_request(host, "Status 2"),
        )
        status = status_result.get("Status", {})
        fw = fw_result.get("StatusFWR", {})

        friendly = status.get("FriendlyName", [])
        wifi = status.get("Wifi", {})

        return {
            "device_name": status.get("DeviceName", ""),
            "friendly_name": friendly[0]
            if isinstance(friendly, list) and friendly
            else "",
            "hostname": status.get("Hostname", ""),
            "ip_address": status.get("IPAddress", ""),
            "uptime": status.get("Uptime", ""),
            "module_id": status.get("Module", 0),
            "firmware": fw.get("Version", ""),
            "hardware": fw.get("Hardware", ""),
            "wifi_rssi": wifi.get("RSSI", 0) if isinstance(wifi, dict) else 0,
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.error("Failed to retrieve Tasmota status: %s", e)
        return {"error": str(e)}


@tool
async def get_tasmota_power(connection_id: str = "") -> Dict:
    """
    Retrieves the power status of all relays on a Tasmota device.
    Use this tool to check which switches are on or off.
    """
    try:
        host = await _get_tasmota_host(connection_id)
        if not host:
            raise ValueError(
                _t(
                    de="Keine Tasmota-Host-Adresse konfiguriert.",
                    en="No Tasmota host address configured.",
                    fr="Aucune adresse hôte Tasmota configurée.",
                    es="No hay dirección de host Tasmota configurada.",
                    it="Nessun indirizzo host Tasmota configurato.",
                    nl="Geen Tasmota-hostadres geconfigureerd.",
                    pl="Nie skonfigurowano adresu hosta Tasmota.",
                    pt="Nenhum endereço de host Tasmota configurado.",
                    ja="Tasmotaホストアドレスが設定されていません。",
                    zh="未配置Tasmota主机地址。",
                )
            )

        result = await _tasmota_request(host, "Power")
        # Single-relay: {"POWER": "ON"}, Multi-relay: {"POWER1": "ON", "POWER2": "OFF"}
        relays = {}
        for key, val in result.items():
            if key.startswith("POWER"):
                if isinstance(val, str):
                    relays[key] = val.upper() == "ON"
        # Also check bare "POWER" key for single-relay
        if "POWER" in result and isinstance(result["POWER"], str):
            relays["POWER"] = result["POWER"].upper() == "ON"

        return {"relays": relays, "raw": result}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.error("Failed to retrieve Tasmota power status: %s", e)
        return {"error": str(e)}


@tool
async def set_tasmota_power(
    state: bool, relay: int = 1, connection_id: str = ""
) -> str:
    """
    Switches a relay on a Tasmota device on or off.
    state: True = on, False = off.
    relay: relay number (1-4), default is 1.
    Use this tool to turn switches or outlets on or off.
    German: Gerät/Relais einschalten, ausschalten or schalten.
    """
    try:
        host = await _get_tasmota_host(connection_id)
        if not host:
            return _t(
                de="Fehler: Keine Tasmota-Host-Adresse konfiguriert.",
                en="Error: No Tasmota host address configured.",
                fr="Erreur: Aucune adresse hôte Tasmota configurée.",
                es="Error: No hay dirección de host Tasmota configurada.",
                it="Errore: Nessun indirizzo host Tasmota configurato.",
                nl="Fout: Geen Tasmota-hostadres geconfigureerd.",
                pl="Błąd: Nie skonfigurowano adresu hosta Tasmota.",
                pt="Erro: Nenhum endereço de host Tasmota configurado.",
                ja="エラー：Tasmotaホストアドレスが設定されていません。",
                zh="错误：未配置Tasmota主机地址。",
            )

        command = f"Power{relay}" if relay > 1 else "Power"
        value = "ON" if state else "OFF"

        result = await _tasmota_request(host, f"{command} {value}")
        actual = result.get(command, result.get("POWER", ""))

        return _t(
            de=f"Relais {relay} wurde auf {'AN' if actual.upper() == 'ON' else 'AUS'} gesetzt.",
            en=f"Relay {relay} has been set to {'ON' if actual.upper() == 'ON' else 'OFF'}.",
            fr=f"Relais {relay} défini sur {'ON' if actual.upper() == 'ON' else 'OFF'}.",
            es=f"Relé {relay} establecido en {'ON' if actual.upper() == 'ON' else 'OFF'}.",
            it=f"Relè {relay} impostato su {'ON' if actual.upper() == 'ON' else 'OFF'}.",
            nl=f"Relais {relay} ingesteld op {'AAN' if actual.upper() == 'ON' else 'UIT'}.",
            pl=f"Przekaźnik {relay} ustawiony na {'WŁ' if actual.upper() == 'ON' else 'WYŁ'}.",
            pt=f"Relé {relay} definido como {'LIGADO' if actual.upper() == 'ON' else 'DESLIGADO'}.",
            ja=f"リレー {relay} を {'オン' if actual.upper() == 'ON' else 'オフ'} に設定しました。",
            zh=f"继电器 {relay} 已设置为 {'开' if actual.upper() == 'ON' else '关'}。",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.error("Failed to switch Tasmota relay: %s", e)
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
async def get_tasmota_sensors(connection_id: str = "") -> Dict:
    """
    Retrieves all available sensor data from a Tasmota device.
    Includes temperature, humidity, pressure, power, current, voltage.
    Use this tool to get sensor readings like temperature, humidity, or power consumption.
    """
    try:
        host = await _get_tasmota_host(connection_id)
        if not host:
            raise ValueError(
                _t(
                    de="Keine Tasmota-Host-Adresse konfiguriert.",
                    en="No Tasmota host address configured.",
                    fr="Aucune adresse hôte Tasmota configurée.",
                    es="No hay dirección de host Tasmota configurada.",
                    it="Nessun indirizzo host Tasmota configurato.",
                    nl="Geen Tasmota-hostadres geconfigureerd.",
                    pl="Nie skonfigurowano adresu hosta Tasmota.",
                    pt="Nenhum endereço de host Tasmota configurado.",
                    ja="Tasmotaホストアドレスが設定されていません。",
                    zh="未配置Tasmota主机地址。",
                )
            )

        result = await _tasmota_request(host, "StatusSNS")
        sensors = result.get("StatusSNS", {})

        # Flatten top-level dicts (e.g. "DHT11": {"Temperature": 22})
        # but keep track of nested dicts that need special handling (ENERGY)
        energy_data = {}
        flat = {}
        for key, val in sensors.items():
            if key == "ENERGY" and isinstance(val, dict):
                energy_data = val
            elif isinstance(val, dict):
                flat.update(val)
            else:
                flat[key] = val

        return {
            "temperature": flat.get("Temperature"),
            "humidity": flat.get("Humidity"),
            "pressure": flat.get("Pressure"),
            "power": flat.get("Power"),
            "current": flat.get("Current"),
            "voltage": flat.get("Voltage"),
            "energy_today": energy_data.get("Today"),
            "energy_yesterday": energy_data.get("Yesterday"),
            "energy_power": energy_data.get("Power"),
            "energy_voltage": energy_data.get("Voltage"),
            "energy_current": energy_data.get("Current"),
            "raw": result,
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.error("Failed to retrieve Tasmota sensor data: %s", e)
        return {"error": str(e)}


@tool
async def get_tasmota_wifi_info(connection_id: str = "") -> Dict:
    """
    Retrieves WiFi information from a Tasmota device (SSID, RSSI, signal in dBm).
    Use this tool to check the WiFi signal strength of the device.
    """
    try:
        host = await _get_tasmota_host(connection_id)
        if not host:
            raise ValueError(
                _t(
                    de="Keine Tasmota-Host-Adresse konfiguriert.",
                    en="No Tasmota host address configured.",
                    fr="Aucune adresse hôte Tasmota configurée.",
                    es="No hay dirección de host Tasmota configurada.",
                    it="Nessun indirizzo host Tasmota configurato.",
                    nl="Geen Tasmota-hostadres geconfigureerd.",
                    pl="Nie skonfigurowano adresu hosta Tasmota.",
                    pt="Nenhum endereço de host Tasmota configurado.",
                    ja="Tasmotaホストアドレスが設定されていません。",
                    zh="未配置Tasmota主机地址。",
                )
            )

        result = await _tasmota_request(host, "Status 5")
        status5 = result.get("StatusNET", {})

        return {
            "hostname": status5.get("Hostname", ""),
            "ip": status5.get("IPAddress", ""),
            "ssid": status5.get("SSId", ""),
            "rssi": status5.get("RSSI", 0),
            "signal_dbm": status5.get("Signal", 0),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.error("Failed to retrieve Tasmota WiFi info: %s", e)
        return {"error": str(e)}


@tool
async def send_tasmota_command(command: str, connection_id: str = "") -> Dict:
    """
    Sends an arbitrary Tasmota command to the device.
    Use this tool to send custom Tasmota commands (e.g., Restart, Reset).
    """
    try:
        host = await _get_tasmota_host(connection_id)
        if not host:
            raise ValueError(
                _t(
                    de="Keine Tasmota-Host-Adresse konfiguriert.",
                    en="No Tasmota host address configured.",
                    fr="Aucune adresse hôte Tasmota configurée.",
                    es="No hay dirección de host Tasmota configurada.",
                    it="Nessun indirizzo host Tasmota configurato.",
                    nl="Geen Tasmota-hostadres geconfigureerd.",
                    pl="Nie skonfigurowano adresu hosta Tasmota.",
                    pt="Nenhum endereço de host Tasmota configurado.",
                    ja="Tasmotaホストアドレスが設定されていません。",
                    zh="未配置Tasmota主机地址。",
                )
            )

        result = await _tasmota_request(host, command)
        return {
            "command": command,
            "result": result,
            "success": True,
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.error("Failed to send Tasmota command: %s", e)
        return {
            "command": command,
            "error": str(e),
            "success": False,
        }


@tool
async def get_tasmota_group_devices(
    group_topic: str,
    connection_id: str = "",
) -> List[Dict]:
    """
    Get all devices in a Tasmota group (via MQTT or HTTP).
    Use this tool to list devices that share the same group topic.
    """
    try:
        host = await _get_tasmota_host(connection_id)
        if not host:
            return {"error": "No Tasmota host configured"}

        result = await _tasmota_request(host, f"Status 13")
        devices = result.get("StatusNET", {}).get("Friendly", [])

        return [
            {
                "index": i,
                "name": name,
                "topic": f"{group_topic}_{i + 1}" if i > 0 else group_topic,
            }
            for i, name in enumerate(devices)
            if name
        ]

    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.error("Failed to get Tasmota group devices: %s", e)
        return [{"error": str(e)}]


@tool
async def set_tasmota_group_power(
    group_topic: str,
    power: int,
    connection_id: str = "",
) -> str:
    """
    Control all devices in a Tasmota group (Broadcast).
    Use this tool to turn all devices in a group on/off.
    German: Gruppe einschalten, ausschalten or schalten.
    """
    try:
        host = await _get_tasmota_host(connection_id)
        if not host:
            raise ValueError(
                _t(
                    de="Keine Tasmota-Host-Adresse konfiguriert.",
                    en="No Tasmota host address configured.",
                    fr="Aucune adresse hôte Tasmota configurée.",
                    es="No hay dirección de host Tasmota configurada.",
                    it="Nessun indirizzo host Tasmota configurato.",
                    nl="Geen Tasmota-hostadres geconfigureerd.",
                    pl="Nie skonfigurowano adresu hosta Tasmota.",
                    pt="Nenhum endereço de host Tasmota configurado.",
                    ja="Tasmotaホストアドレスが設定されていません。",
                    zh="未配置Tasmota主机地址。",
                )
            )

        command = f"GroupTopic {group_topic}"
        await _tasmota_request(host, command)

        command = f"Power{power}"
        await _tasmota_request(host, command)

        return _t(
            de=f"Gruppen-Befehl '{command}' an {group_topic} gesendet.",
            en=f"Group command '{command}' sent to {group_topic}.",
            fr=f"Commande de groupe '{command}' envoyée à {group_topic}.",
            es=f"Comando de grupo '{command}' enviado a {group_topic}.",
            it=f"Comando di gruppo '{command}' inviato a {group_topic}.",
            nl=f"Groepsopdracht '{command}' verzonden naar {group_topic}.",
            pl=f"Polecenie grupowe '{command}' wysłane do {group_topic}.",
            pt=f"Comando de grupo '{command}' enviado para {group_topic}.",
            ja=f"グループコマンド '{command}' を {group_topic} に送信しました。",
            zh=f"群组命令 '{command}' 已发送到 {group_topic}。",
        )

    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.error("Failed to send Tasmota group command: %s", e)
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
async def discover_tasmota_devices(
    mqtt_broker: str = "",
    connection_id: str = "",
) -> List[Dict]:
    """
    Discover Tasmota devices via MQTT (if broker configured).
    Use this tool to find all Tasmota devices on the network.
    """
    try:
        host = await _get_tasmota_host(connection_id)
        if not host:
            return {"error": "No Tasmota host configured"}

        result = await _tasmota_request(host, "Status 11")

        devices = []
        for idx, dev in enumerate(result.get("StatusNET", {}).get("MqttDiscovery", [])):
            devices.append(
                {
                    "index": idx,
                    "topic": dev.get("Topic", ""),
                    "name": dev.get("Name", ""),
                    "model": dev.get("Model", ""),
                    "ip": dev.get("IP", ""),
                }
            )

        return (
            devices
            if devices
            else [
                {
                    "info": "No MQTT discovery results. Ensure MQTT is configured on devices."
                }
            ]
        )

    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.error("Failed to discover Tasmota devices: %s", e)
        return [{"error": str(e)}]


@tool
async def control_tasmota_device(
    device_topic: str,
    command: str,
    connection_id: str = "",
) -> str:
    """
    Control a specific Tasmota device by its topic.
    Use this tool to control a specific device (Power, Dimmer, etc.).
    """
    try:
        host = await _get_tasmota_host(connection_id)
        if not host:
            raise ValueError(
                _t(
                    de="Keine Tasmota-Host-Adresse konfiguriert.",
                    en="No Tasmota host address configured.",
                    fr="Aucune adresse hôte Tasmota configurée.",
                    es="No hay dirección de host Tasmota configurada.",
                    it="Nessun indirizzo host Tasmota configurato.",
                    nl="Geen Tasmota-hostadres geconfigureerd.",
                    pl="Nie skonfigurowano adresu hosta Tasmota.",
                    pt="Nenhum endereço de host Tasmota configurado.",
                    ja="Tasmotaホストアドレスが設定されていません。",
                    zh="未配置Tasmota主机地址。",
                )
            )

        full_command = f"cmnd/{device_topic}/{command}"
        result = await _tasmota_request(host, full_command)

        return _t(
            de=f"Befehl an {device_topic}: {command} -> {result}",
            en=f"Command to {device_topic}: {command} -> {result}",
            fr=f"Commande à {device_topic}: {command} -> {result}",
            es=f"Comando a {device_topic}: {command} -> {result}",
            it=f"Comando a {device_topic}: {command} -> {result}",
            nl=f"Opdracht naar {device_topic}: {command} -> {result}",
            pl=f"Polecenie do {device_topic}: {command} -> {result}",
            pt=f"Comando para {device_topic}: {command} -> {result}",
            ja=f"{device_topic} へのコマンド: {command} -> {result}",
            zh=f"发送到 {device_topic} 的命令: {command} -> {result}",
        )

    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.error("Failed to control Tasmota device: %s", e)
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
