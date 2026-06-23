"""
Synology Module — LangGraph @tool functions.
"""

from __future__ import annotations

import logging
import os

import httpx
from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.synology.tools")

_SYNOLOGY_API_INFO = {
    "auth": "SYNO.API.Auth",
    "system": "SYNO.Core.System",
    "storage": "SYNO.Core.Storage",
    "packages": "SYNO.PackageManager",
    "tasks": "SYNO.TaskScheduler",
}


async def _get_api_client(connection_id: str = "") -> dict:
    """Load config and secrets from ConnectionManager or env vars."""
    if connection_id:
        conn = await ConnectionManager.get_connection("synology", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Synology-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Synology connection with ID '{connection_id}' not found.",
                    fr=f"Connexion Synology avec l'ID '{connection_id}' non trouvée.",
                    es=f"Conexión de Synology con ID '{connection_id}' no encontrada.",
                    it=f"Connessione Synology con ID '{connection_id}' non trovata.",
                    nl=f"Synology-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie Synology z ID '{connection_id}' nie znaleziono.",
                    pt=f"Conexão Synology com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のSynology接続が見つかりません。",
                    zh=f"未找到ID为'{connection_id}'的Synology连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("synology")

    if conn:
        base_url = conn.config.get("url", "")
        vault = get_vault()

        password = None
        pwd_key = conn.vault_keys.get("SYNOLOGY_PASSWORD")
        if pwd_key:
            password = await vault.get_secret(pwd_key)

        api_key = None
        if conn.vault_keys.get("SYNOLOGY_API_KEY"):
            api_key = await vault.get_secret(conn.vault_keys.get("SYNOLOGY_API_KEY"))

        username = conn.config.get("username", "admin")
        return {
            "base_url": base_url.rstrip("/"),
            "username": username,
            "password": password,
            "api_key": api_key,
        }

    base_url = os.environ.get("SYNOLOGY_URL", "")
    username = os.environ.get("SYNOLOGY_USERNAME", "admin")
    password = os.environ.get("SYNOLOGY_PASSWORD", "")
    api_key = os.environ.get("SYNOLOGY_API_KEY", "")

    if not base_url:
        raise ValueError(
            _t(
                de=(
                    "Keine Synology-Verbindung konfiguriert. "
                    "Bitte im Dashboard unter Einstellungen → Modul → Zahnrad eine Verbindung anlegen, "
                    "oder die Env-Variablen SYNOLOGY_URL / SYNOLOGY_USERNAME / SYNOLOGY_PASSWORD setzen."
                ),
                en=(
                    "No Synology connection configured. "
                    "Please create a connection in Settings → Module → Gear, "
                    "or set the env vars SYNOLOGY_URL / SYNOLOGY_USERNAME / SYNOLOGY_PASSWORD."
                ),
                fr=(
                    "Aucune connexion Synology configurée. "
                    "Veuillez créer une connexion dans Paramètres → Module → Engrenage, "
                    "ou définir les variables d'environnement SYNOLOGY_URL / SYNOLOGY_USERNAME / SYNOLOGY_PASSWORD."
                ),
                es=(
                    "No hay conexión de Synology configurada. "
                    "Por favor cree una conexión en Configuración → Módulo → Engranaje, "
                    "o establezca las variables de entorno SYNOLOGY_URL / SYNOLOGY_USERNAME / SYNOLOGY_PASSWORD."
                ),
                it=(
                    "Nessuna connessione Synology configurata. "
                    "Per favore crea una connessione in Impostazioni → Modulo → Ingranaggio, "
                    "o imposta le variabili di ambiente SYNOLOGY_URL / SYNOLOGY_USERNAME / SYNOLOGY_PASSWORD."
                ),
                nl=(
                    "Geen Synology-verbinding geconfigureerd. "
                    "Maak een verbinding aan in Instellingen → Module → Tandwiel, "
                    "of stel de omgevingsvariabelen SYNOLOGY_URL / SYNOLOGY_USERNAME / SYNOLOGY_PASSWORD in."
                ),
                pl=(
                    "Nie skonfigurowano połączenia Synology. "
                    "Utwórz połączenie w panelu w sekcji Ustawienia → Moduł → Ikona koła zębatego "
                    "lub ustaw zmienne środowiskowe SYNOLOGY_URL / SYNOLOGY_USERNAME / SYNOLOGY_PASSWORD."
                ),
                pt=(
                    "Nenhuma conexão Synology configurada. "
                    "Por favor crie uma conexão em Configurações → Módulo → Engrenagem, "
                    "ou defina as variáveis de ambiente SYNOLOGY_URL / SYNOLOGY_USERNAME / SYNOLOGY_PASSWORD."
                ),
                ja=(
                    "Synology接続が設定されていません。 "
                    "ダッシュボードで設定→モジュール→歯車から接続を作成するか、"
                    "環境変数SYNOLOGY_URL / SYNOLOGY_USERNAME / SYNOLOGY_PASSWORDを設定してください。"
                ),
                zh=(
                    "未配置Synology连接。 "
                    "请在设置→模块→齿轮下创建连接，"
                    "或设置环境变量SYNOLOGY_URL / SYNOLOGY_USERNAME / SYNOLOGY_PASSWORD。"
                ),
            )
        )

    return {
        "base_url": base_url.rstrip("/"),
        "username": username,
        "password": password,
        "api_key": api_key,
    }


async def _synology_request(
    base_url: str,
    endpoint: str,
    session: str,
    api: str,
    method: str = "get",
    params: dict | None = None,
) -> dict:
    """Make a request to the Synology API."""
    params = params or {}
    params["api"] = api
    params["method"] = method
    params["version"] = "1"
    params["_sid"] = session

    url = f"{base_url}/webapi/entry.cgi"
    async with httpx.AsyncClient(timeout=30.0) as client:
        if method.lower() == "post":
            resp = await client.post(url, data=params)
        else:
            resp = await client.get(url, params=params)

        resp.raise_for_status()
        data = resp.json()

        if data.get("success"):
            return data.get("data", {})
        raise ValueError(
            f"Synology API error: {data.get('error', {})} - {data.get('error', {})}"
        )


@tool
async def get_synology_system_info(connection_id: str = "") -> dict:
    """
    Retrieve Synology DSM system information.
    Use this when the user asks for system status, model, version, or uptime.
    """
    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                info = await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.System",
                    "info",
                    {"type": "all"},
                )

                return {
                    "status": "success",
                    "model": info.get("model"),
                    "serial": info.get("serial"),
                    "version": info.get("version"),
                    "version_string": info.get("version_string"),
                    "uptime": info.get("uptime"),
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("get_synology_system_info failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_synology_storage(connection_id: str = "") -> dict:
    """
    Retrieve storage information (disks, RAID, volumes).
    Use this when the user asks for storage status, disk health, or RAID status.
    """
    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                storage = await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.Storage",
                    "info",
                    {"type": "storage"},
                )

                disks = await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.Storage",
                    "disk",
                    {"type": "basic"},
                )

                return {
                    "status": "success",
                    "storage": storage,
                    "disks": disks.get("disks", []),
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("get_synology_storage failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_synology_packages(connection_id: str = "") -> dict:
    """
    Retrieve installed packages.
    Use this when the user asks for installed apps, packages, or package status.
    """
    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                packages = await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.PackageManager",
                    "list",
                    {"type": "all", "app_category": "all"},
                )

                return {
                    "status": "success",
                    "packages": packages.get("packages", []),
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("get_synology_packages failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_synology_services(connection_id: str = "") -> dict:
    """
    Retrieve service status (Active Directory, DHCP, DNS, etc.).
    Use this when the user asks for service status or which services are running.
    """
    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                services = await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.Service",
                    "list",
                    {},
                )

                return {
                    "status": "success",
                    "services": services.get("services", []),
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("get_synology_services failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def restart_synology_service(service_name: str, connection_id: str = "") -> dict:
    """
    Restart a Synology service (e.g., 'active-directory', 'dnsserver', 'dhcpserver').
    Use this when the user asks to restart a specific service.
    German: Dienst/Service Neustart, neustarten or neu starten.
    """
    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                result = await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.Service",
                    "set",
                    {"service_name": service_name, "action": "restart"},
                )

                return {
                    "status": "success",
                    "message": f"Service '{service_name}' restart initiated.",
                    "detail": result,
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("restart_synology_service failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_synology_tasks(connection_id: str = "") -> dict:
    """
    Retrieve scheduled tasks.
    Use this when the user asks for scheduled tasks or backup jobs.
    """
    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                tasks = await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.TaskScheduler",
                    "list",
                    {"type": "all"},
                )

                return {
                    "status": "success",
                    "tasks": tasks.get("tasks", []),
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("get_synology_tasks failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def check_synology_updates(connection_id: str = "") -> dict:
    """
    Check for available DSM updates.
    Use this when the user asks for available updates or new DSM versions.
    """
    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                updates = await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.Upgrade",
                    "check",
                    {"history": "false"},
                )

                return {
                    "status": "success",
                    "update_available": updates.get("update_available", False),
                    "updates": updates.get("updates", []),
                    "current_version": updates.get("current_version"),
                    "new_version": updates.get("new_version"),
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("check_synology_updates failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def install_synology_update(
    confirm: bool = False, connection_id: str = ""
) -> dict:
    """
    Install available DSM update.
    Use this when the user asks to update DSM or install the latest version.
    Requires confirm=True to actually perform the update.
    """
    if not confirm:
        return {
            "status": "pending_confirmation",
            "message": "Update will be installed. Set confirm=True to proceed.",
        }

    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=300.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                result = await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.Upgrade",
                    "update",
                    {},
                )

                return {
                    "status": "success",
                    "message": "DSM update initiated. The system will reboot to apply the update.",
                    "detail": result,
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("install_synology_update failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def install_synology_package(
    package_id: str, confirm: bool = False, connection_id: str = ""
) -> dict:
    """
    Install a Synology package (by package ID).
    Use this when the user asks to install a package like 'Audio Station', 'Video Station', etc.
    Requires confirm=True to actually install.
    """
    if not confirm:
        return {
            "status": "pending_confirmation",
            "message": f"Package '{package_id}' will be installed. Set confirm=True to proceed.",
        }

    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=120.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                result = await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.PackageManager",
                    "install",
                    {"package": package_id},
                )

                return {
                    "status": "success",
                    "message": f"Package '{package_id}' installation initiated.",
                    "detail": result,
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("install_synology_package failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def uninstall_synology_package(
    package_id: str, confirm: bool = False, connection_id: str = ""
) -> dict:
    """
    Uninstall a Synology package (by package ID).
    Use this when the user asks to uninstall a package.
    Requires confirm=True to actually uninstall.
    """
    if not confirm:
        return {
            "status": "pending_confirmation",
            "message": f"Package '{package_id}' will be uninstalled. Set confirm=True to proceed.",
        }

    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=120.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                result = await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.PackageManager",
                    "uninstall",
                    {"package": package_id},
                )

                return {
                    "status": "success",
                    "message": f"Package '{package_id}' uninstallation initiated.",
                    "detail": result,
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("uninstall_synology_package failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_synology_network_info(connection_id: str = "") -> dict:
    """
    Retrieve network information (interfaces, DNS, gateway).
    Use this when the user asks for network configuration or IP addresses.
    """
    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                network = await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.Network",
                    "get",
                    {},
                )

                return {
                    "status": "success",
                    "network": network,
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("get_synology_network_info failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_synology_users(connection_id: str = "") -> dict:
    """
    Retrieve user list.
    Use this when the user asks for user accounts or to see who has access.
    """
    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                users = await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.User",
                    "list",
                    {"limit": 100, "offset": 0},
                )

                return {
                    "status": "success",
                    "users": users.get("users", []),
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("get_synology_users failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def shutdown_synologyNAS(confirm: bool = False, connection_id: str = "") -> dict:
    """
    Shutdown the Synology NAS.
    Use this when the user asks to shutdown the NAS.
    German: NAS herunterfahren, abschalten or ausschalten.
    WARNING: This will power off the entire device!
    Requires confirm=True to actually shutdown.
    """
    if not confirm:
        return {
            "status": "pending_confirmation",
            "message": "NAS will be SHUT DOWN. Set confirm=True to proceed. WARNING: This will power off the device!",
        }

    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.System",
                    "shutdown",
                    {},
                )

                return {
                    "status": "success",
                    "message": "NAS shutdown initiated. The device is powering off.",
                }
            finally:
                pass

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("shutdown_synologyNAS failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def reboot_synologyNAS(confirm: bool = False, connection_id: str = "") -> dict:
    """
    Reboot the Synology NAS.
    Use this when the user asks to restart or reboot the NAS.
    German: NAS Neustart, neustarten or neu starten.
    Requires confirm=True to actually reboot.
    """
    if not confirm:
        return {
            "status": "pending_confirmation",
            "message": "NAS will be REBOOTED. Set confirm=True to proceed.",
        }

    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.System",
                    "reboot",
                    {},
                )

                return {
                    "status": "success",
                    "message": "NAS reboot initiated. The device will restart.",
                }
            finally:
                pass

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("reboot_synologyNAS failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def create_synology_user(
    username: str,
    password: str,
    description: str = "",
    connection_id: str = "",
) -> dict:
    """
    Create a new Synology user.
    Use this when the user asks to create a new user account.
    """
    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                result = await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.User",
                    "create",
                    {
                        "name": username,
                        "password": password,
                        "description": description,
                    },
                )

                return {
                    "status": "success",
                    "message": f"User '{username}' created successfully.",
                    "detail": result,
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("create_synology_user failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def delete_synology_user(
    username: str, confirm: bool = False, connection_id: str = ""
) -> dict:
    """
    Delete a Synology user.
    Use this when the user asks to delete a user account.
    Requires confirm=True to actually delete.
    """
    if not confirm:
        return {
            "status": "pending_confirmation",
            "message": f"User '{username}' will be DELETED. Set confirm=True to proceed.",
        }

    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.User",
                    "delete",
                    {"name": username},
                )

                return {
                    "status": "success",
                    "message": f"User '{username}' deleted successfully.",
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("delete_synology_user failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def change_synology_user_password(
    username: str,
    new_password: str,
    connection_id: str = "",
) -> dict:
    """
    Change password for a Synology user.
    Use this when the user asks to change a password.
    """
    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.User",
                    "set_password",
                    {"name": username, "password": new_password},
                )

                return {
                    "status": "success",
                    "message": f"Password for user '{username}' changed successfully.",
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("change_synology_user_password failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_synology_groups(connection_id: str = "") -> dict:
    """
    Retrieve group list.
    Use this when the user asks for groups or to see existing user groups.
    """
    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                groups = await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.Group",
                    "list",
                    {"limit": 100, "offset": 0},
                )

                return {
                    "status": "success",
                    "groups": groups.get("groups", []),
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("get_synology_groups failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def create_synology_group(
    group_name: str,
    description: str = "",
    connection_id: str = "",
) -> dict:
    """
    Create a new Synology group.
    Use this when the user asks to create a new user group.
    """
    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                result = await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.Group",
                    "create",
                    {"name": group_name, "description": description},
                )

                return {
                    "status": "success",
                    "message": f"Group '{group_name}' created successfully.",
                    "detail": result,
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("create_synology_group failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def add_user_to_group(
    username: str,
    group_name: str,
    connection_id: str = "",
) -> dict:
    """
    Add a user to a group.
    Use this when the user asks to add a user to a specific group.
    """
    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                result = await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.Group",
                    "set_users",
                    {"name": group_name, "users": [username], "action": "add"},
                )

                return {
                    "status": "success",
                    "message": f"User '{username}' added to group '{group_name}'.",
                    "detail": result,
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("add_user_to_group failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def remove_user_from_group(
    username: str,
    group_name: str,
    connection_id: str = "",
) -> dict:
    """
    Remove a user from a group.
    Use this when the user asks to remove a user from a specific group.
    """
    try:
        client = await _get_api_client(connection_id)

        async with httpx.AsyncClient(timeout=30.0) as http:
            login_resp = await http.get(
                f"{client['base_url']}/webapi/entry.cgi",
                params={
                    "api": "SYNO.API.Auth",
                    "method": "login",
                    "version": "7",
                    "account": client["username"],
                    "passwd": client["password"],
                    "session": "core",
                    "format": "cookie",
                },
            )
            login_resp.raise_for_status()
            login_data = login_resp.json()

            if not login_data.get("success"):
                raise ValueError(f"Login failed: {login_data.get('error', {})}")

            session = login_data["data"]["sid"]

            try:
                await _synology_request(
                    client["base_url"],
                    "entry.cgi",
                    session,
                    "SYNO.Core.Group",
                    "set_users",
                    {"name": group_name, "users": [username], "action": "remove"},
                )

                return {
                    "status": "success",
                    "message": f"User '{username}' removed from group '{group_name}'.",
                }
            finally:
                await http.get(
                    f"{client['base_url']}/webapi/entry.cgi",
                    params={
                        "api": "SYNO.API.Auth",
                        "method": "logout",
                        "version": "7",
                        "_sid": session,
                    },
                )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("remove_user_from_group failed: %s", e)
        return {"error": "Request failed. Check server logs."}
