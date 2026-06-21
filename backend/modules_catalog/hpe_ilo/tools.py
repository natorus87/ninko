"""
HPE iLO Module — LangGraph @tool functions.
Supports both iLO4 and iLO5 REST API.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import aiohttp
from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.hpe_ilo.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """
    Helper: loads config and secrets from ConnectionManager.
    """
    if connection_id:
        conn = await ConnectionManager.get_connection("hpe_ilo", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"HPE iLO-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"HPE iLO connection with ID '{connection_id}' not found.",
                    fr=f"Connexion HPE iLO avec l'ID '{connection_id}' introuvable.",
                    es=f"Conexión HPE iLO con ID '{connection_id}' no encontrada.",
                    it=f"Connessione HPE iLO con ID '{connection_id}' non trovata.",
                    nl=f"HPE iLO-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie HPE iLO z ID '{connection_id}' nie znaleziono.",
                    pt=f"Conexão HPE iLO com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のHPE iLO接続が見つかりません。",
                    zh=f"未找到ID为'{connection_id}'的HPE iLO连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("hpe_ilo")

    if conn:
        base_url = conn.config.get("url", "")
        user = conn.config.get("user", "Administrator")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("ILO_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)
        if not password:
            password = os.environ.get("ILO_PASSWORD", "")
        return {"base_url": base_url, "user": user, "password": password}

    base_url = os.environ.get("ILO_HOST", "")
    user = os.environ.get("ILO_USER", "Administrator")
    vault = get_vault()
    password = await vault.get_secret("ILO_PASSWORD")

    if not base_url:
        raise ValueError(
            _t(
                de="Keine HPE iLO-Verbindung konfiguriert.",
                en="No HPE iLO connection configured.",
                fr="Aucune connexion HPE iLO configurée.",
                es="No hay conexión HPE iLO configurada.",
                it="Nessuna connessione HPE iLO configurata.",
                nl="Geen HPE iLO-verbinding geconfigureerd.",
                pl="Nie skonfigurowano połączenia HPE iLO.",
                pt="Nenhuma conexão HPE iLO configurada.",
                ja="HPE iLO接続が設定されていません。",
                zh="未配置HPE iLO连接。",
            )
        )

    return {"base_url": f"https://{base_url}", "user": user, "password": password}


async def _ilo_request(
    method: str, path: str, client: dict, json: Optional[dict] = None
) -> dict:
    """Make an authenticated request to iLO REST API."""
    base_url = client["base_url"].rstrip("/")
    url = f"{base_url}/rest/v1{path}"

    async with aiohttp.ClientSession(
        auth=aiohttp.BasicAuth(client["user"], client["password"]),
        timeout=aiohttp.ClientTimeout(total=30),
    ) as session:
        async with session.request(method, url, json=json, ssl=False) as resp:
            if resp.status == 204:
                return {"status": "OK"}
            resp.raise_for_status()
            return await resp.json()


# ═══════════════════════════════════════════════════════
# Read-only tools
# ═══════════════════════════════════════════════════════


@tool
async def get_ilo_info(connection_id: str = "") -> str:
    """
    Get iLO firmware version, license, and manager information.
    Use this when the user asks about the iLO version, firmware, or license.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _ilo_request("GET", "/manager", client)
        oem = data.get("Oem", {})
        hp = oem.get("Hp", {})
        return _t(
            de=f"iLO Info: {hp.get('ManagerType', '?')}, Firmware {hp.get('ManagerVersion', {}).get('Version', '?')}, Lizenz: {hp.get('License', '?')}",
            en=f"iLO Info: {hp.get('ManagerType', '?')}, Firmware {hp.get('ManagerVersion', {}).get('Version', '?')}, License: {hp.get('License', '?')}",
            fr=f"Info iLO: {hp.get('ManagerType', '?')}, Firmware {hp.get('ManagerVersion', {}).get('Version', '?')}, Licence: {hp.get('License', '?')}",
            es=f"Info iLO: {hp.get('ManagerType', '?')}, Firmware {hp.get('ManagerVersion', {}).get('Version', '?')}, Licencia: {hp.get('License', '?')}",
            it=f"Info iLO: {hp.get('ManagerType', '?')}, Firmware {hp.get('ManagerVersion', {}).get('Version', '?')}, Licenza: {hp.get('License', '?')}",
            nl=f"iLO Info: {hp.get('ManagerType', '?')}, Firmware {hp.get('ManagerVersion', {}).get('Version', '?')}, Licentie: {hp.get('License', '?')}",
            pl=f"Info iLO: {hp.get('ManagerType', '?')}, Firmware {hp.get('ManagerVersion', {}).get('Version', '?')}, Licencja: {hp.get('License', '?')}",
            pt=f"Info iLO: {hp.get('ManagerType', '?')}, Firmware {hp.get('ManagerVersion', {}).get('Version', '?')}, Licença: {hp.get('License', '?')}",
            ja=f"iLO情報: {hp.get('ManagerType', '?')}, ファームウェア {hp.get('ManagerVersion', {}).get('Version', '?')}, ライセンス: {hp.get('License', '?')}",
            zh=f"iLO信息: {hp.get('ManagerType', '?')}, 固件 {hp.get('ManagerVersion', {}).get('Version', '?')}, 许可证: {hp.get('License', '?')}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("get_ilo_info failed: %s", e)
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
async def get_server_info(connection_id: str = "") -> str:
    """
    Get server model, serial number, power state, and health status.
    Use this to check the physical server status.
    """
    try:
        client = await _get_api_client(connection_id)
        systems = await _ilo_request("GET", "/systems", client)
        members = systems.get("Members", [])
        if not members:
            return _t(
                de="Keine Server gefunden",
                en="No servers found",
                fr="Aucun serveur trouvé",
                es="No se encontraron servidores",
                it="Nessun server trovato",
                nl="Geen servers gevonden",
                pl="Nie znaleziono serwerów",
                pt="Nenhum servidor encontrado",
                ja="サーバーが見つかりません",
                zh="未找到服务器",
            )

        system = await _ilo_request(
            "GET", members[0]["@odata.id"].replace("/rest/v1", ""), client
        )
        oem = system.get("Oem", {})
        hp = oem.get("Hp", {})
        return _t(
            de=f"Server: {system.get('Model', '?')} von {system.get('Manufacturer', '?')}, S/N: {system.get('SerialNumber', '?')}, Status: {system.get('PowerState', '?')}, Health: {hp.get('Health', '?')}",
            en=f"Server: {system.get('Model', '?')} by {system.get('Manufacturer', '?')}, S/N: {system.get('SerialNumber', '?')}, Status: {system.get('PowerState', '?')}, Health: {hp.get('Health', '?')}",
            fr=f"Serveur: {system.get('Model', '?')} par {system.get('Manufacturer', '?')}, S/N: {system.get('SerialNumber', '?')}, État: {system.get('PowerState', '?')}, Santé: {hp.get('Health', '?')}",
            es=f"Servidor: {system.get('Model', '?')} de {system.get('Manufacturer', '?')}, S/N: {system.get('SerialNumber', '?')}, Estado: {system.get('PowerState', '?')}, Salud: {hp.get('Health', '?')}",
            it=f"Server: {system.get('Model', '?')} di {system.get('Manufacturer', '?')}, S/N: {system.get('SerialNumber', '?')}, Stato: {system.get('PowerState', '?')}, Salute: {hp.get('Health', '?')}",
            nl=f"Server: {system.get('Model', '?')} van {system.get('Manufacturer', '?')}, S/N: {system.get('SerialNumber', '?')}, Status: {system.get('PowerState', '?')}, Gezondheid: {hp.get('Health', '?')}",
            pl=f"Serwer: {system.get('Model', '?')} od {system.get('Manufacturer', '?')}, S/N: {system.get('SerialNumber', '?')}, Stan: {system.get('PowerState', '?')}, Zdrowie: {hp.get('Health', '?')}",
            pt=f"Servidor: {system.get('Model', '?')} por {system.get('Manufacturer', '?')}, S/N: {system.get('SerialNumber', '?')}, Estado: {system.get('PowerState', '?')}, Saúde: {hp.get('Health', '?')}",
            ja=f"サーバー: {system.get('Model', '?')} ({system.get('Manufacturer', '?')}), S/N: {system.get('SerialNumber', '?')}, ステータス: {system.get('PowerState', '?')}, ヘルス: {hp.get('Health', '?')}",
            zh=f"服务器: {system.get('Model', '?')} 来自 {system.get('Manufacturer', '?')}, S/N: {system.get('SerialNumber', '?')}, 状态: {system.get('PowerState', '?')}, 健康状况: {hp.get('Health', '?')}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("get_server_info failed: %s", e)
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
async def get_server_thermal(connection_id: str = "") -> str:
    """
    Get server thermal information (temperatures, fan speeds).
    Use this when the user asks about server temperatures or fan status.
    """
    try:
        client = await _get_api_client(connection_id)
        systems = await _ilo_request("GET", "/systems", client)
        members = systems.get("Members", [])
        if not members:
            return _t(
                de="Keine Server gefunden",
                en="No servers found",
                fr="Aucun serveur trouvé",
                es="No se encontraron servidores",
                it="Nessun server trovato",
                nl="Geen servers gevonden",
                pl="Nie znaleziono serwerów",
                pt="Nenhum servidor encontrado",
                ja="サーバーが見つかりません",
                zh="未找到服务器",
            )

        thermal = await _ilo_request(
            "GET",
            "/chassis"
            + members[0]["@odata.id"].replace("/rest/v1/systems", "")
            + "/thermal",
            client,
        )
        temps = thermal.get("Temperatures", [])
        lines = [
            "🌡️ "
            + _t(
                de="Temperatur",
                en="Temperature",
                fr="Température",
                es="Temperatura",
                it="Temperatura",
                nl="Temperatuur",
                pl="Temperatura",
                pt="Temperatura",
                ja="温度",
                zh="温度",
            )
        ]

        for t in temps[:8]:
            reading = t.get("ReadingCelsius")
            if reading:
                name = t.get("Name", "Sensor")
                status = t.get("Status", {}).get("Health", "OK")
                lines.append(f"  {name}: {reading}°C ({status})")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("get_server_thermal failed: %s", e)
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
async def get_server_power(connection_id: str = "") -> str:
    """
    Get power supply information.
    Use this to check PSU status and power consumption.
    """
    try:
        client = await _get_api_client(connection_id)
        systems = await _ilo_request("GET", "/systems", client)
        members = systems.get("Members", [])
        if not members:
            return _t(
                de="Keine Server gefunden",
                en="No servers found",
                fr="Aucun serveur trouvé",
                es="No se encontraron servidores",
                it="Nessun server trovato",
                nl="Geen servers gevonden",
                pl="Nie znaleziono serwerów",
                pt="Nenhum servidor encontrado",
                ja="サーバーが見つかりません",
                zh="未找到服务器",
            )

        power = await _ilo_request(
            "GET",
            "/chassis"
            + members[0]["@odata.id"].replace("/rest/v1/systems", "")
            + "/power",
            client,
        )
        psus = power.get("PowerSupplies", [])
        lines = [
            "🔌 "
            + _t(
                de="Netzteile",
                en="Power Supplies",
                fr="Alimentations",
                es="Fuentes de alimentación",
                it="Alimentatori",
                nl="Voedingen",
                pl="Zasilacze",
                pt="Fontes de alimentação",
                ja="電源",
                zh="电源",
            )
        ]

        for ps in psus:
            status = ps.get("Status", {}).get("Health", "OK")
            line = f"  {ps.get('Name', 'PSU')}: {status}"
            watts = ps.get("LastPowerOutputWatts") or ps.get("PowerOutputWatts")
            if watts:
                line += f" ({watts}W)"
            lines.append(line)

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("get_server_power failed: %s", e)
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
async def get_ilo_nics(connection_id: str = "") -> str:
    """
    Get iLO network information (IP address, MAC address).
    Use this to check the iLO network config.
    """
    try:
        client = await _get_api_client(connection_id)
        nics = await _ilo_request("GET", "/managers/-/EthernetInterfaces", client)
        members = nics.get("Members", [])
        if not members:
            return _t(
                de="Keine Netzwerk-Interfaces gefunden",
                en="No network interfaces found",
                fr="Aucune interface réseau trouvée",
                es="No se encontraron interfaces de red",
                it="Nessuna interfaccia di rete trovata",
                nl="Geen netwerkinterfaces gevonden",
                pl="Nie znaleziono interfejsów sieciowych",
                pt="Nenhuma interface de rede encontrada",
                ja="ネットワークインターフェースが見つかりません",
                zh="未找到网络接口",
            )

        lines = [
            "🌐 iLO "
            + _t(
                de="Netzwerk",
                en="Network",
                fr="Réseau",
                es="Red",
                it="Rete",
                nl="Netwerk",
                pl="Sieć",
                pt="Rede",
                ja="ネットワーク",
                zh="网络",
            )
        ]
        for nic in members[:4]:
            name = nic.get("Name", "NIC")
            mac = nic.get("MACAddress", "")
            ip = nic.get("IPv4Address", {}).get("Address", "")
            status = nic.get("Status", {}).get("Health", "OK")
            lines.append(f"  {name}: {ip or 'DHCP'} ({mac}) - {status}")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("get_ilo_nics failed: %s", e)
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
async def get_ilo_eventlog(connection_id: str = "") -> str:
    """
    Get recent iLO event log entries.
    Use this to check for errors or recent system events.
    """
    try:
        client = await _get_api_client(connection_id)
        log = await _ilo_request("GET", "/managers/-/LogServices/IML/Entries", client)
        members = log.get("Members", [])
        if not members:
            return _t(
                de="Keine Event-Log-Einträge",
                en="No event log entries",
                fr="Aucune entrée de journal d'événements",
                es="No hay entradas de registro de eventos",
                it="Nessuna voce nel registro eventi",
                nl="Geen eventlog-vermeldingen",
                pl="Brak wpisów w dzienniku zdarzeń",
                pt="Nenhuma entrada no log de eventos",
                ja="イベントログエントリがありません",
                zh="无事件日志条目",
            )

        lines = [
            "📋 "
            + _t(
                de="Letzte Events",
                en="Recent Events",
                fr="Événements récents",
                es="Eventos recientes",
                it="Eventi recenti",
                nl="Recente evenementen",
                pl="Ostatnie zdarzenia",
                pt="Eventos recentes",
                ja="最近のイベント",
                zh="最近事件",
            )
        ]
        for entry in members[:5]:
            created = entry.get("Created", "")[:10]
            severity = entry.get("Severity", "OK")
            msg = entry.get("Message", "")
            lines.append(f"  [{severity}] {created}: {msg[:80]}")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("get_ilo_eventlog failed: %s", e)
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


# ═══════════════════════════════════════════════════════
# Write/Action tools
# ═══════════════════════════════════════════════


@tool
async def server_power_on(connection_id: str = "") -> str:
    """
    Power on the server.
    Use this when the user wants to power on the server.
    German: Server einschalten/anschalten.
    """
    try:
        client = await _get_api_client(connection_id)
        systems = await _ilo_request("GET", "/systems", client)
        members = systems.get("Members", [])
        if not members:
            return _t(
                de="Keine Server gefunden",
                en="No servers found",
                fr="Aucun serveur trouvé",
                es="No se encontraron servidores",
                it="Nessun server trovato",
                nl="Geen servers gevonden",
                pl="Nie znaleziono serwerów",
                pt="Nenhum servidor encontrado",
                ja="サーバーが見つかりません",
                zh="未找到服务器",
            )

        await _ilo_request(
            "PATCH",
            members[0]["@odata.id"].replace("/rest/v1", ""),
            client,
            json={"PowerState": "On"},
        )
        return _t(
            de="✅ Server wird eingeschaltet",
            en="✅ Server powering on",
            fr="✅ Serveur en cours de mise sous tension",
            es="✅ Servidor encendiendo",
            it="✅ Server in accensione",
            nl="✅ Server wordt ingeschakeld",
            pl="✅ Serwer jest włączany",
            pt="✅ Servidor ligando",
            ja="✅ サーバーをオンにしています",
            zh="✅ 服务器正在开机",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("server_power_on failed: %s", e)
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
async def server_power_off(connection_id: str = "") -> str:
    """
    Power off the server (graceful shutdown).
    Use this when the user wants to shut down the server.
    German: Server ausschalten, herunterfahren or abschalten.
    """
    try:
        client = await _get_api_client(connection_id)
        systems = await _ilo_request("GET", "/systems", client)
        members = systems.get("Members", [])
        if not members:
            return _t(
                de="Keine Server gefunden",
                en="No servers found",
                fr="Aucun serveur trouvé",
                es="No se encontraron servidores",
                it="Nessun server trovato",
                nl="Geen servers gevonden",
                pl="Nie znaleziono serwerów",
                pt="Nenhum servidor encontrado",
                ja="サーバーが見つかりません",
                zh="未找到服务器",
            )

        await _ilo_request(
            "PATCH",
            members[0]["@odata.id"].replace("/rest/v1", ""),
            client,
            json={"PowerState": "Off"},
        )
        return _t(
            de="✅ Server wird ausgeschaltet",
            en="✅ Server powering off",
            fr="✅ Serveur en cours d'arrêt",
            es="✅ Servidor apagando",
            it="✅ Server in spegnimento",
            nl="✅ Server wordt uitgeschakeld",
            pl="✅ Serwer jest wyłączany",
            pt="✅ Servidor desligando",
            ja="✅ サーバーをオフにしています",
            zh="✅ 服务器正在关机",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("server_power_off failed: %s", e)
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
async def server_reset_ilo(connection_id: str = "") -> str:
    """
    Reset iLO (reboot the iLO management processor).
    Use this when iLO is unresponsive or has stale data.
    German: iLO Neustart, iLO reset, iLO zurücksetzen.
    """
    try:
        client = await _get_api_client(connection_id)
        await _ilo_request(
            "POST",
            "/managers/-/Actions/Manager.Reset",
            client,
            json={"ResetType": "ForceRestart"},
        )
        return _t(
            de="✅ iLO wird zurückgesetzt",
            en="✅ iLO resetting",
            fr="✅ iLO en cours de réinitialisation",
            es="✅ iLO reiniciando",
            it="✅ iLO in ripristino",
            nl="✅ iLO wordt gereset",
            pl="✅ iLO jest resetowane",
            pt="✅ iLO reiniciando",
            ja="✅ iLOをリセットしています",
            zh="✅ iLO正在重置",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("server_reset_ilo failed: %s", e)
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
async def server_press_boot_button(
    boot_target: str = "Bios", connection_id: str = ""
) -> str:
    """
    Press boot button to boot into BIOS or EFI Shell.
    Use this to force boot into BIOS for next boot.
    Valid targets: Bios, EfShell, Normal, Pxe.
    """
    try:
        client = await _get_api_client(connection_id)
        systems = await _ilo_request("GET", "/systems", client)
        members = systems.get("Members", [])
        if not members:
            return _t(
                de="Keine Server gefunden",
                en="No servers found",
                fr="Aucun serveur trouvé",
                es="No se encontraron servidores",
                it="Nessun server trovato",
                nl="Geen servers gevonden",
                pl="Nie znaleziono serwerów",
                pt="Nenhum servidor encontrado",
                ja="サーバーが見つかりません",
                zh="未找到服务器",
            )

        system_uri = members[0]["@odata.id"].replace("/rest/v1", "")

        await _ilo_request(
            "POST",
            f"{system_uri}/Actions/ComputerSystem.PressBootButton",
            client,
            json={"BootTarget": boot_target},
        )
        return _t(
            de=f"✅ Boot-Button gedrückt: {boot_target}",
            en=f"✅ Boot button pressed: {boot_target}",
            fr=f"✅ Bouton de démarrage appuyé: {boot_target}",
            es=f"✅ Botón de arranque presionado: {boot_target}",
            it=f"✅ Pulsante di avvio premuto: {boot_target}",
            nl=f"✅ Opstartknop ingedrukt: {boot_target}",
            pl=f"✅ Przycisk boot naciśnięty: {boot_target}",
            pt=f"✅ Botão de inicialização pressionado: {boot_target}",
            ja=f"✅ bootボタン押しました: {boot_target}",
            zh=f"✅ 已按下启动按钮: {boot_target}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("server_press_boot_button failed: %s", e)
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
