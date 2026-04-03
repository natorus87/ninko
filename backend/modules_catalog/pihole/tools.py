"""Pi-hole module — tools for the AI agent. Uses Pi-hole v6 REST API with session-based auth."""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx
from langchain_core.tools import tool
from agents.base_agent import _t

logger = logging.getLogger("ninko.modules.pihole.tools")

# ── Session Cache ──────────────────────────────────
_session_cache: dict[str, dict] = {}  # url -> {"sid": str, "expires": float}
SESSION_TTL = 300  # 5 minutes


async def _get_pihole_config(connection_id: str = "") -> dict:
    """Load Pi-hole connection data from ConnectionManager, env, or Vault."""
    from core.connections import ConnectionManager
    from core.vault import get_vault
    import os
    
    vault = get_vault()

    if connection_id:
        conn = await ConnectionManager.get_default_connection("pihole") if connection_id == "default" else await ConnectionManager.get_connection("pihole", connection_id)
        if not conn:
            raise ValueError(f"Pi-hole connection with ID '{connection_id}' not found.")
            
        url = conn.config.get("url", "").rstrip("/")
        password = ""
        if "password" in conn.vault_keys:
            password = await vault.get_secret(conn.vault_keys["password"]) or ""
            
        return {"url": url, "password": password}

    # Try via ConnectionManager without ID (default)
    conn = await ConnectionManager.get_default_connection("pihole")
    if conn and conn.config.get("url"):
        url = conn.config.get("url", "").rstrip("/")
        password = ""
        if "password" in conn.vault_keys:
            password = await vault.get_secret(conn.vault_keys["password"]) or ""
        return {"url": url, "password": password}

    # FALLBACK: legacy env vars (from routes_settings)
    fallback_url = os.environ.get("PIHOLE_URL", "").rstrip("/")
    
    # If not in env vars, try loading directly from legacy settings in Redis
    if not fallback_url:
        try:
            from core.redis_client import get_redis
            import json
            redis = get_redis()
            raw = await redis.connection.get("ninko:settings:modules")
            if raw:
                overrides = json.loads(raw)
                conn_data = overrides.get("pihole", {}).get("connection", {})
                fallback_url = conn_data.get("PIHOLE_URL", "").rstrip("/")
        except Exception:
            pass

    if fallback_url:
        fallback_password = await vault.get_secret("PIHOLE_PASSWORD") or os.environ.get("PIHOLE_PASSWORD", "")
        return {"url": fallback_url, "password": fallback_password}

    raise ValueError(_t(
        "Keine Standard-Pi-hole-Verbindung konfiguriert (Verbitte den Nutzer im Dashboard unter 'Einstellungen -> Verbindungen' eine Pi-hole Verbindung anzulegen).",
        "No default Pi-hole connection configured (ask the user to create a Pi-hole connection in the dashboard under 'Settings -> Connections').",
    ))


async def _authenticate(base_url: str, password: str) -> str:
    """
    Pi-hole v6 session auth: POST /api/auth → sid.
    Caches the token for SESSION_TTL seconds.
    Handles 429 (api_seats_exceeded) via session cleanup.
    """
    import asyncio

    cache_key = base_url
    cached = _session_cache.get(cache_key)
    if cached and cached["expires"] > time.time():
        return cached["sid"]

    async with httpx.AsyncClient(timeout=10) as client:
        for attempt in range(3):
            resp = await client.post(
                f"{base_url}/api/auth",
                json={"password": password},
            )

            if resp.status_code == 429:
                body = resp.json() if resp.text else {}
                hint = body.get("error", {}).get("key", "")
                logger.warning(
                    "Pi-hole auth 429: %s (attempt %d/3)",
                    hint, attempt + 1,
                )

                # api_seats_exceeded → delete old session and retry
                if hint == "api_seats_exceeded" and cached:
                    try:
                        await client.delete(
                            f"{base_url}/api/auth",
                            headers={"sid": cached['sid']},
                        )
                        _session_cache.pop(cache_key, None)
                        cached = None
                    except Exception:
                        pass

                await asyncio.sleep(2 * (attempt + 1))
                continue

            if resp.status_code == 401:
                raise ValueError(_t(
                    "Pi-hole Auth fehlgeschlagen: falsches Passwort",
                    "Pi-hole auth failed: wrong password",
                ))

            resp.raise_for_status()
            data = resp.json()

            sid = data.get("session", {}).get("sid", "")
            if not sid:
                raise ValueError(_t(
                    "Pi-hole Auth fehlgeschlagen: kein SID erhalten",
                    "Pi-hole auth failed: no SID received",
                ))

            _session_cache[cache_key] = {
                "sid": sid,
                "expires": time.time() + SESSION_TTL,
            }
            logger.info("Pi-hole session created for %s", base_url)
            return sid

    raise ValueError(_t(
        "Pi-hole Auth fehlgeschlagen: zu viele Versuche (429)",
        "Pi-hole auth failed: too many attempts (429)",
    ))


async def _pihole_request(
    method: str,
    path: str,
    body: dict | None = None,
    params: dict | None = None,
    connection_id: str = "",
) -> dict:
    """
    Authenticated request to the Pi-hole API.
    Re-authenticates on 401.
    """
    config = await _get_pihole_config(connection_id)
    if not config["url"]:
        raise ValueError(_t(
            "Pi-hole nicht konfiguriert. Bitte URL und Passwort in den Modul-Einstellungen setzen.",
            "Pi-hole not configured. Please set URL and password in the module settings.",
        ))

    base_url = config["url"]
    sid = await _authenticate(base_url, config["password"])

    url = f"{base_url}/api{path}"
    headers = {"sid": sid}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.request(
            method, url, headers=headers, json=body, params=params
        )

        # Token expired → re-auth
        if resp.status_code == 401:
            _session_cache.pop(base_url, None)
            sid = await _authenticate(base_url, config["password"])
            headers["sid"] = sid
            resp = await client.request(
                method, url, headers=headers, json=body, params=params
            )

        resp.raise_for_status()

        if resp.text:
            return resp.json()
        return {}


# ── Tools ──────────────────────────────────────────

@tool
async def get_pihole_summary(connection_id: str = "") -> dict:
    """
    Pi-hole summary: blocked queries, percent blocked, total queries, status (enabled/disabled), clients.
    """
    data = await _pihole_request("GET", "/stats/summary", connection_id=connection_id)

    queries = data.get("queries", {})
    clients = data.get("clients", {})

    return {
        "status": "enabled" if data.get("gravity", {}).get("blocking") != "disabled" else "disabled",
        "dns_queries_today": queries.get("total", 0),
        "ads_blocked_today": queries.get("blocked", 0),
        "ads_percentage_today": round(queries.get("percent_blocked", 0), 1),
        "unique_domains": queries.get("unique_domains", 0),
        "queries_forwarded": queries.get("forwarded", 0),
        "queries_cached": queries.get("cached", 0),
        "clients_ever_seen": clients.get("total", 0),
        "unique_clients": clients.get("active", 0),
        "domains_blocked": data.get("gravity", {}).get("domains_being_blocked", 0),
    }


@tool
async def get_query_log(count: int = 100, connection_id: str = "") -> list[dict]:
    """
    Recent DNS queries from the Pi-hole query log.
    Shows domain, client, status (blocked/allowed/cached) and query type.

    Args:
        count: Number of entries (default: 100, max: 500)
    """
    count = min(count, 500)
    data = await _pihole_request("GET", "/queries", params={"length": count}, connection_id=connection_id)

    queries = data.get("queries", [])
    results = []
    for q in queries[:count]:
        results.append({
            "timestamp": q.get("time", 0),
            "type": q.get("type", ""),
            "domain": q.get("domain", ""),
            "client": q.get("client", {}).get("name", q.get("client", {}).get("ip", "")),
            "status": q.get("status", ""),
            "reply_type": q.get("reply", {}).get("type", ""),
            "duration_ms": q.get("reply", {}).get("time", 0),
        })
    return results


@tool
async def get_top_domains(count: int = 10, connection_id: str = "") -> dict:
    """
    Top permitted and blocked domains.

    Args:
        count: Number per category (default: 10)
    """
    data = await _pihole_request("GET", "/stats/top_domains", params={"count": count}, connection_id=connection_id)

    top_permitted = {}
    for entry in data.get("top_domains", []):
        top_permitted[entry.get("domain", "")] = entry.get("count", 0)

    data_blocked = await _pihole_request("GET", "/stats/top_domains", params={"count": count, "blocked": "true"}, connection_id=connection_id)

    top_blocked = {}
    for entry in data_blocked.get("top_domains", []):
        top_blocked[entry.get("domain", "")] = entry.get("count", 0)

    return {
        "top_permitted": top_permitted,
        "top_blocked": top_blocked,
    }


@tool
async def get_top_clients(count: int = 10, connection_id: str = "") -> dict:
    """
    Most active DNS clients (by query count).

    Args:
        count: Number of clients (default: 10)
    """
    data = await _pihole_request("GET", "/stats/top_clients", params={"count": count}, connection_id=connection_id)

    clients = {}
    for entry in data.get("top_clients", []):
        name = entry.get("name", "") or entry.get("ip", "")
        clients[name] = entry.get("count", 0)

    return {"top_clients": clients}


@tool
async def toggle_blocking(enable: bool = True, duration: int = 0, connection_id: str = "") -> str:
    """
    Enable or disable DNS blocking.
    When disabling, a duration in seconds can be specified (0 = permanent).

    Args:
        enable: True = enable blocking, False = disable
        duration: Duration of disable in seconds (0 = permanent, only when enable=False)
    """
    body = {"blocking": enable}
    if not enable and duration > 0:
        body["timer"] = duration

    await _pihole_request("POST", "/dns/blocking", body=body, connection_id=connection_id)

    if enable:
        return _t("DNS-Blocking aktiviert.", "DNS blocking enabled.")
    elif duration > 0:
        return _t(f"DNS-Blocking für {duration} Sekunden deaktiviert.", f"DNS blocking disabled for {duration} seconds.")
    else:
        return _t("DNS-Blocking dauerhaft deaktiviert.", "DNS blocking permanently disabled.")


@tool
async def get_blocklists(connection_id: str = "") -> list[dict]:
    """
    All configured blocklists (adlists) with status and domain count.
    """
    data = await _pihole_request("GET", "/lists", connection_id=connection_id)

    lists = []
    for entry in data.get("lists", []):
        lists.append({
            "id": entry.get("id", 0),
            "address": entry.get("address", ""),
            "enabled": entry.get("enabled", False),
            "comment": entry.get("comment", ""),
            "number": entry.get("number", 0),
        })
    return lists


@tool
async def add_domain_to_list(
    domain: str,
    list_type: str = "deny",
    kind: str = "exact",
    comment: str = "",
    connection_id: str = "",
) -> str:
    """
    Add a domain to the whitelist or blacklist.

    Args:
        domain: Domain name (e.g. 'example.com')
        list_type: 'allow' (whitelist) or 'deny' (blacklist)
        kind: 'exact' or 'regex'
        comment: Optional comment
    """
    if list_type not in ("allow", "deny"):
        return _t("Fehler: list_type muss 'allow' oder 'deny' sein.", "Error: list_type must be 'allow' or 'deny'.")
    if kind not in ("exact", "regex"):
        return _t("Fehler: kind muss 'exact' oder 'regex' sein.", "Error: kind must be 'exact' or 'regex'.")

    body = {
        "domain": domain,
        "comment": comment or f"Added via Ninko",
    }

    await _pihole_request("POST", f"/domains/{list_type}/{kind}", body=body, connection_id=connection_id)

    label = "Whitelist" if list_type == "allow" else "Blacklist"
    return _t(f"Domain '{domain}' zur {label} ({kind}) hinzugefügt.", f"Domain '{domain}' added to {label} ({kind}).")


@tool
async def remove_domain_from_list(
    domain: str,
    list_type: str = "deny",
    kind: str = "exact",
    connection_id: str = "",
) -> str:
    """
    Remove a domain from the whitelist or blacklist.

    Args:
        domain: Domain name
        list_type: 'allow' or 'deny'
        kind: 'exact' or 'regex'
    """
    if list_type not in ("allow", "deny"):
        return _t("Fehler: list_type muss 'allow' oder 'deny' sein.", "Error: list_type must be 'allow' or 'deny'.")
    if kind not in ("exact", "regex"):
        return _t("Fehler: kind muss 'exact' oder 'regex' sein.", "Error: kind must be 'exact' or 'regex'.")

    # Pi-hole v6: DELETE with domain in body or as path
    body = {"domain": domain}
    await _pihole_request("DELETE", f"/domains/{list_type}/{kind}", body=body, connection_id=connection_id)

    label = "Whitelist" if list_type == "allow" else "Blacklist"
    return _t(f"Domain '{domain}' von der {label} ({kind}) entfernt.", f"Domain '{domain}' removed from {label} ({kind}).")


@tool
async def get_pihole_system(connection_id: str = "") -> dict:
    """
    Pi-hole system information: version, uptime, gravity size, memory.
    """
    # Versions
    version_data = await _pihole_request("GET", "/info/version", connection_id=connection_id)
    # System
    try:
        system_data = await _pihole_request("GET", "/info/system", connection_id=connection_id)
    except Exception:
        system_data = {}
    # Gravity
    try:
        gravity_data = await _pihole_request("GET", "/info/gravity", connection_id=connection_id)
    except Exception:
        gravity_data = {}

    return {
        "version_core": version_data.get("core", {}).get("version", ""),
        "version_ftl": version_data.get("ftl", {}).get("version", ""),
        "version_web": version_data.get("web", {}).get("version", ""),
        "uptime": system_data.get("uptime", 0),
        "memory_usage": system_data.get("memory", {}).get("ram", {}).get("used_percent", 0),
        "cpu_temp": system_data.get("sensors", {}).get("cpu_temp", None),
        "gravity_size": gravity_data.get("domains_being_blocked", 0),
        "gravity_last_update": gravity_data.get("last_update", {}).get("absolute", ""),
    }


@tool
async def get_custom_dns_records(connection_id: str = "") -> dict:
    """
    Retrieve all local DNS entries (custom DNS hosts) from Pi-hole.
    Returns a dictionary with {Domain: IP}.
    """
    data = await _pihole_request("GET", "/config", connection_id=connection_id)
    hosts = []
    
    if "config" in data and "dns" in data["config"] and "hosts" in data["config"]["dns"]:
        hosts = data["config"]["dns"]["hosts"]
    elif "dns" in data and "hosts" in data["dns"]:
        # Fallback for other API response structures
        hosts = data["dns"]["hosts"]
        
    records = {}
    for entry in hosts:
        parts = str(entry).split(" ", 1)
        if len(parts) == 2:
            ip, domain = parts
            records[domain.strip()] = ip.strip()
            
    return {"custom_dns_records": records}


@tool
async def add_custom_dns_record(domain: str, ip: str, connection_id: str = "") -> str:
    """
    Add a new local DNS entry (custom DNS host).

    Args:
        domain: Domain name (e.g. 'service.local')
        ip: IP address the domain should resolve to (e.g. '192.168.1.100')
    """
    import urllib.parse
    
    # URL-encoded path for PUT request in v6: /api/config/dns/hosts/{IP}%20{domain}
    encoded_entry = urllib.parse.quote(f"{ip} {domain}")
    
    await _pihole_request("PUT", f"/config/dns/hosts/{encoded_entry}", connection_id=connection_id)
    
    return _t(f"Local DNS Eintrag hinzugefügt: {domain} -> {ip}", f"Local DNS entry added: {domain} -> {ip}")


@tool
async def remove_custom_dns_record(domain: str, ip: str, connection_id: str = "") -> str:
    """
    Delete a local DNS entry (custom DNS host) in Pi-hole.
    
    Args:
        domain: Domain name (e.g. 'service.local')
        ip: Assigned IP address of the entry (must match exactly)
    """
    import urllib.parse
    
    encoded_entry = urllib.parse.quote(f"{ip} {domain}")
    
    await _pihole_request("DELETE", f"/config/dns/hosts/{encoded_entry}", connection_id=connection_id)
    
    return _t(f"Local DNS Eintrag gelöscht: {domain} -> {ip}", f"Local DNS entry deleted: {domain} -> {ip}")


@tool
async def get_cname_records(connection_id: str = "") -> dict:
    """
    Retrieve all local CNAME records from Pi-hole.
    Returns a dictionary with {Domain: Target}.
    """
    data = await _pihole_request("GET", "/config", connection_id=connection_id)
    cnames = []
    if "config" in data and "dns" in data["config"] and "cnameRecords" in data["config"]["dns"]:
        cnames = data["config"]["dns"]["cnameRecords"]
    elif "dns" in data and "cnameRecords" in data["dns"]:
        cnames = data["dns"]["cnameRecords"]
        
    records = {}
    for entry in cnames:
        parts = str(entry).split(",", 1)
        if len(parts) == 2:
            records[parts[0].strip()] = parts[1].strip()
            
    return {"cname_records": records}


@tool
async def add_cname_record(domain: str, target: str, connection_id: str = "") -> str:
    """
    Add a new local CNAME record.
    
    Args:
        domain: Domain name (e.g. 'alias.local')
        target: Target the CNAME should point to (e.g. 'server.local')
    """
    import urllib.parse
    encoded_entry = urllib.parse.quote(f"{domain},{target}")
    await _pihole_request("PUT", f"/config/dns/cnameRecords/{encoded_entry}", connection_id=connection_id)
    return _t(f"CNAME Record hinzugefügt: {domain} -> {target}", f"CNAME record added: {domain} -> {target}")


@tool
async def remove_cname_record(domain: str, target: str, connection_id: str = "") -> str:
    """
    Delete a local CNAME record in Pi-hole.
    
    Args:
        domain: Domain name (e.g. 'alias.local')
        target: Assigned target (must match exactly)
    """
    import urllib.parse
    encoded_entry = urllib.parse.quote(f"{domain},{target}")
    await _pihole_request("DELETE", f"/config/dns/cnameRecords/{encoded_entry}", connection_id=connection_id)
    return _t(f"CNAME Record gelöscht: {domain} -> {target}", f"CNAME record deleted: {domain} -> {target}")


@tool
async def get_dhcp_leases(connection_id: str = "") -> list[dict]:
    """
    Retrieve all active DHCP leases from Pi-hole.
    Returns assigned IP addresses, MAC addresses and hostnames.
    """
    data = await _pihole_request("GET", "/dhcp/leases", connection_id=connection_id)
    return data.get("leases", [])


@tool
async def delete_dhcp_lease(ip: str, connection_id: str = "") -> str:
    """
    Delete an active DHCP lease by IP address.
    
    Args:
        ip: IP address whose lease should be deleted (e.g. '192.168.1.50')
    """
    await _pihole_request("DELETE", f"/dhcp/leases/{ip}", connection_id=connection_id)
    return _t(f"DHCP Lease für IP {ip} wurde gelöscht.", f"DHCP lease for IP {ip} has been deleted.")


@tool
async def update_gravity(connection_id: str = "") -> str:
    """
    Trigger a manual gravity update (download and refresh blocklists).
    This process may take a moment.
    """
    await _pihole_request("POST", "/action/gravity", connection_id=connection_id)
    return _t("Gravity-Update wurde erfolgreich gestartet.", "Gravity update started successfully.")


@tool
async def flush_dns_cache(connection_id: str = "") -> str:
    """
    Restart the DNS service on Pi-hole and flush the DNS cache.
    """
    await _pihole_request("POST", "/action/restartdns", connection_id=connection_id)
    return _t("DNS Server neu gestartet und Cache geleert.", "DNS server restarted and cache cleared.")


@tool
async def flush_logs(connection_id: str = "") -> str:
    """
    Delete/flush all query logs (FTL/DNS logs) in Pi-hole.
    """
    await _pihole_request("POST", "/action/flush/logs", connection_id=connection_id)
    return _t("Logs wurden erfolgreich gelöscht.", "Logs deleted successfully.")


@tool
async def flush_network_table(connection_id: str = "") -> str:
    """
    Flush the network table (ARP cache / known devices) in the Pi-hole database.
    """
    await _pihole_request("POST", "/action/flush/network", connection_id=connection_id)
    return _t("Netzwerktabelle wurde erfolgreich geleert.", "Network table flushed successfully.")


@tool
async def get_system_messages(connection_id: str = "") -> list[dict]:
    """
    Retrieve all active system warnings and messages (e.g. DNSMASQ_WARN) from Pi-hole.
    Returns message ID, type and message text.
    """
    data = await _pihole_request("GET", "/info/messages", connection_id=connection_id)
    return data.get("messages", [])


@tool
async def dismiss_system_message(message_id: str, connection_id: str = "") -> str:
    """
    Delete/dismiss a specific system warning in Pi-hole by ID.
    
    Args:
        message_id: ID of the message to delete.
    """
    await _pihole_request("DELETE", f"/info/messages/{message_id}", connection_id=connection_id)
    return _t(f"Systemmeldung mit ID {message_id} wurde gelöscht.", f"System message with ID {message_id} deleted.")

