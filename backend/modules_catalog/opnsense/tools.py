"""OPNsense module — LangGraph @tool functions."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import tool

from core.connections import ConnectionManager
from core.tls import get_connection_verify_arg
from core.vault import get_vault
from agents.base_agent import _t

logger = logging.getLogger("ninko.modules.opnsense.tools")


async def _get_opnsense_auth(connection_id: str = "") -> tuple:
    """
    Helper: loads auth data from ConnectionManager or environment variables.
    Returns: (host, (api_key, api_secret), verify_arg)
    """
    if connection_id:
        conn = await ConnectionManager.get_connection("opnsense", connection_id)
        if not conn:
            raise ValueError(
                f"OPNsense connection with ID '{connection_id}' not found."
            )
    else:
        conn = await ConnectionManager.get_default_connection("opnsense")

    if conn:
        host = conn.config.get("host", "")
        api_key = conn.config.get("api_key", "")
        api_secret = conn.config.get("api_secret", "")

        vault = get_vault()
        api_key_vk = conn.vault_keys.get("api_key")
        if api_key_vk:
            api_key = await vault.get_secret(api_key_vk) or api_key
        secret_vk = conn.vault_keys.get("OPNSENSE_API_SECRET")
        if secret_vk:
            api_secret = await vault.get_secret(secret_vk) or api_secret

        verify = await get_connection_verify_arg(conn, "opnsense", default_verify=True)
        return host, (api_key, api_secret), verify

    host = os.environ.get("OPNSENSE_HOST", "")
    api_key = os.environ.get("OPNSENSE_API_KEY", "")
    api_secret = os.environ.get("OPNSENSE_API_SECRET", "")

    if not host:
        raise ValueError(
            _t(
                de="Keine OPNsense-Verbindung konfiguriert. Bitte im Dashboard unter Einstellungen → Modul → Zahnrad eine Verbindung anlegen, oder die Env-Variablen OPNSENSE_HOST, OPNSENSE_API_KEY, OPNSENSE_API_SECRET setzen.",
                en="No OPNsense connection configured. Please create a connection in the dashboard under Settings → Module → gear icon, or set the environment variables OPNSENSE_HOST, OPNSENSE_API_KEY, OPNSENSE_API_SECRET.",
                fr="Aucune connexion OPNsense configurée. Veuillez créer une connexion dans le tableau de bord sous Paramètres → Module → icône d'engrenage, ou définir les variables d'environnement OPNSENSE_HOST, OPNSENSE_API_KEY, OPNSENSE_API_SECRET.",
                es="No hay conexión OPNsense configurada. Por favor cree una conexión en el panel bajo Configuración → Módulo → icono de engranaje, o establezca las variables de entorno OPNSENSE_HOST, OPNSENSE_API_KEY, OPNSENSE_API_SECRET.",
                it="Nessuna connessione OPNsense configurata. Per favore crea una connessione nel cruscotto sotto Impostazioni → Modulo → icona ingranaggio, o imposta le variabili di ambiente OPNSENSE_HOST, OPNSENSE_API_KEY, OPNSENSE_API_SECRET.",
                nl="Geen OPNsense-verbinding geconfigureerd. Maak een verbinding aan in het dashboard onder Instellingen → Module → tandwielpictogram, of stel de omgevingsvariabelen OPNSENSE_HOST, OPNSENSE_API_KEY, OPNSENSE_API_SECRET in.",
                pl="Nie skonfigurowano połączenia OPNsense. Utwórz połączenie w panelu w sekcji Ustawienia → Moduł → ikona koła zębatego lub ustaw zmienne środowiskowe OPNSENSE_HOST, OPNSENSE_API_KEY, OPNSENSE_API_SECRET.",
                pt="Nenhuma conexão OPNsense configurada. Por favor crie uma conexão no painel em Configurações → Módulo → ícone de engrenagem, ou defina as variáveis de ambiente OPNSENSE_HOST, OPNSENSE_API_KEY, OPNSENSE_API_SECRET.",
                ja="OPNSense接続が設定されていません。ダッシュボードで設定→モジュール→歯車アイコンから接続を作成するか、環境変数OPNSENSE_HOST、OPNSENSE_API_KEY、OPNSENSE_API_SECRETを設定してください。",
                zh="未配置OPNSense连接。请在仪表板中的设置→模块→齿轮图标下创建连接，或设置环境变量OPNSENSE_HOST、OPNSENSE_API_KEY、OPNSENSE_API_SECRET。",
            )
        )

    verify_ssl = os.environ.get("OPNSENSE_VERIFY_SSL", "true").lower() == "true"
    if verify_ssl:
        ca_path = os.environ.get("OPNSENSE_CA_CERT_PATH", "").strip()
        if ca_path:
            return host, (api_key, api_secret), ca_path
    return host, (api_key, api_secret), verify_ssl


async def _opnsense_request(
    endpoint: str,
    connection_id: str = "",
    method: str = "GET",
    json_data: dict | None = None,
) -> Any:
    """Sends a request to the OPNsense API."""
    host, auth, verify = await _get_opnsense_auth(connection_id)

    if not host:
        raise ValueError("No OPNsense host address provided.")

    url = f"https://{host}{endpoint}"

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=verify) as client:
            if method == "GET":
                resp = await client.get(url, auth=auth)
            elif method == "POST":
                resp = await client.post(url, auth=auth, json=json_data)
            elif method == "DELETE":
                resp = await client.delete(url, auth=auth)
            else:
                raise ValueError(f"Unsupported method: {method}")

            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        logger.error("OPNsense API Error: %s", e)
        raise ValueError(f"OPNsense API error: {e}")


@tool
async def get_opnsense_system_status(connection_id: str = "") -> Dict:
    """
    Retrieves the system status of the OPNsense firewall (version, uptime, CPU, RAM, disk).
    Use this tool to get general system information about the OPNsense firewall.
    """
    try:
        host, _, _ = await _get_opnsense_auth(connection_id)

        time_data, fw_data, mem_data, disk_data = await asyncio.gather(
            _opnsense_request("/api/diagnostics/system/systemTime", connection_id),
            _opnsense_request("/api/core/firmware/info", connection_id),
            _opnsense_request("/api/diagnostics/system/systemResources", connection_id),
            _opnsense_request("/api/diagnostics/system/systemDisk", connection_id),
        )

        mem = mem_data.get("memory", {})
        mem_total = int(mem.get("total") or 1)
        mem_used = int(mem.get("used") or 0)
        mem_pct = round(mem_used / mem_total * 100)

        devices = disk_data.get("devices", [])
        disk_pct = devices[0].get("used_pct", 0) if devices else 0

        loadavg = time_data.get("loadavg", "0, 0, 0")
        load_1m = float(loadavg.split(",")[0].strip()) if loadavg else 0.0

        return {
            "version": fw_data.get("product_version", ""),
            "firmware": fw_data.get("product_id", "OPNsense"),
            "uptime": time_data.get("uptime", ""),
            "cpu": load_1m,
            "memory": mem_pct,
            "disk": disk_pct,
            "host": host,
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to retrieve OPNsense system status: %s", e)
        return {"error": str(e)}


@tool
async def get_opnsense_interfaces(connection_id: str = "") -> List[Dict]:
    """
    Retrieves all network interfaces of the OPNsense firewall (LAN, WAN, OPT, etc.).
    Use this tool to get network interface information (IP, MAC, status).
    """
    try:
        result = await _opnsense_request(
            "/api/interfaces/overview/interfacesInfo",
            connection_id,
            method="POST",
            json_data={},
        )
        interfaces = result.get("rows", [])

        return [
            {
                "name": iface.get("device", ""),
                "descr": iface.get("description", ""),
                "ipaddr": iface.get("addr4", ""),
                "ipv6": iface.get("addr6", ""),
                "macaddr": iface.get("macaddr", ""),
                "status": iface.get("status", ""),
                "media": iface.get("media", ""),
                "enabled": iface.get("enabled", False),
            }
            for iface in interfaces
        ]
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to retrieve OPNsense interfaces: %s", e)
        return [{"error": str(e)}]


@tool
async def get_opnsense_gateways(connection_id: str = "") -> List[Dict]:
    """
    Retrieves the status of all gateways (name, IP, status, latency).
    Use this tool to check gateway status and latency.
    """
    try:
        result = await _opnsense_request("/api/routes/gateway/status", connection_id)
        gateways = result.get("gateways", [])

        return [
            {
                "name": gw.get("name", ""),
                "ip": gw.get("ip", ""),
                "status": gw.get("status", ""),
                "rtt": gw.get("rtt"),
                "rttdev": gw.get("rttdev"),
            }
            for gw in gateways
        ]
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to retrieve OPNsense gateways: %s", e)
        return [{"error": str(e)}]


@tool
async def get_opnsense_firewall_rules(
    connection_id: str = "", interface: str = ""
) -> List[Dict]:
    """
    Retrieves firewall rules. Optionally filtered by interface (e.g. 'wan', 'lan').
    Use this tool to list active firewall rules.
    """
    try:
        result = await _opnsense_request(
            "/api/firewall/filter/searchRule", connection_id
        )
        rules = result.get("rows", [])

        if interface:
            rules = [
                r for r in rules if interface.lower() in r.get("interface", "").lower()
            ]

        return [
            {
                "uuid": r.get("uuid", ""),
                "sequence": r.get("sequence"),
                "enabled": r.get("enabled"),
                "action": r.get("action"),
                "interface": r.get("interface"),
                "protocol": r.get("protocol"),
                "source": r.get("source"),
                "destination": r.get("destination"),
                "descr": r.get("descr"),
            }
            for r in rules[:50]
        ]
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to retrieve OPNsense firewall rules: %s", e)
        return [{"error": str(e)}]


@tool
async def get_opnsense_nat_rules(connection_id: str = "") -> List[Dict]:
    """
    Retrieves NAT rules (port forwarding, outbound NAT).
    Use this tool to list NAT rules.
    """
    try:
        result = await _opnsense_request(
            "/api/firewall/filter/searchRule?type=nat", connection_id
        )
        rules = result.get("rows", [])

        return [
            {
                "uuid": r.get("uuid", ""),
                "sequence": r.get("sequence"),
                "enabled": r.get("enabled"),
                "interface": r.get("interface"),
                "protocol": r.get("protocol"),
                "source": r.get("source"),
                "destination": r.get("destination"),
                "target": r.get("target"),
                "target_port": r.get("target_port"),
                "descr": r.get("descr"),
            }
            for r in rules[:50]
        ]
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to retrieve OPNsense NAT rules: %s", e)
        return [{"error": str(e)}]


@tool
async def get_opnsense_services(connection_id: str = "") -> List[Dict]:
    """
    Retrieves the status of all services (DHCP, DNS, VPN, etc.).
    Use this tool to check which services are running.
    """
    try:
        result = await _opnsense_request("/api/core/service/search", connection_id)
        services = result.get("rows", [])

        return [
            {
                "name": s.get("name", ""),
                "description": s.get("description", ""),
                "running": bool(s.get("running", 0)),
                "locked": bool(s.get("locked", 0)),
            }
            for s in services
        ]
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to retrieve OPNsense services: %s", e)
        return [{"error": str(e)}]


@tool
async def get_opnsense_dhcp_leases(connection_id: str = "") -> List[Dict]:
    """
    Retrieves current DHCP leases (assigned IP addresses).
    Use this tool to see DHCP leases and connected devices.
    """
    try:
        result = await _opnsense_request(
            "/api/dhcpv4/leases/searchLease", connection_id
        )
        leases = result.get("rows", [])

        return [
            {
                "ip": lease.get("ip", ""),
                "mac": lease.get("mac", ""),
                "hostname": lease.get("hostname"),
                "starts": lease.get("starts"),
                "ends": lease.get("ends"),
                "state": lease.get("state"),
            }
            for lease in leases
        ]
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to retrieve OPNsense DHCP leases: %s", e)
        return [{"error": str(e)}]


@tool
async def create_opnsense_firewall_rule(
    interface: str,
    action: str,
    protocol: str,
    source: str,
    destination: str,
    description: str = "",
    connection_id: str = "",
) -> str:
    """
    Creates a new firewall rule on OPNsense.
    Use this tool to add a firewall rule. Requires confirmation.
    """
    try:
        payload = {
            "rule": {
                "interface": interface,
                "action": action,
                "protocol": protocol,
                "source": source,
                "destination": destination,
                "descr": description,
                "enabled": "1",
            }
        }
        result = await _opnsense_request(
            "/api/firewall/filter/addRule",
            connection_id,
            method="POST",
            json_data=payload,
        )
        if result.get("status") == "ok":
            return _t(
                de=f"Firewall-Regel erstellt: {description}",
                en=f"Firewall rule created: {description}",
                fr=f"Règle de pare-feu créée: {description}",
                es=f"Regla de firewall creada: {description}",
                it=f"Regola firewall creata: {description}",
                nl=f"Firewall-regel aangemaakt: {description}",
                pl=f"Utworzono regułę firewall: {description}",
                pt=f"Regra de firewall criada: {description}",
                ja=f"ファイアウォールルールを作成しました: {description}",
                zh=f"已创建防火墙规则: {description}",
            )
        return _t(
            de=f"Fehler beim Erstellen der Regel: {result}",
            en=f"Error creating rule: {result}",
            fr=f"Erreur lors de la création de la règle: {result}",
            es=f"Error al crear la regla: {result}",
            it=f"Errore durante la creazione della regola: {result}",
            nl=f"Fout bij het aanmaken van de regel: {result}",
            pl=f"Błąd podczas tworzenia reguły: {result}",
            pt=f"Erro ao criar a regra: {result}",
            ja=f"ルール作成エラー: {result}",
            zh=f"创建规则错误: {result}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to create OPNsense firewall rule: %s", e)
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
async def delete_opnsense_firewall_rule(rule_uuid: str, connection_id: str = "") -> str:
    """
    Deletes a firewall rule by UUID. Use this tool to remove a firewall rule. Requires confirmation.
    """
    try:
        result = await _opnsense_request(
            f"/api/firewall/filter/deleteRule/{rule_uuid}", connection_id, method="POST"
        )
        if result.get("status") == "ok":
            return _t(
                de=f"Firewall-Regel {rule_uuid} gelöscht.",
                en=f"Firewall rule {rule_uuid} deleted.",
                fr=f"Règle de pare-feu {rule_uuid} supprimée.",
                es=f"Regla de firewall {rule_uuid} eliminada.",
                it=f"Regola firewall {rule_uuid} eliminata.",
                nl=f"Firewall-regel {rule_uuid} verwijderd.",
                pl=f"Reguła firewall {rule_uuid} usunięta.",
                pt=f"Regra de firewall {rule_uuid} excluída.",
                ja=f"ファイアウォールルール {rule_uuid} を削除しました。",
                zh=f"已删除防火墙规则 {rule_uuid}。",
            )
        return _t(
            de=f"Fehler beim Löschen der Regel: {result}",
            en=f"Error deleting rule: {result}",
            fr=f"Erreur lors de la suppression de la règle: {result}",
            es=f"Error al eliminar la regla: {result}",
            it=f"Errore durante l'eliminazione della regola: {result}",
            nl=f"Fout bij het verwijderen van de regel: {result}",
            pl=f"Błąd podczas usuwania reguły: {result}",
            pt=f"Erro ao excluir a regra: {result}",
            ja=f"ルール削除エラー: {result}",
            zh=f"删除规则错误: {result}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to delete OPNsense firewall rule: %s", e)
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
async def create_opnsense_nat_rule(
    interface: str,
    protocol: str,
    source: str,
    destination: str,
    target: str,
    target_port: str,
    description: str = "",
    connection_id: str = "",
) -> str:
    """
    Creates a new NAT rule (port forwarding) on OPNsense.
    Use this tool to add a NAT rule. Requires confirmation.
    """
    try:
        payload = {
            "rule": {
                "interface": interface,
                "protocol": protocol,
                "source": source,
                "destination": destination,
                "target": target,
                "target_port": target_port,
                "descr": description,
                "enabled": "1",
            }
        }
        result = await _opnsense_request(
            "/api/firewall/filter/addRule",
            connection_id,
            method="POST",
            json_data=payload,
        )
        if result.get("status") == "ok":
            return _t(
                de=f"NAT-Regel erstellt: {description}",
                en=f"NAT rule created: {description}",
                fr=f"Règle NAT créée: {description}",
                es=f"Regla NAT creada: {description}",
                it=f"Regola NAT creata: {description}",
                nl=f"NAT-regel aangemaakt: {description}",
                pl=f"Utworzono regułę NAT: {description}",
                pt=f"Regra NAT criada: {description}",
                ja=f"NATルールを作成しました: {description}",
                zh=f"已创建NAT规则: {description}",
            )
        return _t(
            de=f"Fehler beim Erstellen der NAT-Regel: {result}",
            en=f"Error creating NAT rule: {result}",
            fr=f"Erreur lors de la création de la règle NAT: {result}",
            es=f"Error al crear la regla NAT: {result}",
            it=f"Errore durante la creazione della regola NAT: {result}",
            nl=f"Fout bij het aanmaken van de NAT-regel: {result}",
            pl=f"Błąd podczas tworzenia reguły NAT: {result}",
            pt=f"Erro ao criar a regra NAT: {result}",
            ja=f"NATルール作成エラー: {result}",
            zh=f"创建NAT规则错误: {result}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to create OPNsense NAT rule: %s", e)
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
async def delete_opnsense_nat_rule(rule_uuid: str, connection_id: str = "") -> str:
    """
    Deletes a NAT rule by UUID. Use this tool to remove a NAT rule. Requires confirmation.
    """
    try:
        result = await _opnsense_request(
            f"/api/firewall/filter/deleteRule/{rule_uuid}", connection_id, method="POST"
        )
        if result.get("status") == "ok":
            return _t(
                de=f"NAT-Regel {rule_uuid} gelöscht.",
                en=f"NAT rule {rule_uuid} deleted.",
                fr=f"Règle NAT {rule_uuid} supprimée.",
                es=f"Regla NAT {rule_uuid} eliminada.",
                it=f"Regola NAT {rule_uuid} eliminata.",
                nl=f"NAT-regel {rule_uuid} verwijderd.",
                pl=f"Reguła NAT {rule_uuid} usunięta.",
                pt=f"Regra NAT {rule_uuid} excluída.",
                ja=f"NATルール {rule_uuid} を削除しました。",
                zh=f"已删除NAT规则 {rule_uuid}。",
            )
        return _t(
            de=f"Fehler beim Löschen der NAT-Regel: {result}",
            en=f"Error deleting NAT rule: {result}",
            fr=f"Erreur lors de la suppression de la règle NAT: {result}",
            es=f"Error al eliminar la regla NAT: {result}",
            it=f"Errore durante l'eliminazione della regola NAT: {result}",
            nl=f"Fout bij het verwijderen van de NAT-regel: {result}",
            pl=f"Błąd podczas usuwania reguły NAT: {result}",
            pt=f"Erro ao excluir a regra NAT: {result}",
            ja=f"NATルール削除エラー: {result}",
            zh=f"删除NAT规则错误: {result}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to delete OPNsense NAT rule: %s", e)
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
async def restart_opnsense_service(service_name: str, connection_id: str = "") -> str:
    """
    Restarts an OPNsense service (e.g. 'unbound', 'dhcpd', 'openvpn').
    Use this tool to restart a service on OPNsense.
    """
    try:
        result = await _opnsense_request(
            f"/api/core/service/restart/{service_name}", connection_id, method="POST"
        )

        if result.get("status") == "ok":
            return _t(
                de=f"Service '{service_name}' wurde neu gestartet.",
                en=f"Service '{service_name}' has been restarted.",
                fr=f"Le service '{service_name}' a été redémarré.",
                es=f"El servicio '{service_name}' ha sido reiniciado.",
                it=f"Il servizio '{service_name}' è stato riavviato.",
                nl=f"Service '{service_name}' is opnieuw gestart.",
                pl=f"Usługa '{service_name}' została ponownie uruchomiona.",
                pt=f"O serviço '{service_name}' foi reiniciado.",
                ja=f"サービス '{service_name}' を再起動しました。",
                zh=f"服务 '{service_name}' 已重启。",
            )
        return _t(
            de=f"Fehler beim Neustart: {result}",
            en=f"Restart failed: {result}",
            fr=f"Échec du redémarrage: {result}",
            es=f"Error al reiniciar: {result}",
            it=f"Riavvio non riuscito: {result}",
            nl=f"Herstart mislukt: {result}",
            pl=f"Błąd podczas ponownego uruchamiania: {result}",
            pt=f"Falha ao reiniciar: {result}",
            ja=f"再起動に失敗しました: {result}",
            zh=f"重启失败: {result}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to restart OPNsense service: %s", e)
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
async def get_opnsense_logs(lines: int = 50, connection_id: str = "") -> List[Dict]:
    """
    Retrieves firewall logs (latest entries).
    Use this tool to see firewall logs.
    """
    try:
        result = await _opnsense_request("/api/diagnostics/firewall/log", connection_id)
        # API returns a list directly
        entries = result if isinstance(result, list) else result.get("rows", [])

        return [
            {
                "timestamp": e.get("__timestamp__", ""),
                "action": e.get("action", ""),
                "interface": e.get("interface", ""),
                "src": e.get("src", ""),
                "dst": e.get("dst", ""),
                "srcport": e.get("srcport", ""),
                "dstport": e.get("dstport", ""),
                "proto": e.get("protoname", ""),
                "label": e.get("label", ""),
            }
            for e in entries[:lines]
        ]
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to retrieve OPNsense logs: %s", e)
        return [{"error": str(e)}]


@tool
async def set_opnsense_interface(
    interface: str,
    enabled: bool = True,
    ip_address: str = "",
    subnet_mask: int = 24,
    connection_id: str = "",
) -> str:
    """
    Configure network interface settings on OPNsense.
    Use this tool to enable/disable an interface or set its IP address.

    Args:
        interface: Interface name (e.g., 'opt1', 'opt2', 'lan', 'wan')
        enabled: Enable or disable the interface
        ip_address: IPv4 address (optional, for static IP)
        subnet_mask: Subnet mask in CIDR notation (default: 24)
        connection_id: Optional connection ID
    """
    try:
        interface_map = {
            "lan": "lan",
            "wan": "wan",
            "opt1": "opt1",
            "opt2": "opt2",
            "opt3": "opt3",
            "opt4": "opt4",
            "opt5": "opt5",
        }
        iface_key = interface_map.get(interface.lower(), interface)

        payload = {
            "interface": iface_key,
            "enable": "1" if enabled else "0",
        }

        if ip_address:
            payload["ipaddr"] = ip_address
            payload["subnet"] = str(subnet_mask)

        result = await _opnsense_request(
            "/api/interfaces/v Interfaces/set",
            connection_id,
            method="POST",
            json_data=payload,
        )

        if result.get("status") == "ok":
            return _t(
                de=f"Interface '{interface}' konfiguriert: {'aktiviert' if enabled else 'deaktiviert'}{f', IP: {ip_address}/{subnet_mask}' if ip_address else ''}",
                en=f"Interface '{interface}' configured: {'enabled' if enabled else 'disabled'}{f', IP: {ip_address}/{subnet_mask}' if ip_address else ''}",
                fr=f"Interface '{interface}' configurée: {'activée' if enabled else 'désactivée'}{f', IP: {ip_address}/{subnet_mask}' if ip_address else ''}",
                es=f"Interfaz '{interface}' configurada: {'habilitada' if enabled else 'deshabilitada'}{f', IP: {ip_address}/{subnet_mask}' if ip_address else ''}",
                it=f"Interfaccia '{interface}' configurata: {'abilitata' if enabled else 'disabilitata'}{f', IP: {ip_address}/{subnet_mask}' if ip_address else ''}",
                nl=f"Interface '{interface}' geconfigureerd: {'ingeschakeld' if enabled else 'uitgeschakeld'}{f', IP: {ip_address}/{subnet_mask}' if ip_address else ''}",
                pl=f"Interfejs '{interface}' skonfigurowany: {'włączony' if enabled else 'wyłączony'}{f', IP: {ip_address}/{subnet_mask}' if ip_address else ''}",
                pt=f"Interface '{interface}' configurado: {'ativado' if enabled else 'desativado'}{f', IP: {ip_address}/{subnet_mask}' if ip_address else ''}",
                ja=f"インターフェース '{interface}' が設定されました: {'有効' if enabled else '無効'}{f', IP: {ip_address}/{subnet_mask}' if ip_address else ''}",
                zh=f"接口 '{interface}' 已配置: {'启用' if enabled else '禁用'}{f', IP: {ip_address}/{subnet_mask}' if ip_address else ''}",
            )

        return _t(
            de=f"Fehler beim Konfigurieren von Interface '{interface}'",
            en=f"Error configuring interface '{interface}'",
            fr=f"Erreur lors de la configuration de l'interface '{interface}'",
            es=f"Error al configurar la interfaz '{interface}'",
            it=f"Errore durante la configurazione dell'interfaccia '{interface}'",
            nl=f"Fout bij het configureren van interface '{interface}'",
            pl=f"Błąd podczas konfigurowania interfejsu '{interface}'",
            pt=f"Erro ao configurar a interface '{interface}'",
            ja=f"インターフェース '{interface}' の設定中にエラーが発生しました",
            zh=f"配置接口 '{interface}' 时出错",
        )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to configure OPNsense interface: %s", e)
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
async def get_opnsense_dhcp_settings(
    interface: str = "lan",
    connection_id: str = "",
) -> Dict:
    """
    Get DHCP server settings for a specific interface on OPNsense.
    Use this tool to retrieve DHCP configuration (range, enable/disable).
    """
    try:
        result = await _opnsense_request(
            f"/api/dhcpv4/settings/{interface}",
            connection_id,
            method="GET",
        )

        settings = result.get(interface, {})
        return {
            "interface": interface,
            "enabled": settings.get("enable", False),
            "range_start": settings.get("range", {}).get("from", ""),
            "range_end": settings.get("range", {}).get("to", ""),
            "default_lease": settings.get("defaultleasetime", ""),
            "max_lease": settings.get("maxleasetime", ""),
            "dns_servers": settings.get("dnsserver", []),
            "domain": settings.get("domain", ""),
            "gateway": settings.get("gateway", ""),
        }

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to retrieve OPNsense DHCP settings: %s", e)
        return {"error": str(e)}


@tool
async def set_opnsense_dhcp(
    interface: str = "lan",
    enabled: bool = True,
    range_start: str = "",
    range_end: str = "",
    dns_servers: str = "",
    gateway: str = "",
    connection_id: str = "",
) -> str:
    """
    Configure DHCP server on OPNsense.
    Use this tool to enable/disable DHCP and set the IP range.
    """
    try:
        interface_map = {
            "lan": "lan",
            "wan": "wan",
            "opt1": "opt1",
            "opt2": "opt2",
            "opt3": "opt3",
            "opt4": "opt4",
            "opt5": "opt5",
        }
        iface_key = interface_map.get(interface.lower(), interface)

        range_from = range_start if range_start else "192.168.1.100"
        range_to = range_end if range_end else "192.168.1.200"

        payload = {
            iface_key: {
                "enable": "1" if enabled else "0",
                "range": {"from": range_from, "to": range_to},
            }
        }

        if dns_servers:
            payload[iface_key]["dnsserver"] = dns_servers.split(",")
        if gateway:
            payload[iface_key]["gateway"] = gateway

        result = await _opnsense_request(
            f"/api/dhcpv4/settings/{iface_key}/set",
            connection_id,
            method="POST",
            json_data=payload,
        )

        if result.get("status") == "ok":
            return _t(
                de=f"DHCP für '{interface}' konfiguriert: {'aktiviert' if enabled else 'deaktiviert'}, Range: {range_from} - {range_to}",
                en=f"DHCP configured for '{interface}': {'enabled' if enabled else 'disabled'}, Range: {range_from} - {range_to}",
                fr=f"DHCP configuré pour '{interface}': {'activé' if enabled else 'désactivé'}, Plage: {range_from} - {range_to}",
                es=f"DHCP configurado para '{interface}': {'habilitado' if enabled else 'deshabilitado'}, Rango: {range_from} - {range_to}",
                it=f"DHCP configurato per '{interface}': {'abilitato' if enabled else 'disabilitato'}, Range: {range_from} - {range_to}",
                nl=f"DHCP geconfigureerd voor '{interface}': {'ingeschakeld' if enabled else 'uitgeschakeld'}, Bereik: {range_from} - {range_to}",
                pl=f"DHCP skonfigurowany dla '{interface}': {'włączony' if enabled else 'wyłączony'}, Zakres: {range_from} - {range_to}",
                pt=f"DHCP configurado para '{interface}': {'ativado' if enabled else 'desativado'}, Intervalo: {range_from} - {range_to}",
                ja=f"'{interface}' のDHCPが設定されました: {'有効' if enabled else '無効'}、範囲: {range_from} - {range_to}",
                zh=f"'{interface}' 的DHCP已配置: {'启用' if enabled else '禁用'}，范围: {range_from} - {range_to}",
            )

        return _t(
            de=f"Fehler beim Konfigurieren von DHCP für '{interface}'",
            en=f"Error configuring DHCP for '{interface}'",
            fr=f"Erreur lors de la configuration du DHCP pour '{interface}'",
            es=f"Error al configurar DHCP para '{interface}'",
            it=f"Errore durante la configurazione del DHCP per '{interface}'",
            nl=f"Fout bij het configureren van DHCP voor '{interface}'",
            pl=f"Błąd podczas konfigurowania DHCP dla '{interface}'",
            pt=f"Erro ao configurar DHCP para '{interface}'",
            ja=f"'{interface}' のDHCP設定中にエラーが発生しました",
            zh=f"配置 '{interface}' 的DHCP时出错",
        )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to configure OPNsense DHCP: %s", e)
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
async def get_opnsense_virtual_ips(connection_id: str = "") -> List[Dict]:
    """
    Get virtual IPs (CARP, proxy ARP, other) on OPNsense.
    Use this tool to see configured virtual IP addresses.
    """
    try:
        result = await _opnsense_request(
            "/api/firewall/virtual_ip/search",
            connection_id,
            method="GET",
        )

        vips = result.get("rows", [])
        return [
            {
                "mode": vip.get("mode", ""),
                "interface": vip.get("interface", ""),
                "address": vip.get("address", ""),
                "description": vip.get("descr", ""),
                "uuid": vip.get("uuid", ""),
            }
            for vip in vips
        ]

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to retrieve OPNsense virtual IPs: %s", e)
        return [{"error": str(e)}]


@tool
async def create_opnsense_virtual_ip(
    mode: str,
    interface: str,
    address: str,
    description: str = "",
    connection_id: str = "",
) -> str:
    """
    Create a virtual IP (CARP, proxy ARP, etc.) on OPNsense.
    Use this tool to add a virtual IP address for HA/load balancing.
    """
    try:
        interface_map = {
            "lan": "lan",
            "wan": "wan",
            "opt1": "opt1",
            "opt2": "opt2",
            "opt3": "opt3",
            "opt4": "opt4",
            "opt5": "opt5",
        }
        iface_key = interface_map.get(interface.lower(), interface)

        payload = {
            "virtualip": {
                "mode": mode,
                "interface": iface_key,
                "address": address,
                "descr": description,
            }
        }

        result = await _opnsense_request(
            "/api/firewall/virtual_ip/add",
            connection_id,
            method="POST",
            json_data=payload,
        )

        if result.get("status") == "ok":
            return _t(
                de=f"Virtuelle IP erstellt: {address} ({mode}) auf {interface}",
                en=f"Virtual IP created: {address} ({mode}) on {interface}",
                fr=f"IP virtuelle créée: {address} ({mode}) sur {interface}",
                es=f"IP virtual creada: {address} ({mode}) en {interface}",
                it=f"IP virtuale creata: {address} ({mode}) su {interface}",
                nl=f"Virtueel IP aangemaakt: {address} ({mode}) op {interface}",
                pl=f"Utworzono wirtualny adres IP: {address} ({mode}) na {interface}",
                pt=f"IP virtual criado: {address} ({mode}) em {interface}",
                ja=f"仮想IPが作成されました: {address} ({mode}) ({interface} 上)",
                zh=f"虚拟IP已创建: {address} ({mode}) 于 {interface}",
            )

        return _t(
            de=f"Fehler beim Erstellen der virtuellen IP '{address}'",
            en=f"Error creating virtual IP '{address}'",
            fr=f"Erreur lors de la création de l'IP virtuelle '{address}'",
            es=f"Error al crear la IP virtual '{address}'",
            it=f"Errore durante la creazione dell'IP virtuale '{address}'",
            nl=f"Fout bij het aanmaken van virtueel IP '{address}'",
            pl=f"Błąd podczas tworzenia wirtualnego IP '{address}'",
            pt=f"Erro ao criar IP virtual '{address}'",
            ja=f"仮想IP '{address}' の作成中にエラーが発生しました",
            zh=f"创建虚拟IP '{address}' 时出错",
        )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to create OPNsense virtual IP: %s", e)
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
async def delete_opnsense_virtual_ip(
    vip_uuid: str,
    connection_id: str = "",
) -> str:
    """
    Delete a virtual IP on OPNsense by UUID.
    Use this tool to remove a virtual IP address.
    """
    try:
        result = await _opnsense_request(
            f"/api/firewall/virtual_ip/del/{vip_uuid}",
            connection_id,
            method="POST",
        )

        if result.get("status") == "ok":
            return _t(
                de=f"Virtuelle IP gelöscht: UUID {vip_uuid}",
                en=f"Virtual IP deleted: UUID {vip_uuid}",
                fr=f"IP virtuelle supprimée: UUID {vip_uuid}",
                es=f"IP virtual eliminada: UUID {vip_uuid}",
                it=f"IP virtuale eliminata: UUID {vip_uuid}",
                nl=f"Virtueel IP verwijderd: UUID {vip_uuid}",
                pl=f"Wirtualny IP usunięty: UUID {vip_uuid}",
                pt=f"IP virtual excluído: UUID {vip_uuid}",
                ja=f"仮想IPが削除されました: UUID {vip_uuid}",
                zh=f"虚拟IP已删除: UUID {vip_uuid}",
            )

        return _t(
            de=f"Fehler beim Löschen der virtuellen IP",
            en=f"Error deleting virtual IP",
            fr=f"Erreur lors de la suppression de l'IP virtuelle",
            es=f"Error al eliminar la IP virtual",
            it=f"Errore durante l'eliminazione dell'IP virtuale",
            nl=f"Fout bij het verwijderen van virtueel IP",
            pl=f"Błąd podczas usuwania wirtualnego IP",
            pt=f"Erro ao excluir IP virtual",
            ja=f"仮想IPの削除中にエラーが発生しました",
            zh=f"删除虚拟IP时出错",
        )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to delete OPNsense virtual IP: %s", e)
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
