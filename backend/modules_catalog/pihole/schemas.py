"""
Pi-hole Modul – Pydantic Schemas.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class PiholeSummary(BaseModel):
    """Pi-hole Zusammenfassung / Stats."""

    domains_blocked: int = 0
    dns_queries_today: int = 0
    ads_blocked_today: int = 0
    ads_percentage_today: float = 0.0
    unique_domains: int = 0
    queries_forwarded: int = 0
    queries_cached: int = 0
    clients_ever_seen: int = 0
    unique_clients: int = 0
    status: str = "unknown"  # "enabled" | "disabled"


class PiholeQuery(BaseModel):
    """Einzelne DNS-Anfrage."""

    timestamp: float = 0
    type: str = ""          # A, AAAA, PTR, etc.
    domain: str = ""
    client: str = ""
    status: str = ""        # Forwarded, Blocked, Cached, etc.
    reply_type: str = ""
    duration_ms: float = 0


class PiholeTopDomains(BaseModel):
    """Top Domains (erlaubt + blockiert)."""

    top_permitted: dict[str, int] = {}
    top_blocked: dict[str, int] = {}


class PiholeTopClients(BaseModel):
    """Top Clients."""

    top_clients: dict[str, int] = {}


class PiholeBlocklist(BaseModel):
    """Adlist / Blockliste."""

    id: int = 0
    address: str = ""
    enabled: bool = True
    comment: str = ""
    date_added: int = 0
    date_modified: int = 0
    number: int = 0      # Anzahl Domains


class PiholeDomainEntry(BaseModel):
    """Whitelist/Blacklist Eintrag."""

    id: int = 0
    domain: str = ""
    type: str = ""        # "allow" | "deny"
    kind: str = ""        # "exact" | "regex"
    enabled: bool = True
    comment: str = ""


class PiholeSystemInfo(BaseModel):
    """Pi-hole System-Informationen."""

    version_core: str = ""
    version_ftl: str = ""
    version_web: str = ""
    uptime: int = 0
    memory_usage: float = 0
    cpu_temp: Optional[float] = None
    gravity_size: int = 0
    gravity_last_update: str = ""
