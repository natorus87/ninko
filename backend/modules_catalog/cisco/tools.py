"""
Cisco Module — LangGraph @tool functions.
Cisco Network Devices API (NX-API, REST API).
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

logger = logging.getLogger("ninko.modules.cisco.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """Get Cisco API client."""
    if connection_id:
        conn = await ConnectionManager.get_connection("cisco", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Cisco-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Cisco connection with ID '{connection_id}' not found.",
                    fr=f"Connexion Cisco avec l'ID '{connection_id}' non trouvée.",
                    es=f"Conexión Cisco con ID '{connection_id}' no encontrada.",
                    it=f"Connessione Cisco con ID '{connection_id}' non trovata.",
                    nl=f"Cisco-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie Cisco o ID '{connection_id}' nie znalezione.",
                    pt=f"Conexão Cisco com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のCisco接続が見つかりません。",
                    zh=f"未找到ID为'{connection_id}'的Cisco连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("cisco")

    if conn:
        host = conn.config.get("host", "")
        user = conn.config.get("user", "")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("CISCO_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)
        if not password:
            password = os.environ.get("CISCO_PASSWORD", "")
        return {"host": host, "user": user, "password": password}

    host = os.environ.get("CISCO_HOST", "")
    user = os.environ.get("CISCO_USER", "")
    vault = get_vault()
    password = await vault.get_secret("CISCO_PASSWORD")

    if not host:
        raise ValueError(
            _t(
                de="Keine Cisco-Verbindung konfiguriert.",
                en="No Cisco connection configured.",
                fr="Aucune connexion Cisco configurée.",
                es="No hay conexión Cisco configurada.",
                it="Nessuna connessione Cisco configurata.",
                nl="Geen Cisco-verbinding geconfigureerd.",
                pl="Brak skonfigurowanego połączenia Cisco.",
                pt="Nenhuma conexão Cisco configurada.",
                ja="Cisco接続が設定されていません。",
                zh="未配置Cisco连接。",
            )
        )

    return {"host": host, "user": user, "password": password}


async def _cisco_request(
    method: str, path: str, client: dict, json: Optional[dict] = None
) -> dict:
    """Make authenticated request to Cisco device API."""
    host = client["host"]
    url = f"https://{host}/api{path}"

    async with aiohttp.ClientSession(
        auth=aiohttp.BasicAuth(client["user"], client["password"]),
        timeout=aiohttp.ClientTimeout(total=30),
    ) as session:
        async with session.request(method, url, json=json, ssl=False) as resp:
            resp.raise_for_status()
            return await resp.json()


async def _nxapi_request(client: dict, commands: list[str]) -> list[str]:
    """Execute NX-API CLI commands."""
    host = client["host"]
    url = f"https://{host}/api/mo/cli.json"

    payload = {
        "ins_api": {
            "version": "1.0",
            "type": "cli_show",
            "chunk": "0",
            "sid": "1",
            "input": commands[0],
            "output_format": "json",
        }
    }

    async with aiohttp.ClientSession(
        auth=aiohttp.BasicAuth(client["user"], client["password"]),
        timeout=aiohttp.ClientTimeout(total=30),
    ) as session:
        async with session.post(url, json=payload, ssl=False) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return [data.get("ins_api", {}).get("body", "")]


# ═══════════════════════════════════════════════════════
# Read-only tools
# ═══════════════════════════════════════════════════════


@tool
async def get_cisco_device_info(connection_id: str = "") -> str:
    """
    Get device information (hostname, model, version, uptime).
    Use this to see basic device info.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _cisco_request("GET", "/platform/mgmt/operational", client)

        lines = [
            "🔰 "
            + _t(
                de="Geräteinfo",
                en="Device info",
                fr="Info appareil",
                es="Info dispositivo",
                it="Info dispositivo",
                nl="Apparaatinfo",
                pl="Informacje o urządzeniu",
                pt="Info do dispositivo",
                ja="デバイス情報",
                zh="设备信息",
            )
        ]
        lines.append(f"  Hostname: {data.get('hostname', '-')}")
        lines.append(f"  Model: {data.get('model', '-')}")
        lines.append(f"  Version: {data.get('version', '-')}")
        lines.append(f"  Uptime: {data.get('uptime', '-')}")
        if data.get("serial"):
            lines.append(f"  Serial: {data.get('serial')}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_cisco_device_info failed: %s", e)
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
async def list_cisco_interfaces(connection_id: str = "") -> str:
    """
    List all network interfaces and their status.
    Use this to see all ports and their state.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _cisco_request("GET", "/interfaces", client)

        ifaces = data.get("interface", [])
        if not ifaces:
            return _t(
                de="Keine Interfaces gefunden",
                en="No interfaces found",
                fr="Aucune interface trouvée",
                es="No se encontraron interfaces",
                it="Nessuna interfaccia trovata",
                nl="Geen interfaces gevonden",
                pl="Nie znaleziono interfejsów",
                pt="Nenhuma interface encontrada",
                ja="インターフェースが見つかりません",
                zh="未找到接口",
            )

        lines = [
            "🔀 "
            + _t(
                de="Interfaces",
                en="Interfaces",
                fr="Interfaces",
                es="Interfaces",
                it="Interfacce",
                nl="Interfaces",
                pl="Interfejsy",
                pt="Interfaces",
                ja="インターフェース",
                zh="接口",
            )
        ]
        for i in ifaces[:20]:
            status = i.get("oper_status", "unknown")
            status_icon = "🟢" if status == "up" else "🔴" if status == "down" else "🟡"
            name = i.get("name", "-")
            speed = i.get("speed", "")
            desc = i.get("description", "")
            lines.append(f"  {status_icon} {name} {speed}")
            if desc:
                lines.append(f"      {desc}")

        total = len(ifaces)
        lines.append(
            "\n"
            + _t(
                de=f"✓ {total} Interfaces",
                en=f"✓ {total} Interfaces",
                fr=f"✓ {total} Interfaces",
                es=f"✓ {total} Interfaces",
                it=f"✓ {total} Interfacce",
                nl=f"✓ {total} Interfaces",
                pl=f"✓ {total} Interfejsów",
                pt=f"✓ {total} Interfaces",
                ja=f"✓ {total} インターフェース",
                zh=f"✓ {total} 接口",
            )
        )

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_cisco_interfaces failed: %s", e)
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
async def get_cisco_interface_details(interface: str, connection_id: str = "") -> str:
    """
    Get detailed information about a specific interface.
    Use this to see full interface statistics.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _cisco_request("GET", f"/interfaces/{interface}", client)

        lines = [
            "🔀 "
            + _t(
                de="Interface-Details",
                en="Interface details",
                fr="Détails de l'interface",
                es="Detalles de la interfaz",
                it="Dettagli interfaccia",
                nl="Interface-details",
                pl="Szczegóły interfejsu",
                pt="Detalhes da interface",
                ja="インターフェース詳細",
                zh="接口详情",
            )
        ]
        lines.append(f"  {interface}")
        lines.append(f"  Status: {data.get('oper_status', '-')}")
        lines.append(f"  Speed: {data.get('speed', '-')}")
        lines.append(f"  Duplex: {data.get('duplex', '-')}")
        lines.append(f"  Description: {data.get('description', '-')}")
        lines.append(f"  MTU: {data.get('mtu', '-')}")

        stats = data.get("counters", {})
        if stats:
            lines.append(f"  In: {stats.get('inOctets', 0)} bytes")
            lines.append(f"  Out: {stats.get('outOctets', 0)} bytes")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_cisco_interface_details failed: %s", e)
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
async def list_cisco_vlans(connection_id: str = "") -> str:
    """
    List all VLANs on the device.
    Use this to see configured VLANs.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _cisco_request("GET", "/vlans", client)

        vlans = data.get("vlan", [])
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
            status = v.get("status", "active")
            status_icon = "✅" if status == "active" else "📦"
            lines.append(f"  {status_icon} VLAN {v.get('id')}: {v.get('name', '-')}")

        total = len(vlans)
        lines.append(
            "\n"
            + _t(
                de=f"✓ {total} VLANs",
                en=f"✓ {total} VLANs",
                fr=f"✓ {total} VLANs",
                es=f"✓ {total} VLANs",
                it=f"✓ {total} VLAN",
                nl=f"✓ {total} VLANs",
                pl=f"✓ {total} VLANów",
                pt=f"✓ {total} VLANs",
                ja=f"✓ {total} VLAN",
                zh=f"✓ {total} VLAN",
            )
        )

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_cisco_vlans failed: %s", e)
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
async def list_cisco_routes(connection_id: str = "") -> str:
    """
    List routing table entries.
    Use this to see active routes.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _cisco_request("GET", "/routing/routes", client)

        routes = data.get("route", [])
        if not routes:
            return _t(
                de="Keine Routen gefunden",
                en="No routes found",
                fr="Aucune route trouvée",
                es="No se encontraron rutas",
                it="Nessuna route trovata",
                nl="Geen routes gevonden",
                pl="Nie znaleziono tras",
                pt="Nenhuma rota encontrada",
                ja="ルートが見つかりません",
                zh="未找到路由",
            )

        lines = [
            "🛤️ "
            + _t(
                de="Routen",
                en="Routes",
                fr="Routes",
                es="Rutas",
                it="Route",
                nl="Routes",
                pl="Trasy",
                pt="Rotas",
                ja="ルート",
                zh="路由",
            )
        ]
        for r in routes[:15]:
            dest = r.get("destination", "-")
            gateway = r.get("next_hop", "-")
            iface = r.get("interface", "-")
            metric = r.get("metric", "")
            lines.append(f"  {dest} → {gateway} ({iface}) {metric}")

        total = len(routes)
        lines.append(
            "\n"
            + _t(
                de=f"✓ {total} Routen",
                en=f"✓ {total} Routes",
                fr=f"✓ {total} Routes",
                es=f"✓ {total} Rutas",
                it=f"✓ {total} Route",
                nl=f"✓ {total} Routes",
                pl=f"✓ {total} Tras",
                pt=f"✓ {total} Rotas",
                ja=f"✓ {total} ルート",
                zh=f"✓ {total} 路由",
            )
        )

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_cisco_routes failed: %s", e)
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
async def list_cisco_mac_addresses(connection_id: str = "") -> str:
    """
    List MAC address table.
    Use this to see learned MAC addresses.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _cisco_request("GET", "/l2/multicast/mac", client)

        macs = data.get("mac", [])
        if not macs:
            return _t(
                de="Keine MAC-Adressen",
                en="No MAC addresses",
                fr="Aucune adresse MAC",
                es="No hay direcciones MAC",
                it="Nessun indirizzo MAC",
                nl="Geen MAC-adressen",
                pl="Brak adresów MAC",
                pt="Nenhum endereço MAC",
                ja="MACアドレスが見つかりません",
                zh="未找到MAC地址",
            )

        lines = [
            "📠 "
            + _t(
                de="MAC-Table",
                en="MAC table",
                fr="Table MAC",
                es="Tabla MAC",
                it="Tabella MAC",
                nl="MAC-tabel",
                pl="Tabela MAC",
                pt="Tabela MAC",
                ja="MACテーブル",
                zh="MAC表",
            )
        ]
        for m in macs[:15]:
            vlan = m.get("vlan", "-")
            mac = m.get("address", "-")
            iface = m.get("interface", "-")
            lines.append(f"  VLAN {vlan}: {mac} → {iface}")

        total = len(macs)
        lines.append(
            "\n"
            + _t(
                de=f"✓ {total} MAC-Adressen",
                en=f"✓ {total} MAC addresses",
                fr=f"✓ {total} adresses MAC",
                es=f"✓ {total} direcciones MAC",
                it=f"✓ {total} indirizzi MAC",
                nl=f"✓ {total} MAC-adressen",
                pl=f"✓ {total} adresów MAC",
                pt=f"✓ {total} endereços MAC",
                ja=f"✓ {total} MACアドレス",
                zh=f"✓ {total} MAC地址",
            )
        )

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_cisco_mac_addresses failed: %s", e)
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
async def get_cisco_poe_status(connection_id: str = "") -> str:
    """
    Get PoE (Power over Ethernet) status.
    Use this to see PoE port status.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _cisco_request("GET", "/interface/poe", client)

        ports = data.get("port", [])
        if not ports:
            return _t(
                de="Keine PoE-Ports",
                en="No PoE ports",
                fr="Aucun port PoE",
                es="No hay puertos PoE",
                it="Nessuna porta PoE",
                nl="Geen PoE-poorten",
                pl="Brak portów PoE",
                pt="Nenhuma porta PoE",
                ja="PoEポートが見つかりません",
                zh="未找到PoE端口",
            )

        lines = [
            "⚡ "
            + _t(
                de="PoE-Status",
                en="PoE status",
                fr="Statut PoE",
                es="Estado PoE",
                it="Stato PoE",
                nl="PoE-status",
                pl="Status PoE",
                pt="Status PoE",
                ja="PoEステータス",
                zh="PoE状态",
            )
        ]
        for p in ports[:15]:
            name = p.get("name", "-")
            status = p.get("status", "-")
            power = p.get("allocated_power", "0")
            lines.append(f"  {name}: {status} ({power}W)")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_cisco_poe_status failed: %s", e)
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
async def enable_cisco_interface(interface: str, connection_id: str = "") -> str:
    """
    Enable a network interface.
    Use this to bring up a port.
    """
    try:
        client = await _get_api_client(connection_id)
        await _cisco_request(
            "PUT",
            f"/interfaces/{interface}",
            client,
            json={"admin_status": "up"},
        )
        return _t(
            de=f"✅ Interface aktiviert: {interface}",
            en=f"✅ Interface enabled: {interface}",
            fr=f"✅ Interface activé : {interface}",
            es=f"✅ Interfaz habilitada: {interface}",
            it=f"✅ Interfaccia abilitata: {interface}",
            nl=f"✅ Interface ingeschakeld: {interface}",
            pl=f"✅ Interfejs włączony: {interface}",
            pt=f"✅ Interface ativada: {interface}",
            ja=f"✅ インターフェース有効: {interface}",
            zh=f"✅ 接口已启用: {interface}",
        )
    except Exception as e:
        logger.error("enable_cisco_interface failed: %s", e)
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
async def disable_cisco_interface(interface: str, connection_id: str = "") -> str:
    """
    Disable a network interface.
    Use this to shut down a port.
    """
    try:
        client = await _get_api_client(connection_id)
        await _cisco_request(
            "PUT",
            f"/interfaces/{interface}",
            client,
            json={"admin_status": "down"},
        )
        return _t(
            de=f"✅ Interface deaktiviert: {interface}",
            en=f"✅ Interface disabled: {interface}",
            fr=f"✅ Interface désactivé : {interface}",
            es=f"✅ Interfaz deshabilitada: {interface}",
            it=f"✅ Interfaccia disabilitata: {interface}",
            nl=f"✅ Interface uitgeschakeld: {interface}",
            pl=f"✅ Interfejs wyłączony: {interface}",
            pt=f"✅ Interface desativada: {interface}",
            ja=f"✅ インターフェース無効: {interface}",
            zh=f"✅ 接口已禁用: {interface}",
        )
    except Exception as e:
        logger.error("disable_cisco_interface failed: %s", e)
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
async def create_cisco_vlan(
    vlan_id: int, vlan_name: str, connection_id: str = ""
) -> str:
    """
    Create a new VLAN.
    Use this to add a VLAN.
    """
    try:
        client = await _get_api_client(connection_id)
        await _cisco_request(
            "POST",
            "/vlans",
            client,
            json={"id": vlan_id, "name": vlan_name, "admin_status": "active"},
        )
        return _t(
            de=f"✅ VLAN erstellt: {vlan_id} ({vlan_name})",
            en=f"✅ VLAN created: {vlan_id} ({vlan_name})",
            fr=f"✅ VLAN créé : {vlan_id} ({vlan_name})",
            es=f"✅ VLAN creado: {vlan_id} ({vlan_name})",
            it=f"✅ VLAN creato: {vlan_id} ({vlan_name})",
            nl=f"✅ VLAN aangemaakt: {vlan_id} ({vlan_name})",
            pl=f"✅ VLAN utworzony: {vlan_id} ({vlan_name})",
            pt=f"✅ VLAN criado: {vlan_id} ({vlan_name})",
            ja=f"✅ VLAN作成: {vlan_id} ({vlan_name})",
            zh=f"✅ VLAN已创建: {vlan_id} ({vlan_name})",
        )
    except Exception as e:
        logger.error("create_cisco_vlan failed: %s", e)
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
async def set_cisco_interface_vlan(
    interface: str, vlan_id: int, connection_id: str = ""
) -> str:
    """
    Assign a port to a VLAN.
    Use this to set port VLAN membership.
    """
    try:
        client = await _get_api_client(connection_id)
        await _cisco_request(
            "PUT",
            f"/interfaces/{interface}",
            client,
            json={"vlan": vlan_id},
        )
        return _t(
            de=f"✅ Interface {interface} → VLAN {vlan_id}",
            en=f"✅ Interface {interface} → VLAN {vlan_id}",
            fr=f"✅ Interface {interface} → VLAN {vlan_id}",
            es=f"✅ Interfaz {interface} → VLAN {vlan_id}",
            it=f"✅ Interfaccia {interface} → VLAN {vlan_id}",
            nl=f"✅ Interface {interface} → VLAN {vlan_id}",
            pl=f"✅ Interfejs {interface} → VLAN {vlan_id}",
            pt=f"✅ Interface {interface} → VLAN {vlan_id}",
            ja=f"✅ インターフェース {interface} → VLAN {vlan_id}",
            zh=f"✅ 接口 {interface} → VLAN {vlan_id}",
        )
    except Exception as e:
        logger.error("set_cisco_interface_vlan failed: %s", e)
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
