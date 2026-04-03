"""
Netgear Module — LangGraph @tool functions.
Netgear Switch/Router HTTP API.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import aiohttp
from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.netgear.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """Get Netgear API client."""
    if connection_id:
        conn = await ConnectionManager.get_connection("netgear", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Netgear-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Netgear connection with ID '{connection_id}' not found.",
                    fr=f"Connexion Netgear avec l'ID '{connection_id}' non trouvée.",
                    es=f"Conexión Netgear con ID '{connection_id}' no encontrada.",
                    it=f"Connessione Netgear con ID '{connection_id}' non trovata.",
                    nl=f"Netgear-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie Netgear o ID '{connection_id}' nie znaleziono.",
                    pt=f"Conexão Netgear com ID '{connection_id}' não encontrada.",
                    ja=f"Netgear接続ID '{connection_id}' が見つかりません。",
                    zh=f"未找到ID为'{connection_id}'的Netgear连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("netgear")

    if conn:
        host = conn.config.get("host", "")
        user = conn.config.get("user", "admin")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("NETGEAR_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)
        if not password:
            password = os.environ.get("NETGEAR_PASSWORD", "")
        return {"host": host, "user": user, "password": password}

    host = os.environ.get("NETGEAR_HOST", "")
    user = os.environ.get("NETGEAR_USER", "admin")
    vault = get_vault()
    password = await vault.get_secret("NETGEAR_PASSWORD")

    if not host:
        raise ValueError(
            _t(
                de="Keine Netgear-Verbindung konfiguriert.",
                en="No Netgear connection configured.",
                fr="Aucune connexion Netgear configurée.",
                es="No hay conexión Netgear configurada.",
                it="Nessuna connessione Netgear configurata.",
                nl="Geen Netgear-verbinding geconfigureerd.",
                pl="Brak skonfigurowanego połączenia Netgear.",
                pt="Nenhuma conexão Netgear configurada.",
                ja="Netgear接続が設定されていません。",
                zh="未配置Netgear连接。",
            )
        )

    return {"host": host, "user": user, "password": password}


async def _netgear_request(client: dict, path: str) -> dict:
    """Make authenticated request to Netgear device."""
    host = client["host"]
    url = f"http://{host}{path}"

    auth = aiohttp.BasicAuth(client["user"], client["password"])

    async with aiohttp.ClientSession(
        auth=auth,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as session:
        async with session.get(url) as resp:
            if resp.status == 401:
                raise Exception("Authentication failed")
            resp.raise_for_status()
            try:
                return await resp.json()
            except Exception:
                text = await resp.text()
                return {"raw": text}


# ═══════════════════════════════════════════════════════
# Read-only tools
# ═══════════════════════════════════════════════════════


@tool
async def get_netgear_sysinfo(connection_id: str = "") -> str:
    """
    Get system information.
    Use this to see basic device info.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _netgear_request(client, "/sysinfo")

        if "raw" in data:
            return _t(
                de="Gerät antwortet, aber kein JSON",
                en="Device responds but not JSON",
                fr="L'appareil répond mais pas en JSON",
                es="El dispositivo responde pero no en JSON",
                it="Il dispositivo risponde ma non in JSON",
                nl="Apparaat reageert maar niet in JSON",
                pl="Urządzenie odpowiada, ale nie w JSON",
                pt="O dispositivo responde mas não em JSON",
                ja="デバイスは応答しますがJSONではありません",
                zh="设备响应但非JSON格式",
            )

        lines = [
            "📶 "
            + _t(
                de="Geräteinfo",
                en="Device info",
                fr="Info appareil",
                es="Info dispositivo",
                it="Info dispositivo",
                nl="Apparaat info",
                pl="Info urządzenia",
                pt="Info dispositivo",
                ja="デバイス情報",
                zh="设备信息",
            )
        ]
        lines.append(f"  Model: {data.get('model', '-')}")
        lines.append(f"  Description: {data.get('description', '-')}")
        lines.append(f"  Firmware: {data.get('firmware_version', '-')}")
        lines.append(f"  MAC: {data.get('mac_addr', '-')}")
        lines.append(f"  Uptime: {data.get('uptime', '-')}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_netgear_sysinfo failed: %s", e)
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
async def list_netgear_ports(connection_id: str = "") -> str:
    """
    List all ports and their status.
    Use this to see all switch ports.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _netgear_request(client, "/portinfo")

        ports = data.get("port_info", [])
        if not ports:
            ports = data.get("ports", [])

        if not ports:
            return _t(
                de="Keine Ports gefunden",
                en="No ports found",
                fr="Aucun port trouvé",
                es="No se encontraron puertos",
                it="Nessuna porta trovata",
                nl="Geen poorten gevonden",
                pl="Nie znaleziono portów",
                pt="Nenhuma porta encontrada",
                ja="ポートが見つかりません",
                zh="未找到端口",
            )

        lines = [
            "🔀 "
            + _t(
                de="Ports",
                en="Ports",
                fr="Ports",
                es="Puertos",
                it="Porte",
                nl="Poorten",
                pl="Porty",
                pt="Portas",
                ja="ポート",
                zh="端口",
            )
        ]
        for p in ports[:20]:
            name = p.get("port", p.get("id", "-"))
            status = p.get("link_status", p.get("status", "unknown"))
            status_icon = "🟢" if status == "Up" or status == "1" else "🔴"
            speed = p.get("speed", p.get("current_speed", "-"))
            duplex = p.get("duplex", "-")
            lines.append(f"  {status_icon} Port {name}: {speed}/{duplex}")

        total = len(ports)
        lines.append(f"\n✓ {total} Ports")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_netgear_ports failed: %s", e)
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
async def list_netgear_vlans(connection_id: str = "") -> str:
    """
    List configured VLANs.
    Use this to see VLAN configuration.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _netgear_request(client, "/vlan")

        vlans = data.get("vlan", [])
        if not vlans:
            vlans = data.get("vlans", [])

        if not vlans:
            return _t(
                de="Keine VLANs gefunden",
                en="No VLANs found",
                fr="Aucun VLAN trouvé",
                es="No se encontraron VLANs",
                it="Nessun VLAN trovato",
                nl="Geen VLANs gevonden",
                pl="Nie znaleziono VLANów",
                pt="Nenhum VLAN encontrado",
                ja="VLANが見つかりません",
                zh="未找到VLAN",
            )

        lines = [
            "🏷️ "
            + _t(
                de="VLANs",
                en="VLANs",
                fr="VLANs",
                es="VLANs",
                it="VLAN",
                nl="VLANs",
                pl="VLANy",
                pt="VLANs",
                ja="VLAN",
                zh="VLAN",
            )
        ]
        for v in vlans[:20]:
            vid = v.get("vid", v.get("vlan_id", "-"))
            name = v.get("name", v.get("vlan_name", "-"))
            lines.append(f"  VLAN {vid}: {name}")

        total = len(vlans)
        lines.append(f"\n✓ {total} VLANs")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_netgear_vlans failed: %s", e)
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
async def get_netgear_port_stats(port: str, connection_id: str = "") -> str:
    """
    Get port statistics.
    Use this to see traffic counters for a port.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _netgear_request(client, f"/portstats/{port}")

        if "raw" in data:
            return _t(
                de=f"Port nicht gefunden: {port}",
                en=f"Port not found: {port}",
                fr=f"Port non trouvé: {port}",
                es=f"Puerto no encontrado: {port}",
                it=f"Porta non trovata: {port}",
                nl=f"Port niet gevonden: {port}",
                pl=f"Nie znaleziono portu: {port}",
                pt=f"Porta não encontrada: {port}",
                ja=f"ポートが見つかりません: {port}",
                zh=f"未找到端口: {port}",
            )

        lines = [
            "📊 "
            + _t(
                de="Port-Stats",
                en="Port stats",
                fr="Stats port",
                es="Estadísticas puerto",
                it="Statistiche porta",
                nl="Poort stats",
                pl="Statystyki portu",
                pt="Estatísticas porta",
                ja="ポート統計",
                zh="端口统计",
            )
        ]
        lines.append(f"  Port {port}")
        rx = data.get("rx_bytes", "0")
        tx = data.get("tx_bytes", "0")
        lines.append(f"  RX: {int(rx) / 1024 / 1024:.2f} MB")
        lines.append(f"  TX: {int(tx) / 1024 / 1024:.2f} MB")
        lines.append(f"  RX Packets: {data.get('rx_packets', '-')}")
        lines.append(f"  TX Packets: {data.get('tx_packets', '-')}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_netgear_port_stats failed: %s", e)
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
async def list_netgear_arp(connection_id: str = "") -> str:
    """
    List ARP table.
    Use this to see connected devices.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _netgear_request(client, "/arp")

        arp = data.get("arp", [])
        if not arp:
            return _t(
                de="Keine ARP-Einträge",
                en="No ARP entries",
                fr="Aucune entrée ARP",
                es="No hay entradas ARP",
                it="Nessuna voce ARP",
                nl="Geen ARP-vermeldingen",
                pl="Brak wpisów ARP",
                pt="Nenhuma entrada ARP",
                ja="ARPエントリがありません",
                zh="无ARP条目",
            )

        lines = [
            "📠 "
            + _t(
                de="ARP-Table",
                en="ARP table",
                fr="Table ARP",
                es="Tabla ARP",
                it="Tabella ARP",
                nl="ARP-tabel",
                pl="Tabela ARP",
                pt="Tabela ARP",
                ja="ARPテーブル",
                zh="ARP表",
            )
        ]
        for a in arp[:15]:
            ip = a.get("ip_address", a.get("ip", "-"))
            mac = a.get("mac_address", a.get("mac", "-"))
            age = a.get("age", "0")
            lines.append(f"  {ip} → {mac} (age:{age})")

        total = len(arp)
        lines.append(
            f"\n✓ {total} "
            + _t(
                de="Einträge",
                en="entries",
                fr="entrées",
                es="entradas",
                it="voci",
                nl="vermeldingen",
                pl="wpisów",
                pt="entradas",
                ja="エントリ",
                zh="条目",
            )
        )

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_netgear_arp failed: %s", e)
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
async def list_netgear_lldp(connection_id: str = "") -> str:
    """
    List LLDP neighbors.
    Use this to see connected devices via LLDP.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _netgear_request(client, "/lldp")

        neighbors = data.get("lldp", [])
        if not neighbors:
            return _t(
                de="Keine LLDP-Nachbarn",
                en="No LLDP neighbors",
                fr="Aucun voisin LLDP",
                es="No hay vecinos LLDP",
                it="Nessun vicino LLDP",
                nl="Geen LLDP-neighbours",
                pl="Brak sąsiadów LLDP",
                pt="Nenhum vizinho LLDP",
                ja="LLDPネイバーがいません",
                zh="无LLDP邻居",
            )

        lines = [
            "🔗 "
            + _t(
                de="LLDP-Nachbarn",
                en="LLDP neighbors",
                fr="Voisins LLDP",
                es="Vecinos LLDP",
                it="Vicini LLDP",
                nl="LLDP-neighbours",
                pl="Sąsiedzi LLDP",
                pt="Vizinhos LLDP",
                ja="LLDPネイバー",
                zh="LLDP邻居",
            )
        ]
        for n in neighbors[:15]:
            local = n.get("local_port", "-")
            remote = n.get("chassis_id", n.get("device_id", "-"))
            name = n.get("port_id", "-")
            lines.append(f"  Port {local} → {name} ({remote})")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_netgear_lldp failed: %s", e)
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
# ═══════════════════════════════════════════════════════


@tool
async def enable_netgear_port(port: str, connection_id: str = "") -> str:
    """
    Enable a port.
    Use this to enable a switch port.
    """
    try:
        client = await _get_api_client(connection_id)
        await _netgear_request(client, f"/port/{port}/enable")
        return _t(
            de=f"✅ Port aktiviert: {port}",
            en=f"✅ Port enabled: {port}",
            fr=f"✅ Port activé: {port}",
            es=f"✅ Puerto habilitado: {port}",
            it=f"✅ Porta abilitata: {port}",
            nl=f"✅ Poort ingeschakeld: {port}",
            pl=f"✅ Port włączony: {port}",
            pt=f"✅ Porta habilitada: {port}",
            ja=f"✅ ポート有効: {port}",
            zh=f"✅ 端口已启用: {port}",
        )
    except Exception as e:
        logger.error("enable_netgear_port failed: %s", e)
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
async def disable_netgear_port(port: str, connection_id: str = "") -> str:
    """
    Disable a port.
    Use this to disable a switch port.
    """
    try:
        client = await _get_api_client(connection_id)
        await _netgear_request(client, f"/port/{port}/disable")
        return _t(
            de=f"✅ Port deaktiviert: {port}",
            en=f"✅ Port disabled: {port}",
            fr=f"✅ Port désactivé: {port}",
            es=f"✅ Puerto deshabilitado: {port}",
            it=f"✅ Porta disabilitata: {port}",
            nl=f"✅ Poort uitgeschakeld: {port}",
            pl=f"✅ Port wyłączony: {port}",
            pt=f"✅ Porta desabilitada: {port}",
            ja=f"✅ ポート無効: {port}",
            zh=f"✅ 端口已禁用: {port}",
        )
    except Exception as e:
        logger.error("disable_netgear_port failed: %s", e)
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
async def reboot_netgear(connection_id: str = "") -> str:
    """
    Reboot the Netgear device.
    Use this to restart the device.
    """
    try:
        client = await _get_api_client(connection_id)
        await _netgear_request(client, "/reboot")
        return _t(
            de="✅ Gerät wird neu gestartet",
            en="✅ Device rebooting",
            fr="✅ Appareil en redémarrage",
            es="✅ Dispositivo reiniciándose",
            it="✅ Dispositivo in riavvio",
            nl="✅ Apparaat wordt herstart",
            pl="✅ Urządzenie restartowane",
            pt="✅ Dispositivo reiniciando",
            ja="✅ デバイスを再起動中",
            zh="✅ 设备正在重启",
        )
    except Exception as e:
        logger.error("reboot_netgear failed: %s", e)
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
