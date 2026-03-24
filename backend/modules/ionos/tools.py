"""
IONOS DNS Modul – Tools für den AI-Agenten.
Nutzt die IONOS Cloud DNS API v1.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx
from langchain_core.tools import tool

logger = logging.getLogger("kumio.modules.ionos.tools")

IONOS_DNS_API_BASE = "https://api.hosting.ionos.com/dns/v1"


async def _get_ionos_config(connection_id: str = "") -> dict:
    """IONOS Verbindungsdaten aus ConnectionManager, Vault oder Env-Var laden."""
    from core.connections import ConnectionManager
    from core.vault import get_vault

    conn = None
    if connection_id:
        conn = await ConnectionManager.get_connection("ionos", connection_id)
        if not conn:
            raise ValueError(f"IONOS Verbindung mit ID '{connection_id}' nicht gefunden.")
    else:
        conn = await ConnectionManager.get_default_connection("ionos")

    if conn:
        vault = get_vault()
        api_key = ""
        if "api_key" in conn.vault_keys:
            api_key = await vault.get_secret(conn.vault_keys["api_key"]) or ""
            api_key = api_key.replace("—", "-").strip()
        return {"api_key": api_key}

    # Fallback: Env-Var (für k8s / docker-compose Konfiguration ohne UI)
    api_key = os.getenv("IONOS_API_KEY", "").replace("—", "-").strip()
    if not api_key:
        raise ValueError(
            "Keine IONOS-Verbindung konfiguriert. "
            "Bitte eine Verbindung in den Einstellungen anlegen oder IONOS_API_KEY setzen."
        )
    return {"api_key": api_key}


async def _ionos_request(
    method: str,
    path: str,
    body: dict | None = None,
    params: dict | None = None,
    connection_id: str = "",
) -> dict | list | str:
    """Authentifizierter Request an die IONOS DNS API."""
    config = await _get_ionos_config(connection_id)
    api_key = config["api_key"]
    
    if not api_key:
        raise ValueError(
            "IONOS API-Key nicht konfiguriert. "
            "Bitte IONOS_API_KEY in den Modul-Einstellungen setzen."
        )

    # Clean path
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
        
        # Responses might be empty for DELETE
        if resp.status_code == 204 or not resp.text:
            return ""
            
        return resp.json()


# ── Tools ──────────────────────────────────────────

@tool
async def get_ionos_zones(connection_id: str = "") -> list[dict]:
    """
    Ruft alle DNS-Zonen bei IONOS ab.
    Nützlich, um die zone_id (UUID) für weitere Operationen zu finden.
    """
    response = await _ionos_request("GET", "zones", connection_id=connection_id)
    if isinstance(response, list):
        return response
    
    # Manchmal verpackt die API die Liste
    return response


@tool
async def get_ionos_records(zone_id: str, connection_id: str = "") -> list[dict]:
    """
    Ruft alle DNS-Einträge (A, AAAA, CNAME, TXT, etc.) für eine bestimmte DNS-Zone ab.
    
    Args:
        zone_id: Die eindeutige UUID der IONOS DNS Zone (aus get_ionos_zones).
    """
    # Die IONOS Hosting API gibt Records als Teil von GET /zones/{id} zurück.
    # Der separate Endpoint /zones/{id}/records ist nicht für alle Keys zugänglich.
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
    Erstellt einen neuen DNS-Eintrag in einer IONOS Zone.
    
    Args:
        zone_id: Die UUID der Zone.
        name: Der Hostname (z.B. 'www' oder 'api'). Verwende den vollständigen FQDN, oder einfach '@' falls es APEX ist.
        record_type: Der Record-Typ (A, AAAA, CNAME, TXT, MX, etc.).
        content: Das Ziel (IP-Adresse, Domain für CNAME, Text für TXT).
        ttl: Die Time-To-Live in Sekunden (Standard: 3600).
        prio: Die Priorität (nur für MX-Einträge relevant).
    """
    record = {
        "name": name,
        "type": record_type.upper(),
        "content": content,
        "ttl": ttl
    }

    # Prio nur bei MX hinzufügen
    if record_type.upper() == "MX":
        record["prio"] = prio

    # IONOS API erwartet ein Array von Records
    await _ionos_request("POST", f"zones/{zone_id}/records", body=[record], connection_id=connection_id)
    return f"DNS-Eintrag ({record_type}) für '{name}' -> '{content}' erfolgreich erstellt."


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
    Aktualisiert einen bestehenden IONOS DNS-Eintrag.
    
    Args:
        zone_id: Die UUID der Zone.
        record_id: Die eindeutige UUID des anzupassenden DNS-Eintrags.
        name: Der neue (oder alte) Hostname.
        record_type: Der Record-Typ (A, CNAME, etc.).
        content: Das neue Ziel.
        ttl: Die Time-To-Live in Sekunden.
        prio: Die Priorität (für MX).
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
    return f"DNS-Eintrag {record_id} aktualisiert: {name} ({record_type}) -> {content}."


@tool
async def delete_ionos_record(zone_id: str, record_id: str, connection_id: str = "") -> str:
    """
    Löscht einen DNS-Eintrag bei IONOS endgültig.
    
    Args:
        zone_id: Die UUID der Zone.
        record_id: Die eindeutige UUID des zu löschenden DNS-Eintrags.
    """
    await _ionos_request("DELETE", f"zones/{zone_id}/records/{record_id}", connection_id=connection_id)
    return f"DNS-Eintrag {record_id} aus der Zone {zone_id} erfolgreich gelöscht."
