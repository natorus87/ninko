"""Security Core — Policy Engine: Scope-Validierung, Approval-Gate, SSRF-Schutz.

Zentrale, serverseitige Durchsetzung. Der Agent-Prompt ist KEINE Sicherheitsgrenze —
jede hier implementierte Pruefung greift unabhaengig davon, was das LLM vorschlaegt.

Drei Verantwortlichkeiten:
1. Scanner/Target/Profil-Zulaessigkeit (Allowlists, unterstuetzte Target-Typen).
2. Netzwerk-Scope (CIDR/Domain-Allowlist + net_guard-SSRF-Basisschutz, DNS-Rebinding-
   Teilschutz durch Re-Resolve zum Validierungszeitpunkt).
3. Approval-Gate fuer intrusive Profile (Redis-gestuetzt, an einen Run gebunden,
   zeitlich begrenzt, Audit-Trail).
"""

from __future__ import annotations

import ipaddress
import json
import logging
import socket
import time
import uuid
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from core.net_guard import BlockedOutboundURLError, assert_safe_outbound_url

from .models import ScanProfile, ScannerDefinition, SecurityTarget, TargetType, TriggerType
from .scanner_registry import get_scan_profile, get_scanner_registry, scanner_allowed_in_profile

logger = logging.getLogger("ninko.modules.security.policy")

_APPROVAL_TTL_S = 900  # 15 Minuten
_APPROVAL_REDIS_PREFIX = "ninko:security:approval:"

# Target-Typen, deren locator eine Netzwerk-Adresse/URL ist (fuer Scope-Checks relevant).
_NETWORK_TARGET_TYPES = frozenset({
    TargetType.HOSTNAME,
    TargetType.IP_ADDRESS,
    TargetType.CIDR,
    TargetType.URL,
    TargetType.API_ENDPOINT,
    TargetType.SSH_HOST,
    TargetType.TLS_ENDPOINT,
    TargetType.LLM_ENDPOINT,
    TargetType.OPENAI_COMPATIBLE_API,
    TargetType.LITELLM_GATEWAY,
    TargetType.VLLM_ENDPOINT,
    TargetType.OPEN_WEBUI_INSTANCE,
})


class PolicyViolation(ValueError):
    """Scan-Anfrage verletzt Scope-, Allowlist- oder Approval-Policy. Fail-closed."""


class PolicyDecision(BaseModel):
    """Ergebnis einer vollstaendigen Policy-Pruefung fuer eine Scan-Anfrage."""

    model_config = ConfigDict(extra="forbid")

    allowed: bool
    requires_approval: bool
    warnings: list[str] = Field(default_factory=list)


def _extract_host(target: SecurityTarget) -> str | None:
    """Extrahiert einen pruefbaren Hostnamen/IP aus dem Target-Locator."""
    if target.target_type in (TargetType.URL, TargetType.API_ENDPOINT) or target.locator.startswith(
        ("http://", "https://")
    ):
        return urlparse(target.locator).hostname
    if target.target_type in (
        TargetType.HOSTNAME,
        TargetType.IP_ADDRESS,
        TargetType.SSH_HOST,
        TargetType.TLS_ENDPOINT,
    ):
        # locator kann "host:port" sein
        return target.locator.split(":")[0].strip()
    return None


def _resolve_all_ips(host: str) -> list[ipaddress._BaseAddress]:
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return []
    ips: list[ipaddress._BaseAddress] = []
    for info in infos:
        addr = info[4][0]
        try:
            ips.append(ipaddress.ip_address(addr.split("%")[0]))
        except ValueError:
            continue
    return ips


def enforce_network_scope(target: SecurityTarget) -> list[str]:
    """Prueft Netzwerk-Scope fuer netzwerkbasierte Targets. Wirft PolicyViolation
    bei Verstoss (fail-closed), gibt sonst eine Liste von Warnungen zurueck.

    Zwei Ebenen:
    1. Harter Link-Local/Cloud-Metadata-Block, fuer JEDEN Netzwerk-Target-Typ —
       nicht nur fuer http(s)-URLs. net_guard.assert_safe_outbound_url prueft das
       nur fuer URL-foermige Locators; Scanner wie Nmap/testssl.sh adressieren
       Ziele aber meist als blossen Hostnamen/IP (TargetType.HOSTNAME/IP_ADDRESS/
       SSH_HOST/TLS_ENDPOINT), die diesen Praefix nie haben. Ohne diesen
       zusaetzlichen Check waere z.B. ein Target (IP_ADDRESS, "169.254.169.254")
       vollstaendig ungeschuetzt, obwohl fuer URL-Targets derselbe Fall blockiert
       wird — beide Locator-Formen muessen dieselbe Sperre durchlaufen.
    2. target.scope_constraints["cidr_allowlist"] — falls gesetzt, MUSS jede aufgeloeste
       IP darin liegen (explizite Allowlist, staerker als Punkt 1). Re-Resolve zum
       Pruefzeitpunkt (nicht nur beim Anlegen des Targets) als Teilschutz gegen DNS-
       Rebinding — vollstaendiger Schutz erfordert zusaetzlich IP-Pinning direkt am
       Scanner-Aufruf, was hier bewusst nicht implementiert ist (siehe Doku, bekannte
       Limitation).
    """
    warnings: list[str] = []
    if target.target_type not in _NETWORK_TARGET_TYPES:
        return warnings

    if target.locator.startswith(("http://", "https://")):
        try:
            assert_safe_outbound_url(target.locator, purpose="security-scan-target")
        except BlockedOutboundURLError as exc:
            raise PolicyViolation(str(exc)) from exc

    host = _extract_host(target)
    if host is None:
        return warnings

    resolved = _resolve_all_ips(host)
    for ip in resolved:
        if ip.is_link_local or (ip.version == 6 and ip.is_site_local):
            raise PolicyViolation(
                f"Host {host} (Target {target.id}) loest zu Link-Local/Metadata-Adresse "
                f"{ip} auf — fuer Security-Scan-Targets gesperrt."
            )

    cidr_allowlist = target.scope_constraints.get("cidr_allowlist")
    if not cidr_allowlist:
        return warnings

    try:
        allowed_networks = [ipaddress.ip_network(c, strict=False) for c in cidr_allowlist]
    except ValueError as exc:
        raise PolicyViolation(f"Ungueltiger cidr_allowlist-Eintrag in Target {target.id}: {exc}") from exc

    if not resolved:
        raise PolicyViolation(
            f"Host {host} (Target {target.id}) konnte nicht aufgeloest werden — "
            "Scan wird fail-closed blockiert."
        )
    for ip in resolved:
        if not any(ip in net for net in allowed_networks):
            raise PolicyViolation(
                f"Host {host} loest zu {ip} auf — ausserhalb des erlaubten CIDR-Scopes "
                f"{cidr_allowlist} von Target {target.id}. Moeglicher DNS-Rebinding-Versuch "
                "oder falsch konfiguriertes Target."
            )
    return warnings


def enforce_allowlists(target: SecurityTarget, scanner_id: str, profile_id: str) -> None:
    """Prueft Scanner-/Profil-/Target-Typ-Zulaessigkeit. Wirft PolicyViolation."""
    if not target.enabled:
        raise PolicyViolation(f"Target {target.id} ist deaktiviert.")

    registry = get_scanner_registry()
    definition: ScannerDefinition = registry.get_definition(scanner_id)  # wirft UnknownScannerError
    if not definition.enabled:
        raise PolicyViolation(f"Scanner {scanner_id} ist deaktiviert.")

    profile: ScanProfile = get_scan_profile(profile_id)  # wirft ValueError bei unbekanntem Profil

    if not scanner_allowed_in_profile(scanner_id, profile_id):
        raise PolicyViolation(f"Scanner {scanner_id} ist im Profil {profile_id} nicht erlaubt.")

    if target.target_type not in definition.supported_target_types:
        raise PolicyViolation(
            f"Scanner {scanner_id} unterstuetzt Target-Typ {target.target_type.value} nicht."
        )

    if target.allowed_scanners and scanner_id not in target.allowed_scanners:
        raise PolicyViolation(f"Scanner {scanner_id} ist fuer Target {target.id} nicht freigegeben.")

    if target.allowed_profiles and profile.kind not in target.allowed_profiles:
        raise PolicyViolation(f"Profil {profile_id} ist fuer Target {target.id} nicht freigegeben.")


def enforce_trigger_policy(profile_id: str, trigger_type: TriggerType) -> None:
    """Intrusive Profile duerfen laut Auftrag NIEMALS zeitgesteuert laufen."""
    profile = get_scan_profile(profile_id)
    if not profile.allow_scheduling and trigger_type != TriggerType.MANUAL:
        raise PolicyViolation(
            f"Profil {profile_id} ist intrusive und darf nur manuell ausgeloest werden "
            f"(trigger_type={trigger_type.value} abgelehnt)."
        )


def enforce_capabilities(
    required_capability: str, agent_capabilities: list[str], denied_capabilities: list[str]
) -> None:
    """Serverseitiger Capability-Check fuer Agent-initiierte Scan-Anfragen.

    Der Agent-Prompt ist keine Sicherheitsgrenze — dieser Check laeuft unabhaengig
    davon, was im System-Prompt steht.
    """
    if required_capability in denied_capabilities:
        raise PolicyViolation(f"Capability {required_capability!r} ist fuer diesen Agent explizit verboten.")
    if agent_capabilities and required_capability not in agent_capabilities:
        raise PolicyViolation(f"Agent hat die Capability {required_capability!r} nicht.")


def validate_scan_request(
    *,
    target: SecurityTarget,
    scanner_id: str,
    profile_id: str,
    trigger_type: TriggerType,
    agent_capabilities: list[str] | None = None,
    denied_capabilities: list[str] | None = None,
    required_capability: str | None = None,
) -> PolicyDecision:
    """Vollstaendige Policy-Pruefung. Wirft PolicyViolation bei jedem Verstoss
    (fail-closed) — gibt bei Erfolg eine PolicyDecision zurueck, die angibt, ob
    zusaetzlich eine explizite Freigabe (Approval) noetig ist.
    """
    enforce_allowlists(target, scanner_id, profile_id)
    enforce_trigger_policy(profile_id, trigger_type)
    warnings = enforce_network_scope(target)

    if required_capability is not None:
        enforce_capabilities(required_capability, agent_capabilities or [], denied_capabilities or [])

    profile = get_scan_profile(profile_id)
    return PolicyDecision(allowed=True, requires_approval=profile.requires_approval, warnings=warnings)


# ── Approval-Gate ──────────────────────────────────────────────────────


class ApprovalRequest(BaseModel):
    """An einen konkreten Scan-Run gebundene, zeitlich begrenzte Freigabe-Anfrage."""

    model_config = ConfigDict(extra="forbid")

    approval_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scan_run_id: str
    target_id: str
    scanner_id: str
    profile_id: str
    scope_summary: str
    requested_by: str
    requested_at: float = Field(default_factory=time.time)
    expires_at: float
    status: str = "pending"  # pending | approved | rejected | expired
    decided_by: str | None = None
    decided_at: float | None = None


async def create_approval_request(
    *, scan_run_id: str, target: SecurityTarget, scanner_id: str, profile_id: str, requested_by: str
) -> ApprovalRequest:
    """Legt eine Freigabe-Anfrage an, gebunden an genau diesen scan_run_id.
    TTL-basiert in Redis — nach Ablauf ist die Freigabe automatisch ungueltig
    und muss erneut angefordert werden (auch bei unveraendertem Plan).
    """
    from core.redis_client import get_redis

    now = time.time()
    request = ApprovalRequest(
        scan_run_id=scan_run_id,
        target_id=target.id,
        scanner_id=scanner_id,
        profile_id=profile_id,
        scope_summary=f"{target.name} ({target.target_type.value}: {target.locator})",
        requested_by=requested_by,
        expires_at=now + _APPROVAL_TTL_S,
    )
    redis = get_redis()
    await redis.connection.set(
        f"{_APPROVAL_REDIS_PREFIX}{scan_run_id}", request.model_dump_json(), ex=_APPROVAL_TTL_S
    )
    logger.info(
        "Approval angefordert: run=%s scanner=%s profile=%s target=%s",
        scan_run_id,
        scanner_id,
        profile_id,
        target.id,
    )
    return request


async def get_approval_request(scan_run_id: str) -> ApprovalRequest | None:
    from core.redis_client import get_redis

    redis = get_redis()
    raw = await redis.connection.get(f"{_APPROVAL_REDIS_PREFIX}{scan_run_id}")
    if not raw:
        return None
    return ApprovalRequest.model_validate(json.loads(raw))


async def decide_approval(scan_run_id: str, *, approved: bool, decided_by: str) -> ApprovalRequest:
    """Entscheidet eine anstehende Freigabe. Wirft PolicyViolation, wenn keine
    (noch gueltige) Anfrage fuer diesen Run existiert — z.B. weil sie abgelaufen ist
    oder der Plan sich seither geaendert hat (neue Anfrage = neue scan_run_id = neue
    Freigabe noetig, strukturell erzwungen)."""
    from core.redis_client import get_redis

    request = await get_approval_request(scan_run_id)
    if request is None:
        raise PolicyViolation(
            f"Keine gueltige Freigabe-Anfrage fuer Run {scan_run_id} — abgelaufen oder nie angefordert."
        )
    request.status = "approved" if approved else "rejected"
    request.decided_by = decided_by
    request.decided_at = time.time()

    redis = get_redis()
    remaining_ttl = max(1, int(request.expires_at - time.time()))
    await redis.connection.set(
        f"{_APPROVAL_REDIS_PREFIX}{scan_run_id}", request.model_dump_json(), ex=remaining_ttl
    )
    logger.info("Approval %s fuer Run %s durch %s", request.status, scan_run_id, decided_by)
    return request


async def is_approved(scan_run_id: str) -> bool:
    request = await get_approval_request(scan_run_id)
    return request is not None and request.status == "approved" and request.expires_at > time.time()
