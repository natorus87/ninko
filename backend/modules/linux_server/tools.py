"""
Linux Server Modul – LangGraph @tool-Funktionen.
SSH-basiertes Server-Management mit Passwort und RSA-Key Auth.
"""

from __future__ import annotations

import asyncio
import logging
import os
import io
from typing import Any

from langchain_core.tools import tool

from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("kumio.modules.linux_server.tools")


async def _get_ssh_client(connection_id: str = "") -> dict:
    """
    Erstellt SSH-Connection-Config aus dem ConnectionManager.

    Rückgabe: dict mit host, port, username, password, ssh_key
    Fallback auf Env-Variablen: LINUX_SERVER_HOST, LINUX_SERVER_PORT,
    LINUX_SERVER_USER, LINUX_SERVER_PASSWORD, LINUX_SERVER_SSH_KEY
    """
    if connection_id:
        conn = await ConnectionManager.get_connection("linux_server", connection_id)
        if not conn:
            raise ValueError(f"Linux-Server-Verbindung mit ID '{connection_id}' nicht gefunden.")
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
        # Env-Fallback
        host = os.environ.get("LINUX_SERVER_HOST", "")
        port = int(os.environ.get("LINUX_SERVER_PORT", "22"))
        username = os.environ.get("LINUX_SERVER_USER", "root")
        password = os.environ.get("LINUX_SERVER_PASSWORD", "")
        ssh_key = os.environ.get("LINUX_SERVER_SSH_KEY", "")

    if not host:
        raise ValueError(
            "Keine Linux-Server-Verbindung konfiguriert. "
            "Bitte im Dashboard unter Einstellungen → Modul → Zahnrad eine Verbindung anlegen, "
            "oder die Env-Variablen LINUX_SERVER_HOST / LINUX_SERVER_USER / LINUX_SERVER_PASSWORD setzen."
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
    Führt einen Befehl über SSH aus.
    Unterstützt Passwort- und RSA-Key-Authentifizierung.
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

    # Auth: RSA-Key bevorzugt, dann Passwort
    if cfg["ssh_key"]:
        try:
            pkey = paramiko.RSAKey.from_private_key(io.StringIO(cfg["ssh_key"]))
            connect_kwargs["pkey"] = pkey
        except Exception:
            try:
                pkey = paramiko.Ed25519Key.from_private_key(io.StringIO(cfg["ssh_key"]))
                connect_kwargs["pkey"] = pkey
            except Exception as e:
                logger.warning("SSH-Key konnte nicht geladen werden: %s", e)
                if cfg["password"]:
                    connect_kwargs["password"] = cfg["password"]
    elif cfg["password"]:
        connect_kwargs["password"] = cfg["password"]

    try:
        await asyncio.get_event_loop().run_in_executor(None, lambda: client.connect(**connect_kwargs))

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
    """Kürzt lange Ausgaben."""
    lines = text.split("\n")
    if len(lines) > max_lines:
        text = "\n".join(lines[:max_lines])
        text += f"\n[…{len(lines) - max_lines} Zeilen gekürzt]"
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[…Ausgabe gekürzt]"
    return text


# ═══════════════════════════════════════════════════════
# SSH Befehls-Tools
# ═══════════════════════════════════════════════════════

@tool
async def run_command(cmd: str, connection_id: str = "") -> dict:
    """
    Führt einen beliebigen Shell-Befehl auf dem Linux-Server über SSH aus.
    Nutze dieses Tool für alle Befehle, die kein spezifisches Tool haben.
    """
    try:
        result = await _run_ssh_command(cmd, connection_id)
        if result["error"]:
            result["output"] = result["output"] + ("\nSTDERR: " + result["error"] if result["error"] else "")
        result["output"] = _truncate_output(result["output"])
        return result
    except Exception as e:
        return {"exit_code": -1, "output": "", "error": str(e), "host": ""}


# ═══════════════════════════════════════════════════════
# System-Info Tools
# ═══════════════════════════════════════════════════════

@tool
async def get_system_info(connection_id: str = "") -> dict:
    """Gibt grundlegende System-Informationen zurück (Hostname, OS, Kernel, Uptime, CPU, RAM)."""
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
            "disk": "df -h / | awk 'NR==2{print $3\"/\"$2\" (\"$5\")\"}'",
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
    """Gibt die Festplattennutzung aller gemounteten Dateisysteme zurück (df -h)."""
    try:
        result = await _run_ssh_command("df -h --output=source,size,used,avail,pcent,target 2>/dev/null || df -h", connection_id)
        return _truncate_output(result["output"])
    except Exception as e:
        return f"Fehler: {e}"


@tool
async def get_top_processes(sort_by: str = "cpu", count: int = 10, connection_id: str = "") -> str:
    """
    Gibt die aktivsten Prozesse zurück.
    sort_by: 'cpu' oder 'mem' (Speicher).
    count: Anzahl der anzuzeigenden Prozesse.
    """
    try:
        sort_flag = "-pcpu" if sort_by == "cpu" else "-pmem"
        cmd = f"ps aux --sort={sort_flag} | head -{count + 1}"
        result = await _run_ssh_command(cmd, connection_id)
        return _truncate_output(result["output"])
    except Exception as e:
        return f"Fehler: {e}"


# ═══════════════════════════════════════════════════════
# Service Management (systemd)
# ═══════════════════════════════════════════════════════

@tool
async def list_services(status_filter: str = "all", connection_id: str = "") -> str:
    """
    Listet systemd-Services auf.
    status_filter: 'all', 'running', 'failed', 'stopped'
    """
    try:
        type_flag = {"all": "", "running": "--state=running", "failed": "--state=failed", "stopped": "--state=dead"}
        flag = type_flag.get(status_filter, "")
        cmd = f"systemctl list-units --type=service --no-pager --no-legend {flag} | head -50"
        result = await _run_ssh_command(cmd, connection_id)
        return _truncate_output(result["output"], max_lines=50)
    except Exception as e:
        return f"Fehler: {e}"


@tool
async def service_action(service: str, action: str, connection_id: str = "") -> dict:
    """
    Führt eine systemd-Aktion auf einem Service aus.
    action: 'start', 'stop', 'restart', 'status', 'enable', 'disable'
    """
    valid_actions = {"start", "stop", "restart", "status", "enable", "disable"}
    if action not in valid_actions:
        return {"error": f"Ungültige Aktion '{action}'. Erlaubt: {', '.join(valid_actions)}"}

    try:
        cmd = f"systemctl {action} {service}"
        result = await _run_ssh_command(cmd, connection_id)
        return {
            "service": service,
            "action": action,
            "exit_code": result["exit_code"],
            "output": _truncate_output(result["output"] or result["error"]),
            "success": result["exit_code"] == 0,
        }
    except Exception as e:
        return {"service": service, "action": action, "error": str(e), "success": False}


# ═══════════════════════════════════════════════════════
# Log-Tools
# ═══════════════════════════════════════════════════════

@tool
async def get_journal(service: str = "", lines: int = 50, connection_id: str = "") -> str:
    """
    Gibt Logs aus dem systemd-Journal zurück.
    service: Service-Name (z.B. 'nginx', 'sshd'). Leer = alle.
    lines: Anzahl der Zeilen.
    """
    try:
        unit_flag = f"-u {service}" if service else ""
        cmd = f"journalctl {unit_flag} --no-pager -n {lines} --output=short-iso"
        result = await _run_ssh_command(cmd, connection_id)
        return _truncate_output(result["output"], max_lines=lines)
    except Exception as e:
        return f"Fehler: {e}"


@tool
async def get_logfile(path: str, lines: int = 50, connection_id: str = "") -> str:
    """
    Gibt die letzten Zeilen einer Log-Datei zurück.
    Beispiel: path='/var/log/syslog', lines=100
    """
    try:
        cmd = f"tail -n {lines} {path} 2>/dev/null"
        result = await _run_ssh_command(cmd, connection_id)
        if result["exit_code"] != 0:
            return f"Fehler: Datei '{path}' nicht lesbar oder nicht vorhanden."
        return _truncate_output(result["output"], max_lines=lines)
    except Exception as e:
        return f"Fehler: {e}"


# ═══════════════════════════════════════════════════════
# Paket-Management
# ═══════════════════════════════════════════════════════

@tool
async def apt_update(connection_id: str = "") -> dict:
    """Führt apt update durch (Paketlisten aktualisieren)."""
    try:
        result = await _run_ssh_command("apt-get update 2>&1", connection_id, timeout=120)
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
    Führt apt upgrade durch. Bei packages="" werden alle Pakete aktualisiert.
    Bei packages="nginx mysql-server" werden nur diese aktualisiert.
    """
    try:
        if packages:
            cmd = f"DEBIAN_FRONTEND=noninteractive apt-get install --only-upgrade -y {packages} 2>&1"
        else:
            cmd = "DEBIAN_FRONTEND=noninteractive apt-get upgrade -y 2>&1"
        result = await _run_ssh_command(cmd, connection_id, timeout=300)
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
    Installiert Pakete über apt. Mehrere Pakete durch Leerzeichen getrennt.
    Beispiel: packages='htop vim curl'
    DESTRUKTIV – erfordert Bestätigung.
    """
    try:
        cmd = f"DEBIAN_FRONTEND=noninteractive apt-get install -y {packages} 2>&1"
        result = await _run_ssh_command(cmd, connection_id, timeout=300)
        return {
            "packages": packages,
            "exit_code": result["exit_code"],
            "output": _truncate_output(result["output"], max_lines=30),
            "success": result["exit_code"] == 0,
        }
    except Exception as e:
        return {"packages": packages, "error": str(e), "success": False}


# ═══════════════════════════════════════════════════════
# Datei-Management
# ═══════════════════════════════════════════════════════

@tool
async def read_file(path: str, max_lines: int = 200, connection_id: str = "") -> str:
    """
    Liest den Inhalt einer Datei auf dem Server.
    Beispiel: path='/etc/nginx/nginx.conf'
    """
    try:
        cmd = f"head -n {max_lines} {path} 2>/dev/null"
        result = await _run_ssh_command(cmd, connection_id)
        if result["exit_code"] != 0:
            return f"Fehler: Datei '{path}' nicht lesbar oder nicht vorhanden."
        return _truncate_output(result["output"], max_lines=max_lines)
    except Exception as e:
        return f"Fehler: {e}"


@tool
async def list_directory(path: str = "/var/log", connection_id: str = "") -> str:
    """
    Listet den Inhalt eines Verzeichnisses auf.
    Beispiel: path='/etc/nginx/sites-available'
    """
    try:
        cmd = f"ls -lah {path} 2>/dev/null"
        result = await _run_ssh_command(cmd, connection_id)
        if result["exit_code"] != 0:
            return f"Fehler: Verzeichnis '{path}' nicht lesbar."
        return _truncate_output(result["output"])
    except Exception as e:
        return f"Fehler: {e}"


# ═══════════════════════════════════════════════════════
# Netzwerk
# ═══════════════════════════════════════════════════════

@tool
async def get_network_info(connection_id: str = "") -> str:
    """Gibt Netzwerk-Informationen zurück (IP-Adressen, offene Ports, DNS)."""
    try:
        cmd = "ip -4 addr show | grep inet; echo '---'; ss -tlnp 2>/dev/null | head -20; echo '---'; cat /etc/resolv.conf | grep nameserver"
        result = await _run_ssh_command(cmd, connection_id)
        return _truncate_output(result["output"])
    except Exception as e:
        return f"Fehler: {e}"


@tool
async def check_port(host: str, port: int, connection_id: str = "") -> dict:
    """Prüft ob ein Port auf einem Host erreichbar ist (netcat oder /dev/tcp)."""
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
    """Listet alle Benutzer mit Login-Shell auf (/etc/passwd)."""
    try:
        cmd = "grep -v '/nologin\\|/false' /etc/passwd | cut -d: -f1,3,6,7 | column -t -s:"
        result = await _run_ssh_command(cmd, connection_id)
        return _truncate_output(result["output"])
    except Exception as e:
        return f"Fehler: {e}"


@tool
async def check_last_logins(count: int = 10, connection_id: str = "") -> str:
    """Zeigt die letzten Login-Versuche an (last)."""
    try:
        cmd = f"last -n {count} --time-format iso 2>/dev/null || last -n {count}"
        result = await _run_ssh_command(cmd, connection_id)
        return _truncate_output(result["output"], max_lines=count)
    except Exception as e:
        return f"Fehler: {e}"


# ═══════════════════════════════════════════════════════
# Steuerungs-Tools
# ═══════════════════════════════════════════════════════

@tool
async def reboot_server(connection_id: str = "") -> dict:
    """Startet den Server neu. DESTRUKTIV – erfordert explizite Bestätigung."""
    return {
        "action": "reboot",
        "status": "confirmation_required",
        "detail": "Soll der Server wirklich neu gestartet werden? Dies unterbricht alle laufenden Dienste! Bestätige mit 'Ja'.",
    }


@tool
async def confirm_reboot(connection_id: str = "") -> dict:
    """Bestätigte Server-Neustart. Nur nach expliziter User-Bestätigung aufrufen."""
    try:
        result = await _run_ssh_command("reboot", connection_id, timeout=5)
        return {"action": "reboot", "status": "success", "detail": "Neustart wurde eingeleitet."}
    except Exception:
        return {"action": "reboot", "status": "success", "detail": "Neustart wurde eingeleitet (Verbindung getrennt wie erwartet)."}
