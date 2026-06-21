"""
Lenovo XClarity Module — LangGraph @tool functions.
Lenovo XClarity Administrator API.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import aiohttp
from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.lenovo_xclarity.tools")

_XCLARITY_TOOL_EXCEPTIONS = (
    aiohttp.ClientError,
    asyncio.TimeoutError,
    ValueError,
    KeyError,
    TypeError,
)


def _public_tool_error() -> str:
    """Generic user-facing error text without leaking internals."""
    return _t(
        de="Anfrage fehlgeschlagen. Prüfe die Server-Logs.",
        en="Request failed. Check server logs.",
        fr="Échec de la requête. Vérifiez les journaux du serveur.",
        es="Solicitud fallida. Revise los registros del servidor.",
        it="Richiesta non riuscita. Controlla i log del server.",
        nl="Verzoek mislukt. Controleer de serverlogboeken.",
        pl="Żądanie nie powiodło się. Sprawdź logi serwera.",
        pt="Solicitação falhou. Verifique os logs do servidor.",
        ja="リクエストが失敗しました。サーバーログを確認してください。",
        zh="请求失败。请检查服务器日志。",
    )


async def _get_api_client(connection_id: str = "") -> dict:
    """Get XClarity API client with auth."""
    if connection_id:
        conn = await ConnectionManager.get_connection("lenovo_xclarity", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"XClarity-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"XClarity connection with ID '{connection_id}' not found.",
                    fr=f"Connexion XClarity avec l'ID '{connection_id}' introuvable.",
                    es=f"Conexión XClarity con ID '{connection_id}' no encontrada.",
                    it=f"Connessione XClarity con ID '{connection_id}' non trovata.",
                    nl=f"XClarity-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie XClarity o ID '{connection_id}' nie znalezione.",
                    pt=f"Conexão XClarity com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のXClarity接続が見つかりません。",
                    zh=f"未找到ID为'{connection_id}'的XClarity连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("lenovo_xclarity")

    if conn:
        base_url = conn.config.get("url", "").strip()
        user = conn.config.get("user", "admin")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("XCLARITY_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)
        if not password:
            password = os.environ.get("XCLARITY_PASSWORD", "")
        if base_url and not base_url.startswith(("http://", "https://")):
            base_url = f"https://{base_url}"
        if not base_url:
            raise ValueError(
                _t(
                    de="XClarity-Verbindung ohne URL konfiguriert.",
                    en="XClarity connection is missing URL.",
                    fr="Connexion XClarity sans URL configurée.",
                    es="Conexión XClarity sin URL configurada.",
                    it="Connessione XClarity senza URL configurata.",
                    nl="XClarity-verbinding zonder URL geconfigureerd.",
                    pl="Połączenie XClarity bez skonfigurowanego URL.",
                    pt="Conexão XClarity sem URL configurada.",
                    ja="XClarity接続にURLが設定されていません。",
                    zh="XClarity连接缺少URL配置。",
                )
            )
        if not password:
            raise ValueError(
                _t(
                    de="XClarity-Verbindung ohne Passwort konfiguriert.",
                    en="XClarity connection is missing password.",
                    fr="Connexion XClarity sans mot de passe configuré.",
                    es="Conexión XClarity sin contraseña configurada.",
                    it="Connessione XClarity senza password configurata.",
                    nl="XClarity-verbinding zonder wachtwoord geconfigureerd.",
                    pl="Połączenie XClarity bez skonfigurowanego hasła.",
                    pt="Conexão XClarity sem senha configurada.",
                    ja="XClarity接続にパスワードが設定されていません。",
                    zh="XClarity连接缺少密码配置。",
                )
            )
        return {"base_url": base_url, "user": user, "password": password}

    base_url = os.environ.get("XCLARITY_HOST", "")
    user = os.environ.get("XCLARITY_USER", "admin")
    vault = get_vault()
    password = await vault.get_secret("XCLARITY_PASSWORD")

    if not base_url:
        raise ValueError(
            _t(
                de="Keine XClarity-Verbindung konfiguriert.",
                en="No XClarity connection configured.",
                fr="Aucune connexion XClarity configurée.",
                es="No hay conexión XClarity configurada.",
                it="Nessuna connessione XClarity configurata.",
                nl="Geen XClarity-verbinding geconfigureerd.",
                pl="Brak skonfigurowanego połączenia XClarity.",
                pt="Nenhuma conexão XClarity configurada.",
                ja="XClarity接続が設定されていません。",
                zh="未配置XClarity连接。",
            )
        )

    if not password:
        raise ValueError(
            _t(
                de="XCLARITY_PASSWORD fehlt.",
                en="XCLARITY_PASSWORD is missing.",
                fr="XCLARITY_PASSWORD manquant.",
                es="XCLARITY_PASSWORD faltante.",
                it="XCLARITY_PASSWORD mancante.",
                nl="XCLARITY_PASSWORD ontbreekt.",
                pl="XCLARITY_PASSWORD brakuje.",
                pt="XCLARITY_PASSWORD ausente.",
                ja="XCLARITY_PASSWORD がありません。",
                zh="缺少XCLARITY_PASSWORD。",
            )
        )

    return {"base_url": f"https://{base_url}", "user": user, "password": password}


async def _xclarity_request(
    method: str, path: str, client: dict, json: Optional[dict] = None
) -> dict:
    """Make authenticated request to XClarity API."""
    base_url = client["base_url"].rstrip("/")
    url = f"{base_url}/api{path}"

    async with aiohttp.ClientSession(
        auth=aiohttp.BasicAuth(client["user"], client["password"]),
        timeout=aiohttp.ClientTimeout(total=30),
    ) as session:
        async with session.request(method, url, json=json) as resp:
            if resp.status == 204:
                return {"status": "OK"}
            resp.raise_for_status()
            return await resp.json()


# ═══════════════════════════════════════════════════════
# Read-only tools
# ═══════════════════════════════════════════════════════


@tool
async def list_xclarity_servers(connection_id: str = "") -> str:
    """
    List all managed servers in XClarity.
    Use this to see all ThinkSystem servers.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/servers", client)
        servers = data.get("serverList", [])
        if not servers:
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

        lines = [
            "🖥️ "
            + _t(
                de="Server",
                en="Servers",
                fr="Serveurs",
                es="Servidores",
                it="Server",
                nl="Servers",
                pl="Serwery",
                pt="Servidores",
                ja="サーバー",
                zh="服务器",
            )
        ]
        for s in servers[:15]:
            status_icon = (
                "✅"
                if s.get("status") == "OK"
                else "⚠️"
                if s.get("status") == "Warning"
                else "❌"
            )
            name = s.get("hostname", "-") or s.get("uuid", "-")[:8]
            model = s.get("model", "-")
            lines.append(f"  {status_icon} {name} ({model})")

        total = len(servers)
        lines.append(f"\n✓ {total} Server")

        return "\n".join(lines)
    except _XCLARITY_TOOL_EXCEPTIONS as e:
        logger.error("list_xclarity_servers failed: %s", e)
        return _public_tool_error()


@tool
async def get_xclarity_server_details(server_name: str, connection_id: str = "") -> str:
    """
    Get detailed information about a specific server.
    Use this to see full server details.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/servers", client)
        servers = data.get("serverList", [])
        server = next(
            (
                s
                for s in servers
                if s.get("hostname") == server_name or server_name in s.get("uuid", "")
            ),
            None,
        )
        if not server:
            return _t(
                de=f"Server nicht gefunden: {server_name}",
                en=f"Server not found: {server_name}",
                fr=f"Serveur non trouvé : {server_name}",
                es=f"Servidor no encontrado: {server_name}",
                it=f"Server non trovato: {server_name}",
                nl=f"Server niet gevonden: {server_name}",
                pl=f"Nie znaleziono serwera: {server_name}",
                pt=f"Servidor não encontrado: {server_name}",
                ja=f"サーバーが見つかりません: {server_name}",
                zh=f"未找到服务器: {server_name}",
            )

        lines = [
            "🖥️ "
            + _t(
                de="Serverdetails",
                en="Server details",
                fr="Détails du serveur",
                es="Detalles del servidor",
                it="Dettagli server",
                nl="Serverdetails",
                pl="Szczegóły serwera",
                pt="Detalhes do servidor",
                ja="サーバー詳細",
                zh="服务器详情",
            )
        ]
        lines.append(f"  Hostname: {server.get('hostname', '-')}")
        lines.append(f"  Model: {server.get('model', '-')}")
        lines.append(f"  Type: {server.get('type', '-')}")
        lines.append(f"  UUID: {server.get('uuid', '-')}")
        lines.append(f"  IP: {server.get('ipAddresses', [{}])[0].get('address', '-')}")
        lines.append(f"  Status: {server.get('status', '-')}")

        if server.get("machineType"):
            lines.append(f"  Machine Type: {server.get('machineType')}")
        if server.get("serialNumber"):
            lines.append(f"  Serial: {server.get('serialNumber')}")

        return "\n".join(lines)
    except _XCLARITY_TOOL_EXCEPTIONS as e:
        logger.error("get_xclarity_server_details failed: %s", e)
        return _public_tool_error()


@tool
async def list_xclarity_chassis(connection_id: str = "") -> str:
    """
    List all managed chassis in XClarity.
    Use this to see all chassis enclosures.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/chassis", client)
        chassis_list = data.get("chassisList", [])
        if not chassis_list:
            return _t(
                de="Keine Chassis gefunden",
                en="No chassis found",
                fr="Aucun châssis trouvé",
                es="No se encontraron chassis",
                it="Nessuno chassis trovato",
                nl="Geen chassis gevonden",
                pl="Nie znaleziono chassis",
                pt="Nenhum chassis encontrado",
                ja="シャシーが見つかりません",
                zh="未找到机箱",
            )

        lines = [
            "📦 "
            + _t(
                de="Chassis",
                en="Chassis",
                fr="Châssis",
                es="Chassis",
                it="Chassis",
                nl="Chassis",
                pl="Chassis",
                pt="Chassis",
                ja="シャシー",
                zh="机箱",
            )
        ]
        for c in chassis_list[:15]:
            status_icon = "✅" if c.get("status") == "OK" else "⚠️"
            lines.append(
                f"  {status_icon} {c.get('name', '-')} ({c.get('model', '-')})"
            )

        total = len(chassis_list)
        lines.append(f"\n✓ {total} Chassis")

        return "\n".join(lines)
    except _XCLARITY_TOOL_EXCEPTIONS as e:
        logger.error("list_xclarity_chassis failed: %s", e)
        return _public_tool_error()


@tool
async def list_xclarity_storage(connection_id: str = "") -> str:
    """
    List all managed storage in XClarity.
    Use this to see all storage systems.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/storage", client)
        storage_list = data.get("storageList", [])
        if not storage_list:
            return _t(
                de="Keine Storage gefunden",
                en="No storage found",
                fr="Aucun stockage trouvé",
                es="No se encontró almacenamiento",
                it="Nessuno storage trovato",
                nl="Geen storage gevonden",
                pl="Nie znaleziono storage",
                pt="Nenhum armazenamento encontrado",
                ja="ストレージが見つかりません",
                zh="未找到存储",
            )

        lines = [
            "💾 "
            + _t(
                de="Storage",
                en="Storage",
                fr="Stockage",
                es="Almacenamiento",
                it="Storage",
                nl="Storage",
                pl="Storage",
                pt="Armazenamento",
                ja="ストレージ",
                zh="存储",
            )
        ]
        for s in storage_list[:15]:
            status_icon = "✅" if s.get("status") == "OK" else "⚠️"
            lines.append(
                f"  {status_icon} {s.get('name', '-')} ({s.get('model', '-')})"
            )

        total = len(storage_list)
        lines.append(f"\n✓ {total} Storage")

        return "\n".join(lines)
    except _XCLARITY_TOOL_EXCEPTIONS as e:
        logger.error("list_xclarity_storage failed: %s", e)
        return _public_tool_error()


@tool
async def get_xclarity_server_health(server_name: str, connection_id: str = "") -> str:
    """
    Get health and alerts for a specific server.
    Use this to check server health status.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/servers", client)
        servers = data.get("serverList", [])
        server = next(
            (
                s
                for s in servers
                if s.get("hostname") == server_name or server_name in s.get("uuid", "")
            ),
            None,
        )
        if not server:
            return _t(
                de=f"Server nicht gefunden: {server_name}",
                en=f"Server not found: {server_name}",
                fr=f"Serveur non trouvé : {server_name}",
                es=f"Servidor no encontrado: {server_name}",
                it=f"Server non trovato: {server_name}",
                nl=f"Server niet gevonden: {server_name}",
                pl=f"Nie znaleziono serwera: {server_name}",
                pt=f"Servidor não encontrado: {server_name}",
                ja=f"サーバーが見つかりません: {server_name}",
                zh=f"未找到服务器: {server_name}",
            )

        lines = [
            "💚 "
            + _t(
                de="Server-Gesundheit",
                en="Server health",
                fr="Santé du serveur",
                es="Salud del servidor",
                it="Salute server",
                nl="Servergezondheid",
                pl="Zdrowie serwera",
                pt="Saúde do servidor",
                ja="サーバー 健康状態",
                zh="服务器健康状况",
            )
        ]
        lines.append(f"  {server.get('hostname', '-')}")
        lines.append(f"  Status: {server.get('status', '-')}")
        lines.append(f"  Overall Health: {server.get('overallHealth', 'unknown')}")

        return "\n".join(lines)
    except _XCLARITY_TOOL_EXCEPTIONS as e:
        logger.error("get_xclarity_server_health failed: %s", e)
        return _public_tool_error()


@tool
async def list_xclarity_events(connection_id: str = "") -> str:
    """
    List recent events in XClarity.
    Use this to see recent alerts and warnings.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/events?summary=true", client)
        events = data.get("eventList", [])
        if not events:
            return _t(
                de="Keine Events",
                en="No events",
                fr="Aucun événement",
                es="Sin eventos",
                it="Nessun evento",
                nl="Geen events",
                pl="Brak zdarzeń",
                pt="Sem eventos",
                ja="イベントなし",
                zh="无事件",
            )

        lines = [
            "📋 "
            + _t(
                de="Letzte Events",
                en="Recent events",
                fr="Événements récents",
                es="Eventos recientes",
                it="Eventi recenti",
                nl="Recente events",
                pl="Ostatnie zdarzenia",
                pt="Eventos recentes",
                ja="最近のイベント",
                zh="最近事件",
            )
        ]
        for e in events[:10]:
            severity = e.get("severity", "unknown")
            sev_icon = (
                "🔴"
                if severity in ["critical", "error"]
                else "🟡"
                if severity == "warning"
                else "🟢"
            )
            msg = e.get("message", "-")[:80]
            lines.append(f"  {sev_icon} [{severity}] {msg}")

        return "\n".join(lines)
    except _XCLARITY_TOOL_EXCEPTIONS as e:
        logger.error("list_xclarity_events failed: %s", e)
        return _public_tool_error()


@tool
async def get_xclarity_firmware(server_name: str, connection_id: str = "") -> str:
    """
    Get firmware versions for a server.
    Use this to check installed firmware versions.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/servers", client)
        servers = data.get("serverList", [])
        server = next(
            (
                s
                for s in servers
                if s.get("hostname") == server_name or server_name in s.get("uuid", "")
            ),
            None,
        )
        if not server:
            return _t(
                de=f"Server nicht gefunden: {server_name}",
                en=f"Server not found: {server_name}",
                fr=f"Serveur non trouvé : {server_name}",
                es=f"Servidor no encontrado: {server_name}",
                it=f"Server non trovato: {server_name}",
                nl=f"Server niet gevonden: {server_name}",
                pl=f"Nie znaleziono serwera: {server_name}",
                pt=f"Servidor não encontrado: {server_name}",
                ja=f"サーバーが見つかりません: {server_name}",
                zh=f"未找到服务器: {server_name}",
            )

        uuid = server.get("uuid")
        fw_data = await _xclarity_request("GET", f"/servers/{uuid}/firmware", client)
        firmware = fw_data.get("firmware", [])

        lines = [
            "🔧 "
            + _t(
                de="Firmware",
                en="Firmware",
                fr="Firmware",
                es="Firmware",
                it="Firmware",
                nl="Firmware",
                pl="Firmware",
                pt="Firmware",
                ja="ファームウェア",
                zh="固件",
            )
        ]
        for f in firmware[:10]:
            lines.append(f"  {f.get('name', '-')}: {f.get('version', '-')}")

        return "\n".join(lines)
    except _XCLARITY_TOOL_EXCEPTIONS as e:
        logger.error("get_xclarity_firmware failed: %s", e)
        return _public_tool_error()


# ═══════════════════════════════════════════════════════
# Write/Action tools
# ═══════════════════════════════════════════════════════


@tool
async def power_on_xclarity_server(server_name: str, connection_id: str = "") -> str:
    """
    Power on a server.
    Use this to power on a managed server.
    German: Server einschalten/anschalten.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/servers", client)
        servers = data.get("serverList", [])
        server = next(
            (
                s
                for s in servers
                if s.get("hostname") == server_name or server_name in s.get("uuid", "")
            ),
            None,
        )
        if not server:
            return _t(
                de=f"Server nicht gefunden: {server_name}",
                en=f"Server not found: {server_name}",
                fr=f"Serveur non trouvé : {server_name}",
                es=f"Servidor no encontrado: {server_name}",
                it=f"Server non trovato: {server_name}",
                nl=f"Server niet gevonden: {server_name}",
                pl=f"Nie znaleziono serwera: {server_name}",
                pt=f"Servidor não encontrado: {server_name}",
                ja=f"サーバーが見つかりません: {server_name}",
                zh=f"未找到服务器: {server_name}",
            )

        uuid = server.get("uuid")
        await _xclarity_request(
            "PUT",
            f"/servers/{uuid}/actions/powerOn",
            client,
        )
        return _t(
            de=f"✅ Server wird eingeschaltet: {server_name}",
            en=f"✅ Server powering on: {server_name}",
            fr=f"✅ Serveur en cours d'allumage : {server_name}",
            es=f"✅ Servidor encendiendo: {server_name}",
            it=f"✅ Server in accensione: {server_name}",
            nl=f"✅ Server wordt ingeschakeld: {server_name}",
            pl=f"✅ Serwer jest włączany: {server_name}",
            pt=f"✅ Servidor ligando: {server_name}",
            ja=f"✅ サーバーの電源をオンにしています: {server_name}",
            zh=f"✅ 正在打开服务器: {server_name}",
        )
    except _XCLARITY_TOOL_EXCEPTIONS as e:
        logger.error("power_on_xclarity_server failed: %s", e)
        return _public_tool_error()


@tool
async def power_off_xclarity_server(server_name: str, connection_id: str = "") -> str:
    """
    Power off a server.
    Use this to power off a managed server.
    German: Server ausschalten, herunterfahren or abschalten.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/servers", client)
        servers = data.get("serverList", [])
        server = next(
            (
                s
                for s in servers
                if s.get("hostname") == server_name or server_name in s.get("uuid", "")
            ),
            None,
        )
        if not server:
            return _t(
                de=f"Server nicht gefunden: {server_name}",
                en=f"Server not found: {server_name}",
                fr=f"Serveur non trouvé : {server_name}",
                es=f"Servidor no encontrado: {server_name}",
                it=f"Server non trovato: {server_name}",
                nl=f"Server niet gevonden: {server_name}",
                pl=f"Nie znaleziono serwera: {server_name}",
                pt=f"Servidor não encontrado: {server_name}",
                ja=f"サーバーが見つかりません: {server_name}",
                zh=f"未找到服务器: {server_name}",
            )

        uuid = server.get("uuid")
        await _xclarity_request(
            "PUT",
            f"/servers/{uuid}/actions/powerOff",
            client,
        )
        return _t(
            de=f"✅ Server wird ausgeschaltet: {server_name}",
            en=f"✅ Server powering off: {server_name}",
            fr=f"✅ Serveur en cours d'arrêt : {server_name}",
            es=f"✅ Servidor apagando: {server_name}",
            it=f"Server in spegnimento: {server_name}",
            nl=f"✅ Server wordt uitgeschakeld: {server_name}",
            pl=f"✅ Serwer jest wyłączany: {server_name}",
            pt=f"✅ Servidor desligando: {server_name}",
            ja=f"✅ サーバーの電源をオフにしています: {server_name}",
            zh=f"✅ 正在关闭服务器: {server_name}",
        )
    except _XCLARITY_TOOL_EXCEPTIONS as e:
        logger.error("power_off_xclarity_server failed: %s", e)
        return _public_tool_error()


@tool
async def restart_xclarity_server(server_name: str, connection_id: str = "") -> str:
    """
    Restart a server (reboot).
    Use this to restart a managed server.
    German: Server Neustart, Server neustarten, Server neu starten.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/servers", client)
        servers = data.get("serverList", [])
        server = next(
            (
                s
                for s in servers
                if s.get("hostname") == server_name or server_name in s.get("uuid", "")
            ),
            None,
        )
        if not server:
            return _t(
                de=f"Server nicht gefunden: {server_name}",
                en=f"Server not found: {server_name}",
                fr=f"Serveur non trouvé : {server_name}",
                es=f"Servidor no encontrado: {server_name}",
                it=f"Server non trovato: {server_name}",
                nl=f"Server niet gevonden: {server_name}",
                pl=f"Nie znaleziono serwera: {server_name}",
                pt=f"Servidor não encontrado: {server_name}",
                ja=f"サーバーが見つかりません: {server_name}",
                zh=f"未找到服务器: {server_name}",
            )

        uuid = server.get("uuid")
        await _xclarity_request(
            "PUT",
            f"/servers/{uuid}/actions/restart",
            client,
        )
        return _t(
            de=f"✅ Server wird neu gestartet: {server_name}",
            en=f"✅ Server restarting: {server_name}",
            fr=f"✅ Serveur en cours de redémarrage : {server_name}",
            es=f"✅ Servidor reiniciando: {server_name}",
            it=f"✅ Server in riavvio: {server_name}",
            nl=f"✅ Server wordt opnieuw gestart: {server_name}",
            pl=f"✅ Serwer jest restartowany: {server_name}",
            pt=f"✅ Servidor reiniciando: {server_name}",
            ja=f"✅ サーバーを再起動しています: {server_name}",
            zh=f"✅ 正在重启服务器: {server_name}",
        )
    except _XCLARITY_TOOL_EXCEPTIONS as e:
        logger.error("restart_xclarity_server failed: %s", e)
        return _public_tool_error()


@tool
async def identify_xclarity_server(server_name: str, connection_id: str = "") -> str:
    """
    Identify a server (blink LED).
    Use this to locate a physical server by blinking its LED.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/servers", client)
        servers = data.get("serverList", [])
        server = next(
            (
                s
                for s in servers
                if s.get("hostname") == server_name or server_name in s.get("uuid", "")
            ),
            None,
        )
        if not server:
            return _t(
                de=f"Server nicht gefunden: {server_name}",
                en=f"Server not found: {server_name}",
                fr=f"Serveur non trouvé : {server_name}",
                es=f"Servidor no encontrado: {server_name}",
                it=f"Server non trovato: {server_name}",
                nl=f"Server niet gevonden: {server_name}",
                pl=f"Nie znaleziono serwera: {server_name}",
                pt=f"Servidor não encontrado: {server_name}",
                ja=f"サーバーが見つかりません: {server_name}",
                zh=f"未找到服务器: {server_name}",
            )

        uuid = server.get("uuid")
        await _xclarity_request(
            "PUT",
            f"/servers/{uuid}/actions/identify",
            client,
        )
        return _t(
            de=f"✅ Server-LED wird aktiviert: {server_name}",
            en=f"✅ Server LED activated: {server_name}",
            fr=f"✅ LED du serveur activée : {server_name}",
            es=f"✅ LED del servidor activada: {server_name}",
            it=f"✅ LED server attivata: {server_name}",
            nl=f"✅ Server-LED geactiveerd: {server_name}",
            pl=f"✅ Dioda LED serwera aktywowana: {server_name}",
            pt=f"✅ LED do servidor ativada: {server_name}",
            ja=f"✅ サーバーLEDを点滅させます: {server_name}",
            zh=f"✅ 服务器LED已激活: {server_name}",
        )
    except _XCLARITY_TOOL_EXCEPTIONS as e:
        logger.error("identify_xclarity_server failed: %s", e)
        return _public_tool_error()
