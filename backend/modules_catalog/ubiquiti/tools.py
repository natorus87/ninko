"""
Ubiquiti Module — LangGraph @tool functions.
Ubiquiti UniFi Controller API.
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

logger = logging.getLogger("ninko.modules.ubiquiti.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """Get UniFi API client."""
    if connection_id:
        conn = await ConnectionManager.get_connection("ubiquiti", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Ubiquiti-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Ubiquiti connection with ID '{connection_id}' not found.",
                    fr=f"Connexion Ubiquiti avec l'ID '{connection_id}' non trouvée.",
                    es=f"Conexión Ubiquiti con ID '{connection_id}' no encontrada.",
                    it=f"Connessione Ubiquiti con ID '{connection_id}' non trovata.",
                    nl=f"Ubiquiti-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie Ubiquiti z ID '{connection_id}' nie znalezione.",
                    pt=f"Conexão Ubiquiti com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のUbiquiti接続が見つかりません。",
                    zh=f"未找到ID为'{connection_id}'的Ubiquiti连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("ubiquiti")

    if conn:
        host = conn.config.get("host", "")
        user = conn.config.get("user", "")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("UNIFI_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)
        if not password:
            password = os.environ.get("UNIFI_PASSWORD", "")
        return {"host": host, "user": user, "password": password}

    host = os.environ.get("UNIFI_HOST", "")
    user = os.environ.get("UNIFI_USER", "")
    vault = get_vault()
    password = await vault.get_secret("UNIFI_PASSWORD")

    if not host:
        raise ValueError(
            _t(
                de="Keine Ubiquiti-Verbindung konfiguriert.",
                en="No Ubiquiti connection configured.",
                fr="Aucune connexion Ubiquiti configurée.",
                es="No hay conexión Ubiquiti configurada.",
                it="Nessuna connessione Ubiquiti configurata.",
                nl="Geen Ubiquiti-verbinding geconfigureerd.",
                pl="Brak skonfigurowanego połączenia Ubiquiti.",
                pt="Nenhuma conexão Ubiquiti configurada.",
                ja="Ubiquiti接続が設定されていません。",
                zh="未配置Ubiquiti连接。",
            )
        )

    return {"host": host, "user": user, "password": password}


class UnifiSession:
    def __init__(self, client: dict) -> None:
        self.host = client["host"]
        self.user = client["user"]
        self.password = client["password"]
        self.session = None
        self.cookies = None

    async def __aenter__(self) -> object:
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
        )
        login = await self.session.post(
            f"https://{self.host}/api/login",
            json={"username": self.user, "password": self.password},
            ssl=False,
        )
        login.raise_for_status()
        self.cookies = login.cookies
        return self

    async def __aexit__(self, *args) -> object:
        if self.session:
            await self.session.close()

    async def request(self, path: str) -> list:
        url = f"https://{self.host}/api/s/default{path}"
        async with self.session.get(url, cookies=self.cookies, ssl=False) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data.get("data", [])


# ═══════════════════════════════════════════════════════
# Read-only tools
# ═══════════════════════════════════════════════════════


@tool
async def list_ubiquiti_devices(connection_id: str = "") -> str:
    """
    List all UniFi devices.
    Use this to see all switches, routers, and APs.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            devices = await unifi.request("/stat/device")

        if not devices:
            return _t(
                de="Keine Geräte gefunden",
                en="No devices found",
                fr="Aucun appareil trouvé",
                es="No se encontraron dispositivos",
                it="Nessun dispositivo trovato",
                nl="Geen apparaten gevonden",
                pl="Nie znaleziono urządzeń",
                pt="Nenhum dispositivo encontrado",
                ja="デバイスが見つかりません",
                zh="未找到设备",
            )

        lines = [
            "📡 "
            + _t(
                de="Geräte",
                en="Devices",
                fr="Appareils",
                es="Dispositivos",
                it="Dispositivi",
                nl="Apparaten",
                pl="Urządzenia",
                pt="Dispositivos",
                ja="デバイス",
                zh="设备",
            )
        ]
        for d in devices[:20]:
            state = d.get("state", 0)
            state_icon = "🟢" if state == 1 else "🔴"
            name = d.get("name", "-") or d.get("mac", "-")[:8]
            model = d.get("model", "-")
            lines.append(f"  {state_icon} {name} ({model})")

        total = len(devices)
        lines.append(f"\n✓ {total} Geräte")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("list_ubiquiti_devices failed: %s", e)
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
async def list_ubiquiti_clients(connection_id: str = "") -> str:
    """
    List all clients (wired and wireless).
    Use this to see connected users.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            clients = await unifi.request("/stat/sta")

        if not clients:
            return _t(
                de="Keine Clients gefunden",
                en="No clients found",
                fr="Aucun client trouvé",
                es="No se encontraron clientes",
                it="Nessun cliente trovato",
                nl="Geen clients gevonden",
                pl="Nie znaleziono klientów",
                pt="Nenhum cliente encontrado",
                ja="クライアントが見つかりません",
                zh="未找到客户端",
            )

        lines = [
            "👥 "
            + _t(
                de="Clients",
                en="Clients",
                fr="Clients",
                es="Clientes",
                it="Clienti",
                nl="Clients",
                pl="Klienci",
                pt="Clientes",
                ja="クライアント",
                zh="客户端",
            )
        ]
        for c in clients[:15]:
            wired = c.get("is_wired", False)
            icon = "💻" if wired else "📱"
            name = c.get("hostname", "-") or c.get("name", "-") or c.get("mac", "-")[:8]
            ip = c.get("ip", "-")
            signal = c.get("signal", 0)
            lines.append(f"  {icon} {name} ({ip}) signal:{signal}")

        total = len(clients)
        lines.append(f"\n✓ {total} Clients")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("list_ubiquiti_clients failed: %s", e)
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
async def get_ubiquiti_device(device_name: str, connection_id: str = "") -> str:
    """
    Get detailed information about a specific device.
    Use this to see device stats.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            devices = await unifi.request("/stat/device")

        device = next(
            (
                d
                for d in devices
                if d.get("name") == device_name or device_name in d.get("mac", "")
            ),
            None,
        )
        if not device:
            return _t(
                de=f"Gerät nicht gefunden: {device_name}",
                en=f"Device not found: {device_name}",
                fr=f"Appareil non trouvé: {device_name}",
                es=f"Dispositivo no encontrado: {device_name}",
                it=f"Dispositivo non trovato: {device_name}",
                nl=f"Apparaat niet gevonden: {device_name}",
                pl=f"Urządzenie nie znalezione: {device_name}",
                pt=f"Dispositivo não encontrado: {device_name}",
                ja=f"デバイスが見つかりません: {device_name}",
                zh=f"未找到设备: {device_name}",
            )

        lines = [
            "📡 "
            + _t(
                de="Gerätedetails",
                en="Device details",
                fr="Détails de l'appareil",
                es="Detalles del dispositivo",
                it="Dettagli dispositivo",
                nl="Apparaatdetails",
                pl="Szczegóły urządzenia",
                pt="Detalhes do dispositivo",
                ja="デバイス詳細",
                zh="设备详情",
            )
        ]
        lines.append(f"  Name: {device.get('name', '-')}")
        lines.append(f"  Model: {device.get('model', '-')}")
        lines.append(f"  Version: {device.get('version', '-')}")
        lines.append(f"  IP: {device.get('ip', '-')}")
        lines.append(f"  Uptime: {device.get('uptime', 0) / 3600:.1f} hours")
        lines.append(f"  State: {device.get('state', 0)}")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("get_ubiquiti_device failed: %s", e)
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
async def list_ubiquiti_wlans(connection_id: str = "") -> str:
    """
    List wireless networks (SSIDs).
    Use this to see configured WiFi networks.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            wlans = await unifi.request("/rest/wlanconf")

        if not wlans:
            return _t(
                de="Keine WLANs gefunden",
                en="No WLANs found",
                fr="Aucun WLAN trouvé",
                es="No se encontraron WLANs",
                it="Nessun WLAN trovato",
                nl="Geen WLANs gevonden",
                pl="Nie znaleziono WLAN",
                pt="Nenhum WLAN encontrado",
                ja="WLANが見つかりません",
                zh="未找到WLAN",
            )

        lines = [
            "📶 "
            + _t(
                de="WLANs",
                en="WLANs",
                fr="WLANs",
                es="WLANs",
                it="WLAN",
                nl="WLANs",
                pl="WLAN-y",
                pt="WLANs",
                ja="WLAN",
                zh="WLAN",
            )
        ]
        for w in wlans[:15]:
            enabled = "✅" if w.get("enabled") else "❌"
            ssid = w.get("name", "-")
            security = w.get("security", "-")
            lines.append(f"  {enabled} {ssid} ({security})")

        total = len(wlans)
        lines.append(f"\n✓ {total} WLANs")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("list_ubiquiti_wlans failed: %s", e)
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
async def list_ubiquiti_switch_ports(connection_id: str = "") -> str:
    """
    List switch ports and their status.
    Use this to see port states on UniFi switches.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            devices = await unifi.request("/stat/device")

        lines = [
            "🔀 "
            + _t(
                de="Switch-Ports",
                en="Switch ports",
                fr="Ports du commutateur",
                es="Puertos del switch",
                it="Porte switch",
                nl="Switch-poorten",
                pl="Porty przełącznika",
                pt="Portas do switch",
                ja="スイッチポート",
                zh="交换机端口",
            )
        ]
        switches = [d for d in devices if "sw" in d.get("type", "")]
        for s in switches[:5]:
            name = s.get("name", "-")
            ports = s.get("port_table", [])
            lines.append(f"  📦 {name}:")
            for p in ports[:8]:
                pname = p.get("name", f"Port {p.get('port_idx')}")
                poe = "⚡" if p.get("poe_enable") else ""
                lines.append(f"      {pname} {poe}")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("list_ubiquiti_switch_ports failed: %s", e)
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
async def get_ubiquiti_network_stats(connection_id: str = "") -> str:
    """
    Get network traffic statistics.
    Use this to see throughput.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            devices = await unifi.request("/stat/device")

        total_rx = sum(int(d.get("rx_bytes", 0)) for d in devices)
        total_tx = sum(int(d.get("tx_bytes", 0)) for d in devices)

        lines = [
            "📊 "
            + _t(
                de="Netzwerk-Stats",
                en="Network stats",
                fr="Stats réseau",
                es="Estadísticas de red",
                it="Statistiche rete",
                nl="Netwerkstats",
                pl="Statystyki sieci",
                pt="Estatísticas de rede",
                ja="ネットワーク統計",
                zh="网络统计",
            )
        ]
        lines.append(f"  RX: {total_rx / 1024 / 1024 / 1024:.2f} GB")
        lines.append(f"  TX: {total_tx / 1024 / 1024 / 1024:.2f} GB")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("get_ubiquiti_network_stats failed: %s", e)
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
async def list_ubiquiti_firewall_rules(connection_id: str = "") -> str:
    """
    List firewall rules.
    Use this to see configured firewall rules.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            rules = await unifi.request("/rest/firewallrule")

        if not rules:
            return _t(
                de="Keine Firewall-Regeln",
                en="No firewall rules",
                fr="Aucune règle de pare-feu",
                es="Sin reglas de firewall",
                it="Nessuna regola firewall",
                nl="Geen firewall-regels",
                pl="Brak reguł firewall",
                pt="Nenhuma regra de firewall",
                ja="ファイアウォールルールがありません",
                zh="无防火墙规则",
            )

        lines = [
            "🛡️ "
            + _t(
                de="Firewall-Regeln",
                en="Firewall rules",
                fr="Règles de pare-feu",
                es="Reglas de firewall",
                it="Regole firewall",
                nl="Firewall-regels",
                pl="Reguły firewall",
                pt="Regras de firewall",
                ja="ファイアウォールルール",
                zh="防火墙规则",
            )
        ]
        for r in rules[:15]:
            action = r.get("action", "-")
            src = r.get("src_address", "any")
            dst = r.get("dst_address", "any")
            lines.append(f"  {action}: {src} → {dst}")

        total = len(rules)
        lines.append(f"\n✓ {total} Regeln")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("list_ubiquiti_firewall_rules failed: %s", e)
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
async def restart_ubiquiti_device(device_name: str, connection_id: str = "") -> str:
    """
    Restart a UniFi device.
    Use this to reboot an AP, switch, or router.
    German: UniFi Neustart, Gerät neustarten, Gerät neu starten.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            devices = await unifi.request("/stat/device")

        device = next(
            (
                d
                for d in devices
                if d.get("name") == device_name or device_name in d.get("mac", "")
            ),
            None,
        )
        if not device:
            return _t(
                de=f"Gerät nicht gefunden: {device_name}",
                en=f"Device not found: {device_name}",
                fr=f"Appareil non trouvé: {device_name}",
                es=f"Dispositivo no encontrado: {device_name}",
                it=f"Dispositivo non trovato: {device_name}",
                nl=f"Apparaat niet gevonden: {device_name}",
                pl=f"Urządzenie nie znalezione: {device_name}",
                pt=f"Dispositivo não encontrado: {device_name}",
                ja=f"デバイスが見つかりません: {device_name}",
                zh=f"未找到设备: {device_name}",
            )

        mac = device["mac"]
        await unifi.request(f"/cmd/devmgr/reboot/{mac}")

        return _t(
            de=f"✅ Gerät wird neu gestartet: {device_name}",
            en=f"✅ Device restarting: {device_name}",
            fr=f"✅ Appareil en cours de redémarrage: {device_name}",
            es=f"✅ Dispositivo reiniciando: {device_name}",
            it=f"✅ Dispositivo in riavvio: {device_name}",
            nl=f"✅ Apparaat wordt herstart: {device_name}",
            pl=f"✅ Urządzenie restartowane: {device_name}",
            pt=f"✅ Dispositivo reiniciando: {device_name}",
            ja=f"✅ デバイスを再起動中: {device_name}",
            zh=f"✅ 设备正在重启: {device_name}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("restart_ubiquiti_device failed: %s", e)
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
async def enable_ubiquiti_wlan(wlan_name: str, connection_id: str = "") -> str:
    """
    Enable a wireless network.
    Use this to enable a WiFi SSID.
    German: WLAN aktivieren/einschalten.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            wlans = await unifi.request("/rest/wlanconf")

        wlan = next(
            (
                w
                for w in wlans
                if w.get("name") == wlan_name or w.get("ssid") == wlan_name
            ),
            None,
        )
        if not wlan:
            return _t(
                de=f"WLAN nicht gefunden: {wlan_name}",
                en=f"WLAN not found: {wlan_name}",
                fr=f"WLAN non trouvé: {wlan_name}",
                es=f"WLAN no encontrado: {wlan_name}",
                it=f"WLAN non trovato: {wlan_name}",
                nl=f"WLAN niet gevonden: {wlan_name}",
                pl=f"WLAN nie znaleziony: {wlan_name}",
                pt=f"WLAN não encontrado: {wlan_name}",
                ja=f"WLANが見つかりません: {wlan_name}",
                zh=f"未找到WLAN: {wlan_name}",
            )

        _id = wlan["_id"]
        await unifi.request(f"/rest/wlanconf/{_id}", json={"enabled": True})

        return _t(
            de=f"✅ WLAN aktiviert: {wlan_name}",
            en=f"✅ WLAN enabled: {wlan_name}",
            fr=f"✅ WLAN activé: {wlan_name}",
            es=f"✅ WLAN activado: {wlan_name}",
            it=f"✅ WLAN attivato: {wlan_name}",
            nl=f"✅ WLAN ingeschakeld: {wlan_name}",
            pl=f"✅ WLAN włączony: {wlan_name}",
            pt=f"✅ WLAN ativado: {wlan_name}",
            ja=f"✅ WLANを有効にしました: {wlan_name}",
            zh=f"✅ WLAN已启用: {wlan_name}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("enable_ubiquiti_wlan failed: %s", e)
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
async def disable_ubiquiti_wlan(wlan_name: str, connection_id: str = "") -> str:
    """
    Disable a wireless network.
    Use this to disable a WiFi SSID.
    German: WLAN deaktivieren/ausschalten.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            wlans = await unifi.request("/rest/wlanconf")

        wlan = next(
            (
                w
                for w in wlans
                if w.get("name") == wlan_name or w.get("ssid") == wlan_name
            ),
            None,
        )
        if not wlan:
            return _t(
                de=f"WLAN nicht gefunden: {wlan_name}",
                en=f"WLAN not found: {wlan_name}",
                fr=f"WLAN non trouvé: {wlan_name}",
                es=f"WLAN no encontrado: {wlan_name}",
                it=f"WLAN non trovato: {wlan_name}",
                nl=f"WLAN niet gevonden: {wlan_name}",
                pl=f"WLAN nie znaleziony: {wlan_name}",
                pt=f"WLAN não encontrado: {wlan_name}",
                ja=f"WLANが見つかりません: {wlan_name}",
                zh=f"未找到WLAN: {wlan_name}",
            )

        _id = wlan["_id"]
        await unifi.request(f"/rest/wlanconf/{_id}", json={"enabled": False})

        return _t(
            de=f"✅ WLAN deaktiviert: {wlan_name}",
            en=f"✅ WLAN disabled: {wlan_name}",
            fr=f"✅ WLAN désactivé: {wlan_name}",
            es=f"✅ WLAN desactivado: {wlan_name}",
            it=f"✅ WLAN disattivato: {wlan_name}",
            nl=f"✅ WLAN uitgeschakeld: {wlan_name}",
            pl=f"✅ WLAN wyłączony: {wlan_name}",
            pt=f"✅ WLAN desativado: {wlan_name}",
            ja=f"✅ WLANを無効にしました: {wlan_name}",
            zh=f"✅ WLAN已禁用: {wlan_name}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("disable_ubiquiti_wlan failed: %s", e)
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
async def kick_ubiquiti_client(mac_address: str, connection_id: str = "") -> str:
    """
    Disconnect a client from the network.
    Use this to kick a client.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            payload = {"mac": mac_address, "cmd": "kick"}
            await unifi.request("/cmd/stamgr", json=payload)

        return _t(
            de=f"✅ Client getrennt: {mac_address}",
            en=f"✅ Client disconnected: {mac_address}",
            fr=f"✅ Client déconnecté: {mac_address}",
            es=f"✅ Cliente desconectado: {mac_address}",
            it=f"✅ Client disconnesso: {mac_address}",
            nl=f"✅ Client ontkoppeld: {mac_address}",
            pl=f"✅ Klient rozłączony: {mac_address}",
            pt=f"✅ Cliente desconectado: {mac_address}",
            ja=f"✅ クライアントを切断: {mac_address}",
            zh=f"✅ 客户端已断开: {mac_address}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("kick_ubiquiti_client failed: %s", e)
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
