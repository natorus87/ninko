"""
Linux Server Module — LangGraph @tool functions.
SSH-based server management with password and RSA-key auth.
"""

from __future__ import annotations

import asyncio
import logging
import os
import io
from typing import Any

from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.linux_server.tools")


async def _get_ssh_client(connection_id: str = "") -> dict:
    """
    Build SSH connection config from ConnectionManager.

    Returns: dict with host, port, username, password, ssh_key
    Falls back to env vars: LINUX_SERVER_HOST, LINUX_SERVER_PORT,
    LINUX_SERVER_USER, LINUX_SERVER_PASSWORD, LINUX_SERVER_SSH_KEY
    """
    if connection_id:
        conn = await ConnectionManager.get_connection("linux_server", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Linux-Server-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Linux Server connection with ID '{connection_id}' not found.",
                    fr=f"Connexion serveur Linux avec l'ID '{connection_id}' introuvable.",
                    es=f"Conexión de servidor Linux con ID '{connection_id}' no encontrada.",
                    it=f"Connessione server Linux con ID '{connection_id}' non trovata.",
                    nl=f"Linux-serververbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie serwera Linux z ID '{connection_id}' nie znaleziono.",
                    pt=f"Conexão de servidor Linux com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のLinuxサーバー接続が見つかりません。",
                    zh=f"未找到ID为'{connection_id}'的Linux服务器连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("linux_server")

    vault = get_vault()

    if conn:
        host = conn.config.get("host", "")
        port = int(conn.config.get("port", "22"))
        username = conn.config.get("user", "root")

        password = None
        password_path = conn.vault_keys.get("LINUX_SERVER_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)

        ssh_key = None
        key_path = conn.vault_keys.get("LINUX_SERVER_SSH_KEY")
        if key_path:
            ssh_key = await vault.get_secret(key_path)
    else:
        host = os.environ.get("LINUX_SERVER_HOST", "")
        port = int(os.environ.get("LINUX_SERVER_PORT", "22"))
        username = os.environ.get("LINUX_SERVER_USER", "root")
        password = os.environ.get("LINUX_SERVER_PASSWORD", "")
        ssh_key = os.environ.get("LINUX_SERVER_SSH_KEY", "")

    if not host:
        raise ValueError(
            _t(
                de=(
                    "Keine Linux-Server-Verbindung konfiguriert. "
                    "Bitte im Dashboard unter Einstellungen → Modul → Zahnrad eine Verbindung anlegen, "
                    "oder die Env-Variablen LINUX_SERVER_HOST / LINUX_SERVER_USER / LINUX_SERVER_PASSWORD setzen."
                ),
                en=(
                    "No Linux Server connection configured. "
                    "Please create a connection in Settings → Module → Gear, "
                    "or set the env vars LINUX_SERVER_HOST / LINUX_SERVER_USER / LINUX_SERVER_PASSWORD."
                ),
                fr=(
                    "Aucune connexion au serveur Linux configurée. "
                    "Créez une connexion dans Tableau de bord → Paramètres → Module → Roue dentée, "
                    "ou définissez les variables d'environnement LINUX_SERVER_HOST / LINUX_SERVER_USER / LINUX_SERVER_PASSWORD."
                ),
                es=(
                    "No hay conexión de servidor Linux configurada. "
                    "Cree una conexión en Panel → Configuración → Módulo → Engranaje, "
                    "o establezca las variables de entorno LINUX_SERVER_HOST / LINUX_SERVER_USER / LINUX_SERVER_PASSWORD."
                ),
                it=(
                    "Nessuna connessione al server Linux configurata. "
                    "Creare una connessione in Dashboard → Impostazioni → Modulo → Ingranaggio, "
                    "o impostare le variabili di ambiente LINUX_SERVER_HOST / LINUX_SERVER_USER / LINUX_SERVER_PASSWORD."
                ),
                nl=(
                    "Geen Linux-serververbinding geconfigureerd. "
                    "Maak een verbinding in Dashboard → Instellingen → Module → Tandwiel, "
                    "of stel de env-variabelen LINUX_SERVER_HOST / LINUX_SERVER_USER / LINUX_SERVER_PASSWORD in."
                ),
                pl=(
                    "Nie skonfigurowano połączenia z serwerem Linux. "
                    "Utwórz połączenie w Panel → Ustawienia → Modul → Koło zębate, "
                    "lub ustaw zmienne środowiskowe LINUX_SERVER_HOST / LINUX_SERVER_USER / LINUX_SERVER_PASSWORD."
                ),
                pt=(
                    "Nenhuma conexão de servidor Linux configurada. "
                    "Crie uma conexão no Painel → Configurações → Módulo → Engrenagem, "
                    "ou defina as variáveis de ambiente LINUX_SERVER_HOST / LINUX_SERVER_USER / LINUX_SERVER_PASSWORD."
                ),
                ja=(
                    "Linuxサーバー接続が設定されていません。 "
                    "ダッシュボード → 設定 → モジュール → 歯車 で接続を作成するか、 "
                    "環境変数 LINUX_SERVER_HOST / LINUX_SERVER_USER / LINUX_SERVER_PASSWORD を設定してください。"
                ),
                zh=(
                    "未配置Linux服务器连接。 "
                    "请在仪表板 → 设置 → 模块 → 齿轮 中创建连接，"
                    "或设置环境变量 LINUX_SERVER_HOST / LINUX_SERVER_USER / LINUX_SERVER_PASSWORD。"
                ),
            )
        )

    return {
        "host": host,
        "port": port,
        "username": username,
        "password": password or None,
        "ssh_key": ssh_key or None,
    }


async def _run_ssh_command(
    cmd: str,
    connection_id: str = "",
    timeout: int = 30,
) -> dict:
    """
    Execute a command over SSH.
    Supports password and RSA-key authentication.
    """
    import paramiko

    cfg = await _get_ssh_client(connection_id)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    connect_kwargs: dict[str, Any] = {
        "hostname": cfg["host"],
        "port": cfg["port"],
        "username": cfg["username"],
        "timeout": timeout,
    }

    # Auth: RSA-key preferred, then password
    if cfg["ssh_key"]:
        try:
            pkey = paramiko.RSAKey.from_private_key(io.StringIO(cfg["ssh_key"]))
            connect_kwargs["pkey"] = pkey
        except Exception:
            try:
                pkey = paramiko.Ed25519Key.from_private_key(io.StringIO(cfg["ssh_key"]))
                connect_kwargs["pkey"] = pkey
            except Exception as e:
                logger.warning("Failed to load SSH key: %s", e)
                if cfg["password"]:
                    connect_kwargs["password"] = cfg["password"]
    elif cfg["password"]:
        connect_kwargs["password"] = cfg["password"]

    try:
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: client.connect(**connect_kwargs)
        )

        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        output = stdout.read().decode("utf-8", errors="replace")
        error = stderr.read().decode("utf-8", errors="replace")

        return {
            "exit_code": exit_code,
            "output": output.strip(),
            "error": error.strip(),
            "host": cfg["host"],
        }
    finally:
        client.close()


def _truncate_output(text: str, max_lines: int = 100, max_chars: int = 4000) -> str:
    """Truncate long output."""
    lines = text.split("\n")
    if len(lines) > max_lines:
        text = "\n".join(lines[:max_lines])
        text += _t(
            de=f"\n[…{len(lines) - max_lines} Zeilen gekürzt]",
            en=f"\n[…{len(lines) - max_lines} lines truncated]",
        )
    if len(text) > max_chars:
        text = text[:max_chars] + _t(
            de="\n[…Ausgabe gekürzt]",
            en="\n[…output truncated]",
        )
    return text


def _error_message(e: Exception) -> str:
    """Return a multilingual error message string."""
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
# SSH Command Tools
# ═══════════════════════════════════════════════════════


@tool
async def run_command(cmd: str, connection_id: str = "") -> dict:
    """
    Execute an arbitrary shell command on the Linux server over SSH.
    Use this tool for commands that have no specific tool.
    """
    try:
        result = await _run_ssh_command(cmd, connection_id)
        if result["error"]:
            result["output"] = result["output"] + (
                "\nSTDERR: " + result["error"] if result["error"] else ""
            )
        result["output"] = _truncate_output(result["output"])
        return result
    except Exception as e:
        return {"exit_code": -1, "output": "", "error": str(e), "host": ""}


# ═══════════════════════════════════════════════════════
# System Info Tools
# ═══════════════════════════════════════════════════════


@tool
async def get_system_info(connection_id: str = "") -> dict:
    """Return basic system information (hostname, OS, kernel, uptime, CPU, RAM)."""
    try:
        cmds = {
            "hostname": "hostname",
            "os": "cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'=' -f2 | tr -d '\"' || uname -s",
            "kernel": "uname -r",
            "uptime": "uptime -p 2>/dev/null || uptime",
            "cpu_info": "lscpu | grep 'Model name' | cut -d':' -f2 | xargs",
            "cpu_cores": "nproc",
            "ram_total": "free -h | awk '/Mem:/{print $2}'",
            "ram_used": "free -h | awk '/Mem:/{print $3}'",
            "ram_percent": "free | awk '/Mem:/{printf \"%.1f\", $3/$2*100}'",
            "disk": 'df -h / | awk \'NR==2{print $3"/"$2" ("$5")"}\'',
            "load": "cat /proc/loadavg | awk '{print $1, $2, $3}'",
        }

        results = {}
        for key, cmd in cmds.items():
            r = await _run_ssh_command(cmd, connection_id)
            results[key] = r["output"] if r["exit_code"] == 0 else "N/A"

        return {"host": results.get("hostname", ""), **results}
    except Exception as e:
        return {"error": str(e)}


@tool
async def get_disk_usage(connection_id: str = "") -> str:
    """Return disk usage of all mounted filesystems (df -h)."""
    try:
        result = await _run_ssh_command(
            "df -h --output=source,size,used,avail,pcent,target 2>/dev/null || df -h",
            connection_id,
        )
        return _truncate_output(result["output"])
    except Exception as e:
        return _error_message(e)


@tool
async def get_top_processes(
    sort_by: str = "cpu", count: int = 10, connection_id: str = ""
) -> str:
    """
    Return the most active processes.
    sort_by: 'cpu' or 'mem'.
    count: number of processes to show.
    """
    try:
        sort_flag = "-pcpu" if sort_by == "cpu" else "-pmem"
        cmd = f"ps aux --sort={sort_flag} | head -{count + 1}"
        result = await _run_ssh_command(cmd, connection_id)
        return _truncate_output(result["output"])
    except Exception as e:
        return _error_message(e)


# ═══════════════════════════════════════════════════════
# Service Management (systemd)
# ═══════════════════════════════════════════════════════


@tool
async def list_services(status_filter: str = "all", connection_id: str = "") -> str:
    """
    List systemd services.
    status_filter: 'all', 'running', 'failed', 'stopped'
    """
    try:
        type_flag = {
            "all": "",
            "running": "--state=running",
            "failed": "--state=failed",
            "stopped": "--state=dead",
        }
        flag = type_flag.get(status_filter, "")
        cmd = f"systemctl list-units --type=service --no-pager --no-legend {flag} | head -50"
        result = await _run_ssh_command(cmd, connection_id)
        return _truncate_output(result["output"], max_lines=50)
    except Exception as e:
        return _error_message(e)


@tool
async def service_action(service: str, action: str, connection_id: str = "") -> dict:
    """
    Execute a systemd action on a service.
    action: 'start', 'stop', 'restart', 'status', 'enable', 'disable'
    """
    valid_actions = {"start", "stop", "restart", "status", "enable", "disable"}
    if action not in valid_actions:
        return {
            "error": _t(
                de=f"Ungültige Aktion '{action}'. Erlaubt: {', '.join(valid_actions)}",
                en=f"Invalid action '{action}'. Allowed: {', '.join(valid_actions)}",
            )
        }

    try:
        cmd = f"systemctl {action} {service}"
        result = await _run_ssh_command(cmd, connection_id)
        logger.info("Service %s %s: exit_code=%d", service, action, result["exit_code"])
        return {
            "service": service,
            "action": action,
            "exit_code": result["exit_code"],
            "output": _truncate_output(result["output"] or result["error"]),
            "success": result["exit_code"] == 0,
        }
    except Exception as e:
        logger.error("service_action failed: %s", e)
        return {"service": service, "action": action, "error": str(e), "success": False}


# ═══════════════════════════════════════════════════════
# Log Tools
# ═══════════════════════════════════════════════════════


@tool
async def get_journal(
    service: str = "", lines: int = 50, connection_id: str = ""
) -> str:
    """
    Return logs from the systemd journal.
    service: service name (e.g. 'nginx', 'sshd'). Empty = all.
    lines: number of lines.
    """
    try:
        unit_flag = f"-u {service}" if service else ""
        cmd = f"journalctl {unit_flag} --no-pager -n {lines} --output=short-iso"
        result = await _run_ssh_command(cmd, connection_id)
        return _truncate_output(result["output"], max_lines=lines)
    except Exception as e:
        return _error_message(e)


@tool
async def get_logfile(path: str, lines: int = 50, connection_id: str = "") -> str:
    """
    Return the last lines of a log file.
    Example: path='/var/log/syslog', lines=100
    """
    try:
        cmd = f"tail -n {lines} {path} 2>/dev/null"
        result = await _run_ssh_command(cmd, connection_id)
        if result["exit_code"] != 0:
            return _t(
                de=f"Fehler: Datei '{path}' nicht lesbar oder nicht vorhanden.",
                en=f"Error: File '{path}' is not readable or does not exist.",
            )
        return _truncate_output(result["output"], max_lines=lines)
    except Exception as e:
        return _error_message(e)


# ═══════════════════════════════════════════════════════
# Package Management
# ═══════════════════════════════════════════════════════


@tool
async def apt_update(connection_id: str = "") -> dict:
    """Run apt update (refresh package lists)."""
    try:
        result = await _run_ssh_command(
            "apt-get update 2>&1", connection_id, timeout=120
        )
        logger.info("apt update: exit_code=%d", result["exit_code"])
        return {
            "exit_code": result["exit_code"],
            "output": _truncate_output(result["output"], max_lines=30),
            "success": result["exit_code"] == 0,
        }
    except Exception as e:
        return {"error": str(e), "success": False}


@tool
async def apt_upgrade(packages: str = "", connection_id: str = "") -> dict:
    """
    Run apt upgrade. With packages="" all packages are upgraded.
    With packages="nginx mysql-server" only those are upgraded.
    """
    try:
        if packages:
            cmd = f"DEBIAN_FRONTEND=noninteractive apt-get install --only-upgrade -y {packages} 2>&1"
        else:
            cmd = "DEBIAN_FRONTEND=noninteractive apt-get upgrade -y 2>&1"
        result = await _run_ssh_command(cmd, connection_id, timeout=300)
        logger.info("apt upgrade: exit_code=%d", result["exit_code"])
        return {
            "exit_code": result["exit_code"],
            "output": _truncate_output(result["output"], max_lines=30),
            "success": result["exit_code"] == 0,
        }
    except Exception as e:
        return {"error": str(e), "success": False}


@tool
async def apt_install(packages: str, connection_id: str = "") -> dict:
    """
    Install packages via apt. Multiple packages separated by spaces.
    Example: packages='htop vim curl'
    DESTRUCTIVE — requires confirmation.
    """
    try:
        cmd = f"DEBIAN_FRONTEND=noninteractive apt-get install -y {packages} 2>&1"
        result = await _run_ssh_command(cmd, connection_id, timeout=300)
        logger.info("apt install %s: exit_code=%d", packages, result["exit_code"])
        return {
            "packages": packages,
            "exit_code": result["exit_code"],
            "output": _truncate_output(result["output"], max_lines=30),
            "success": result["exit_code"] == 0,
        }
    except Exception as e:
        return {"packages": packages, "error": str(e), "success": False}


# ═══════════════════════════════════════════════════════
# File Management
# ═══════════════════════════════════════════════════════


@tool
async def read_file(path: str, max_lines: int = 200, connection_id: str = "") -> str:
    """
    Read the contents of a file on the server.
    Example: path='/etc/nginx/nginx.conf'
    """
    try:
        cmd = f"head -n {max_lines} {path} 2>/dev/null"
        result = await _run_ssh_command(cmd, connection_id)
        if result["exit_code"] != 0:
            return _t(
                de=f"Fehler: Datei '{path}' nicht lesbar oder nicht vorhanden.",
                en=f"Error: File '{path}' is not readable or does not exist.",
                fr=f"Erreur: Le fichier '{path}' n'est pas lisible ou n'existe pas.",
                es=f"Error: El archivo '{path}' no es legible o no existe.",
                it=f"Errore: Il file '{path}' non è leggibile o non esiste.",
                nl=f"Fout: Bestand '{path}' is niet leesbaar of bestaat niet.",
                pl=f"Błąd: Plik '{path}' nie jest czytelny lub nie istnieje.",
                pt=f"Erro: O arquivo '{path}' não é legível ou não existe.",
                ja=f"エラー：ファイル '{path}' が読み取れないか存在しません。",
                zh=f"错误：文件 '{path}' 不可读或不存在。",
            )
        return _truncate_output(result["output"], max_lines=max_lines)
    except Exception as e:
        return _error_message(e)


@tool
async def list_directory(path: str = "/var/log", connection_id: str = "") -> str:
    """
    List the contents of a directory.
    Example: path='/etc/nginx/sites-available'
    """
    try:
        cmd = f"ls -lah {path} 2>/dev/null"
        result = await _run_ssh_command(cmd, connection_id)
        if result["exit_code"] != 0:
            return _t(
                de=f"Fehler: Datei '{path}' nicht lesbar oder nicht vorhanden.",
                en=f"Error: File '{path}' is not readable or does not exist.",
                fr=f"Erreur: Le fichier '{path}' n'est pas lisible ou n'existe pas.",
                es=f"Error: El archivo '{path}' no es legible o no existe.",
                it=f"Errore: Il file '{path}' non è leggibile o non esiste.",
                nl=f"Fout: Bestand '{path}' is niet leesbaar of bestaat niet.",
                pl=f"Błąd: Plik '{path}' nie jest czytelny lub nie istnieje.",
                pt=f"Erro: O arquivo '{path}' não é legível ou não existe.",
                ja=f"エラー：ファイル '{path}' が読み取れないか存在しません。",
                zh=f"错误：文件 '{path}' 不可读或不存在。",
            )
        return _truncate_output(result["output"])
    except Exception as e:
        return _error_message(e)


# ═══════════════════════════════════════════════════════
# Network
# ═══════════════════════════════════════════════════════


@tool
async def get_network_info(connection_id: str = "") -> str:
    """Return network information (IP addresses, open ports, DNS)."""
    try:
        cmd = "ip -4 addr show | grep inet; echo '---'; ss -tlnp 2>/dev/null | head -20; echo '---'; cat /etc/resolv.conf | grep nameserver"
        result = await _run_ssh_command(cmd, connection_id)
        return _truncate_output(result["output"])
    except Exception as e:
        return _error_message(e)


@tool
async def check_port(host: str, port: int, connection_id: str = "") -> dict:
    """Check whether a port on a host is reachable (netcat or /dev/tcp)."""
    try:
        cmd = f"timeout 3 bash -c 'echo > /dev/tcp/{host}/{port}' 2>&1 && echo 'OPEN' || echo 'CLOSED'"
        result = await _run_ssh_command(cmd, connection_id)
        return {
            "host": host,
            "port": port,
            "status": "open" if "OPEN" in result["output"] else "closed",
        }
    except Exception as e:
        return {"host": host, "port": port, "error": str(e)}


# ═══════════════════════════════════════════════════════
# User Management
# ═══════════════════════════════════════════════════════


@tool
async def list_users(connection_id: str = "") -> str:
    """List all users with login shell (/etc/passwd)."""
    try:
        cmd = "grep -v '/nologin\\|/false' /etc/passwd | cut -d: -f1,3,6,7 | column -t -s:"
        result = await _run_ssh_command(cmd, connection_id)
        return _truncate_output(result["output"])
    except Exception as e:
        return _error_message(e)


@tool
async def check_last_logins(count: int = 10, connection_id: str = "") -> str:
    """Show the last login attempts (last)."""
    try:
        cmd = f"last -n {count} --time-format iso 2>/dev/null || last -n {count}"
        result = await _run_ssh_command(cmd, connection_id)
        return _truncate_output(result["output"], max_lines=count)
    except Exception as e:
        return _error_message(e)


# ═══════════════════════════════════════════════════════
# Control Tools
# ═══════════════════════════════════════════════════════


@tool
async def reboot_server(connection_id: str = "") -> dict:
    """Reboot the server. DESTRUCTIVE — requires explicit confirmation."""
    return {
        "action": "reboot",
        "status": "confirmation_required",
        "detail": _t(
            de="Soll der Server wirklich neu gestartet werden? Dies unterbricht alle laufenden Dienste! Bestätige mit 'Ja'.",
            en="Should the server really be rebooted? This will interrupt all running services! Confirm with 'Yes'.",
        ),
    }


@tool
async def confirm_reboot(connection_id: str = "") -> dict:
    """Confirmed server reboot. Only call after explicit user confirmation."""
    try:
        await _run_ssh_command("reboot", connection_id, timeout=5)
        return {
            "action": "reboot",
            "status": "success",
            "detail": _t(
                de="Neustart wurde eingeleitet.",
                en="Reboot initiated.",
            ),
        }
    except Exception:
        return {
            "action": "reboot",
            "status": "success",
            "detail": _t(
                de="Neustart wurde eingeleitet (Verbindung getrennt wie erwartet).",
                en="Reboot initiated (connection dropped as expected).",
            ),
        }
