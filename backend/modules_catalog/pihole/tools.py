"""
Pi-hole Modul – Tools für den AI-Agenten.
Nutzt die Pi-hole v6 REST API mit Session-basierter Authentifizierung.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import httpx
from langchain_core.tools import tool

logger = logging.getLogger("ninko.modules.pihole.tools")

# ── Session Cache ──────────────────────────────────
_session_cache: dict[str, dict] = {}  # url -> {"sid": str, "expires": float}
SESSION_TTL = 300  # 5 Minuten


async def _get_pihole_config(connection_id: str = "") -> dict:
    """Pi-hole Verbindungsdaten aus ConnectionManager, Env oder Vault laden."""
    from core.connections import ConnectionManager
    from core.vault import get_vault
    import os
    
    vault = get_vault()

    if connection_id:
        conn = await ConnectionManager.get_default_connection("pihole") if connection_id == "default" else await ConnectionManager.get_connection("pihole", connection_id)
        if not conn:
            raise ValueError(f"Pi-hole Verbindung mit ID '{connection_id}' nicht gefunden.")
            
        url = conn.config.get("url", "").rstrip("/")
        password = ""
        if "password" in conn.vault_keys:
            password = await vault.get_secret(conn.vault_keys["password"]) or ""
            
        return {"url": url, "password": password}

    # Versuch über ConnectionManager ohne ID (Default)
    conn = await ConnectionManager.get_default_connection("pihole")
    if conn and conn.config.get("url"):
        url = conn.config.get("url", "").rstrip("/")
        password = ""
        if "password" in conn.vault_keys:
            password = await vault.get_secret(conn.vault_keys["password"]) or ""
        return {"url": url, "password": password}

    # FALLBACK: Legacy Env Vars (aus routes_settings)
    fallback_url = os.environ.get("PIHOLE_URL", "").rstrip("/")
    
    # Wenn nicht in Env Vars, dann versuche es direkt aus den Legacy Settings im Redis zu laden
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

    raise ValueError("Keine Standard-Pi-hole-Verbindung konfiguriert (Verbitte den Nutzer im Dashboard unter 'Einstellungen -> Verbindungen' eine Pi-hole Verbindung anzulegen).")


async def _authenticate(base_url: str, password: str) -> str:
    """
    Pi-hole v6 Session-Auth: POST /api/auth → sid.
    Cached den Token für SESSION_TTL Sekunden.
    Behandelt 429 (api_seats_exceeded) durch Session-Cleanup.
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
                    "Pi-hole Auth 429: %s (Versuch %d/3)",
                    hint, attempt + 1,
                )

                # api_seats_exceeded → alte Session löschen und nochmal
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
                raise ValueError("Pi-hole Auth fehlgeschlagen: falsches Passwort")

            resp.raise_for_status()
            data = resp.json()

            sid = data.get("session", {}).get("sid", "")
            if not sid:
                raise ValueError("Pi-hole Auth fehlgeschlagen: kein SID erhalten")

            _session_cache[cache_key] = {
                "sid": sid,
                "expires": time.time() + SESSION_TTL,
            }
            logger.info("Pi-hole Session erstellt für %s", base_url)
            return sid

    raise ValueError("Pi-hole Auth fehlgeschlagen: zu viele Versuche (429)")


async def _pihole_request(
    method: str,
    path: str,
    body: dict | None = None,
    params: dict | None = None,
    connection_id: str = "",
) -> dict:
    """
    Authentifizierter Request an die Pi-hole API.
    Wiederholt Auth bei 401.
    """
    config = await _get_pihole_config(connection_id)
    if not config["url"]:
        raise ValueError(
            "Pi-hole nicht konfiguriert. "
            "Bitte URL und Passwort in den Modul-Einstellungen setzen."
        )

    base_url = config["url"]
    sid = await _authenticate(base_url, config["password"])

    url = f"{base_url}/api{path}"
    headers = {"sid": sid}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.request(
            method, url, headers=headers, json=body, params=params
        )

        # Token abgelaufen → re-auth
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
    Pi-hole Zusammenfassung: Blockierte Queries, Prozent blockiert,
    Gesamtanfragen, Status (aktiv/deaktiviert), Clients.
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
    Letzte DNS-Anfragen aus dem Pi-hole Query-Log.
    Zeigt Domain, Client, Status (blockiert/erlaubt/cached) und Anfragetyp.

    Args:
        count: Anzahl der Einträge (Standard: 100, Max: 500)
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
    Top erlaubte und blockierte Domains.

    Args:
        count: Anzahl pro Kategorie (Standard: 10)
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
    Die aktivsten DNS-Clients (nach Anzahl Anfragen).

    Args:
        count: Anzahl (Standard: 10)
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
    DNS-Blocking aktivieren oder deaktivieren.
    Bei Deaktivierung kann eine Dauer in Sekunden angegeben werden (0 = dauerhaft).

    Args:
        enable: True = Blocking aktivieren, False = deaktivieren
        duration: Dauer der Deaktivierung in Sekunden (0 = dauerhaft, nur bei enable=False)
    """
    body = {"blocking": enable}
    if not enable and duration > 0:
        body["timer"] = duration

    await _pihole_request("POST", "/dns/blocking", body=body, connection_id=connection_id)

    if enable:
        return "DNS-Blocking aktiviert."
    elif duration > 0:
        return f"DNS-Blocking für {duration} Sekunden deaktiviert."
    else:
        return "DNS-Blocking dauerhaft deaktiviert."


@tool
async def get_blocklists(connection_id: str = "") -> list[dict]:
    """
    Alle konfigurierten Blocklisten (Adlists) mit Status und Domainanzahl.
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
    Domain zur Whitelist oder Blacklist hinzufügen.

    Args:
        domain: Domain-Name (z.B. 'example.com')
        list_type: 'allow' (Whitelist) oder 'deny' (Blacklist)
        kind: 'exact' oder 'regex'
        comment: Optionaler Kommentar
    """
    if list_type not in ("allow", "deny"):
        return "Fehler: list_type muss 'allow' oder 'deny' sein."
    if kind not in ("exact", "regex"):
        return "Fehler: kind muss 'exact' oder 'regex' sein."

    body = {
        "domain": domain,
        "comment": comment or f"Hinzugefügt via Ninko",
    }

    await _pihole_request("POST", f"/domains/{list_type}/{kind}", body=body, connection_id=connection_id)

    label = "Whitelist" if list_type == "allow" else "Blacklist"
    return f"Domain '{domain}' zur {label} ({kind}) hinzugefügt."


@tool
async def remove_domain_from_list(
    domain: str,
    list_type: str = "deny",
    kind: str = "exact",
    connection_id: str = "",
) -> str:
    """
    Domain von der Whitelist oder Blacklist entfernen.

    Args:
        domain: Domain-Name
        list_type: 'allow' oder 'deny'
        kind: 'exact' oder 'regex'
    """
    if list_type not in ("allow", "deny"):
        return "Fehler: list_type muss 'allow' oder 'deny' sein."
    if kind not in ("exact", "regex"):
        return "Fehler: kind muss 'exact' oder 'regex' sein."

    # Pi-hole v6: DELETE mit domain im Body oder als Path
    body = {"domain": domain}
    await _pihole_request("DELETE", f"/domains/{list_type}/{kind}", body=body, connection_id=connection_id)

    label = "Whitelist" if list_type == "allow" else "Blacklist"
    return f"Domain '{domain}' von der {label} ({kind}) entfernt."


@tool
async def get_pihole_system(connection_id: str = "") -> dict:
    """
    Pi-hole System-Informationen: Version, Uptime, Gravity-Größe, Speicher.
    """
    # Versionen
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
    Ruft alle Local DNS Einträge (Custom DNS Hosts) aus dem Pi-hole ab.
    Gibt ein Dictionary mit {Domain: IP} zurück.
    """
    data = await _pihole_request("GET", "/config", connection_id=connection_id)
    hosts = []
    
    if "config" in data and "dns" in data["config"] and "hosts" in data["config"]["dns"]:
        hosts = data["config"]["dns"]["hosts"]
    elif "dns" in data and "hosts" in data["dns"]:
        # Fallback für andere API-Response-Strukturen
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
    Fügt einen neuen Local DNS Eintrag (Custom DNS Host) hinzu.
    
    Args:
        domain: Der Domain-Name (z.B. 'service.local')
        ip: Die IP-Adresse, auf die die Domain zeigen soll (z.B. '192.168.1.100')
    """
    import urllib.parse
    
    # URL encoded Pfad für PUT Request bei v6: /api/config/dns/hosts/{IP}%20{domain}
    encoded_entry = urllib.parse.quote(f"{ip} {domain}")
    
    await _pihole_request("PUT", f"/config/dns/hosts/{encoded_entry}", connection_id=connection_id)
    
    return f"Local DNS Eintrag hinzugefügt: {domain} -> {ip}"


@tool
async def remove_custom_dns_record(domain: str, ip: str, connection_id: str = "") -> str:
    """
    Löscht einen Local DNS Eintrag (Custom DNS Host) in Pi-hole.
    
    Args:
        domain: Der Domain-Name (z.B. 'service.local')
        ip: Die zugewiesene IP-Adresse des Eintrags (muss exakt übereinstimmen)
    """
    import urllib.parse
    
    encoded_entry = urllib.parse.quote(f"{ip} {domain}")
    
    await _pihole_request("DELETE", f"/config/dns/hosts/{encoded_entry}", connection_id=connection_id)
    
    return f"Local DNS Eintrag gelöscht: {domain} -> {ip}"


@tool
async def get_cname_records(connection_id: str = "") -> dict:
    """
    Ruft alle Local CNAME Records aus dem Pi-hole ab.
    Gibt ein Dictionary mit {Domain: Target} zurück.
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
    Fügt einen neuen Local CNAME Record hinzu.
    
    Args:
        domain: Der Domain-Name (z.B. 'alias.local')
        target: Das Ziel, auf das der CNAME zeigen soll (z.B. 'server.local')
    """
    import urllib.parse
    encoded_entry = urllib.parse.quote(f"{domain},{target}")
    await _pihole_request("PUT", f"/config/dns/cnameRecords/{encoded_entry}", connection_id=connection_id)
    return f"CNAME Record hinzugefügt: {domain} -> {target}"


@tool
async def remove_cname_record(domain: str, target: str, connection_id: str = "") -> str:
    """
    Löscht einen Local CNAME Record in Pi-hole.
    
    Args:
        domain: Der Domain-Name (z.B. 'alias.local')
        target: Das zugewiesene Ziel (muss exakt übereinstimmen)
    """
    import urllib.parse
    encoded_entry = urllib.parse.quote(f"{domain},{target}")
    await _pihole_request("DELETE", f"/config/dns/cnameRecords/{encoded_entry}", connection_id=connection_id)
    return f"CNAME Record gelöscht: {domain} -> {target}"


@tool
async def get_dhcp_leases(connection_id: str = "") -> list[dict]:
    """
    Ruft alle aktiven DHCP Leases vom Pi-hole ab.
    Gibt die vergebenen IP-Adressen, MAC-Adressen und Hostnamen zurück.
    """
    data = await _pihole_request("GET", "/dhcp/leases", connection_id=connection_id)
    return data.get("leases", [])


@tool
async def delete_dhcp_lease(ip: str, connection_id: str = "") -> str:
    """
    Löscht einen aktiven DHCP Lease anhand der IP-Adresse.
    
    Args:
        ip: Die IP-Adresse, deren Lease gelöscht werden soll (z.B. '192.168.1.50')
    """
    await _pihole_request("DELETE", f"/dhcp/leases/{ip}", connection_id=connection_id)
    return f"DHCP Lease für IP {ip} wurde gelöscht."


@tool
async def update_gravity(connection_id: str = "") -> str:
    """
    Triggert ein manuelles Gravity-Update (Download und Aktualisierung der Blocklisten).
    Dieser Prozess kann einen Moment dauern.
    """
    await _pihole_request("POST", "/action/gravity", connection_id=connection_id)
    return "Gravity-Update wurde erfolgreich gestartet."


@tool
async def flush_dns_cache(connection_id: str = "") -> str:
    """
    Startet den DNS Service auf dem Pi-hole neu und leert dabei den DNS Cache.
    """
    await _pihole_request("POST", "/action/restartdns", connection_id=connection_id)
    return "DNS Server neu gestartet und Cache geleert."


@tool
async def flush_logs(connection_id: str = "") -> str:
    """
    Löscht/leert alle Query Logs (FTL/DNS Logs) im Pi-hole.
    """
    await _pihole_request("POST", "/action/flush/logs", connection_id=connection_id)
    return "Logs wurden erfolgreich gelöscht."


@tool
async def flush_network_table(connection_id: str = "") -> str:
    """
    Leert die Netzwerktabelle (ARP-Cache/bekannte Geräte) im Pi-hole Datenbank.
    """
    await _pihole_request("POST", "/action/flush/network", connection_id=connection_id)
    return "Netzwerktabelle wurde erfolgreich geleert."


@tool
async def get_system_messages(connection_id: str = "") -> list[dict]:
    """
    Ruft alle aktiven System-Warnungen und Meldungen (z.B. DNSMASQ_WARN) aus Pi-hole ab.
    Gibt Meldungs-ID, Typ und Nachricht zurück.
    """
    data = await _pihole_request("GET", "/info/messages", connection_id=connection_id)
    return data.get("messages", [])


@tool
async def dismiss_system_message(message_id: str, connection_id: str = "") -> str:
    """
    Löscht/verwirft eine bestimmte System-Warnung im Pi-hole anhand der ID.
    
    Args:
        message_id: Die ID der Meldung, die gelöscht werden soll.
    """
    await _pihole_request("DELETE", f"/info/messages/{message_id}", connection_id=connection_id)
    return f"Systemmeldung mit ID {message_id} wurde gelöscht."

