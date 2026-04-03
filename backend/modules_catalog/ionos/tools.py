"""
IONOS DNS Module — Tools for the AI Agent.
Uses the IONOS Cloud DNS API v1.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx
from langchain_core.tools import tool

from agents.base_agent import _t

logger = logging.getLogger("ninko.modules.ionos.tools")

IONOS_DNS_API_BASE = "https://api.hosting.ionos.com/dns/v1"


async def _get_ionos_config(connection_id: str = "") -> dict:
    """Load IONOS connection data from ConnectionManager, Vault, or env var."""
    from core.connections import ConnectionManager
    from core.vault import get_vault

    conn = None
    if connection_id:
        conn = await ConnectionManager.get_connection("ionos", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"IONOS Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"IONOS connection with ID '{connection_id}' not found.",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("ionos")

    if conn:
        vault = get_vault()
        api_key = ""
        if "api_key" in conn.vault_keys:
            api_key = await vault.get_secret(conn.vault_keys["api_key"]) or ""
            api_key = api_key.replace("\u2014", "-").strip()
        return {"api_key": api_key}

    # Fallback: env var (for k8s / docker-compose without UI)
    api_key = os.getenv("IONOS_API_KEY", "").replace("\u2014", "-").strip()
    if not api_key:
        raise ValueError(
            _t(
                de="Keine IONOS-Verbindung konfiguriert. Bitte eine Verbindung in den Einstellungen anlegen oder IONOS_API_KEY setzen.",
                en="No IONOS connection configured. Please create a connection in Settings or set IONOS_API_KEY.",
            )
        )
    return {"api_key": api_key}


async def _ionos_request(
    method: str,
    path: str,
    body: dict | None = None,
    params: dict | None = None,
    connection_id: str = "",
) -> dict | list | str:
    """Authenticated request to the IONOS DNS API."""
    config = await _get_ionos_config(connection_id)
    api_key = config["api_key"]

    if not api_key:
        raise ValueError(
            _t(
                de="IONOS API-Key nicht konfiguriert. Bitte IONOS_API_KEY in den Modul-Einstellungen setzen.",
                en="IONOS API key not configured. Please set IONOS_API_KEY in the module settings.",
            )
        )

    if path.startswith("/"):
        path = path[1:]

    url = f"{IONOS_DNS_API_BASE}/{path}"
    headers = {
        "X-API-Key": api_key,
        "Accept": "application/json"
    }

    if body:
        headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.request(
            method, url, headers=headers, json=body, params=params
        )
        resp.raise_for_status()

        if resp.status_code == 204 or not resp.text:
            return ""

        return resp.json()


# ── Tools ──────────────────────────────────────────

@tool
async def get_ionos_zones(connection_id: str = "") -> list[dict]:
    """
    Retrieve all DNS zones from IONOS.
    Useful for finding the zone_id (UUID) for further operations.
    """
    response = await _ionos_request("GET", "zones", connection_id=connection_id)
    if isinstance(response, list):
        return response
    return response


@tool
async def get_ionos_records(zone_id: str, connection_id: str = "") -> list[dict]:
    """
    Retrieve all DNS records (A, AAAA, CNAME, TXT, etc.) for a specific DNS zone.

    Args:
        zone_id: The unique UUID of the IONOS DNS zone (from get_ionos_zones).
    """
    # The IONOS Hosting API returns records as part of GET /zones/{id}.
    # The separate /zones/{id}/records endpoint is not accessible for all keys.
    response = await _ionos_request("GET", f"zones/{zone_id}", connection_id=connection_id)
    if isinstance(response, dict):
        return response.get("records", [])
    return []


@tool
async def add_ionos_record(
    zone_id: str,
    name: str,
    record_type: str,
    content: str,
    ttl: int = 3600,
    prio: int = 0,
    connection_id: str = ""
) -> str:
    """
    Create a new DNS record in an IONOS zone.

    Args:
        zone_id: The UUID of the zone.
        name: The hostname (e.g. 'www' or 'api'). Use the full FQDN or '@' for apex.
        record_type: Record type (A, AAAA, CNAME, TXT, MX, etc.).
        content: The target (IP address, domain for CNAME, text for TXT).
        ttl: Time-to-live in seconds (default: 3600).
        prio: Priority (only relevant for MX records).
    """
    record = {
        "name": name,
        "type": record_type.upper(),
        "content": content,
        "ttl": ttl
    }

    if record_type.upper() == "MX":
        record["prio"] = prio

    await _ionos_request("POST", f"zones/{zone_id}/records", body=[record], connection_id=connection_id)
    logger.info("Created DNS record (%s) for '%s' -> '%s'", record_type, name, content)
    return _t(
        de=f"DNS-Eintrag ({record_type}) für '{name}' -> '{content}' erfolgreich erstellt.",
        en=f"DNS record ({record_type}) for '{name}' -> '{content}' created successfully.",
    )


@tool
async def update_ionos_record(
    zone_id: str,
    record_id: str,
    name: str,
    record_type: str,
    content: str,
    ttl: int = 3600,
    prio: int = 0,
    connection_id: str = ""
) -> str:
    """
    Update an existing IONOS DNS record.

    Args:
        zone_id: The UUID of the zone.
        record_id: The unique UUID of the DNS record to update.
        name: The new (or old) hostname.
        record_type: Record type (A, CNAME, etc.).
        content: The new target.
        ttl: Time-to-live in seconds.
        prio: Priority (for MX).
    """
    payload = {
        "name": name,
        "type": record_type.upper(),
        "content": content,
        "ttl": ttl
    }

    if record_type.upper() == "MX":
        payload["prio"] = prio

    await _ionos_request("PUT", f"zones/{zone_id}/records/{record_id}", body=payload, connection_id=connection_id)
    logger.info("Updated DNS record %s: %s (%s) -> %s", record_id, name, record_type, content)
    return _t(
        de=f"DNS-Eintrag {record_id} aktualisiert: {name} ({record_type}) -> {content}.",
        en=f"DNS record {record_id} updated: {name} ({record_type}) -> {content}.",
    )


@tool
async def delete_ionos_record(zone_id: str, record_id: str, connection_id: str = "") -> str:
    """
    Delete a DNS record from IONOS permanently.

    Args:
        zone_id: The UUID of the zone.
        record_id: The unique UUID of the DNS record to delete.
    """
    await _ionos_request("DELETE", f"zones/{zone_id}/records/{record_id}", connection_id=connection_id)
    logger.info("Deleted DNS record %s from zone %s", record_id, zone_id)
    return _t(
        de=f"DNS-Eintrag {record_id} aus der Zone {zone_id} erfolgreich gelöscht.",
        en=f"DNS record {record_id} deleted from zone {zone_id} successfully.",
    )
