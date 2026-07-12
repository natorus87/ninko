"""Security Core — Scanner Registry und eingebaute Scan-Profile.

Analog zum Pattern von core/tool_registry.py: eine zentrale, in-memory
Registry als Single Source of Truth. Kein unbekannter oder unregistrierter
Scanner kann jemals ausgefuehrt werden — `get_scanner()` wirft, wenn die
scanner_id nicht registriert ist.

Adapter registrieren sich selbst beim Import (siehe adapters/__init__.py),
nicht diese Datei kennt die Adapter-Implementierungen im Voraus.
"""

from __future__ import annotations

import logging
import threading

from .models import ScanProfile, ScanProfileKind, ScannerDefinition, TargetType
from .scanner_adapter import SecurityScannerAdapter

logger = logging.getLogger("ninko.modules.security.scanner_registry")


class UnknownScannerError(ValueError):
    """Ein referenzierter Scanner ist nicht (oder nicht mehr) registriert."""


class ScannerNotAllowedError(ValueError):
    """Scanner ist fuer dieses Target oder Profil nicht zulaessig."""


class ScannerRegistry:
    """Thread-sicherer, in-memory Registry-Singleton fuer ScannerDefinition + Adapter."""

    def __init__(self) -> None:
        self._definitions: dict[str, ScannerDefinition] = {}
        self._adapters: dict[str, SecurityScannerAdapter] = {}
        self._lock = threading.Lock()

    def register(self, definition: ScannerDefinition, adapter: SecurityScannerAdapter) -> None:
        if definition.id != adapter.scanner_id:
            raise ValueError(
                f"ScannerDefinition.id ({definition.id!r}) != adapter.scanner_id ({adapter.scanner_id!r})"
            )
        with self._lock:
            self._definitions[definition.id] = definition
            self._adapters[definition.id] = adapter
        logger.info("Scanner registriert: %s (%s)", definition.id, definition.category.value)

    def get_definition(self, scanner_id: str) -> ScannerDefinition:
        definition = self._definitions.get(scanner_id)
        if definition is None:
            raise UnknownScannerError(f"Unbekannter Scanner: {scanner_id!r}")
        return definition

    def get_adapter(self, scanner_id: str) -> SecurityScannerAdapter:
        adapter = self._adapters.get(scanner_id)
        if adapter is None:
            raise UnknownScannerError(f"Unbekannter Scanner: {scanner_id!r}")
        return adapter

    def list_definitions(self, *, enabled_only: bool = True) -> list[ScannerDefinition]:
        defs = list(self._definitions.values())
        if enabled_only:
            defs = [d for d in defs if d.enabled]
        return sorted(defs, key=lambda d: d.id)

    def is_registered(self, scanner_id: str) -> bool:
        return scanner_id in self._definitions

    def supports_target_type(self, scanner_id: str, target_type: TargetType) -> bool:
        definition = self.get_definition(scanner_id)
        return target_type in definition.supported_target_types


_registry: ScannerRegistry | None = None
_registry_lock = threading.Lock()


def get_scanner_registry() -> ScannerRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = ScannerRegistry()
    return _registry


# ── Eingebaute Scan-Profile (Passive / Standard / Intrusive) ────────────

BUILTIN_SCAN_PROFILES: dict[str, ScanProfile] = {
    "passive": ScanProfile(
        id="passive",
        name="Passive",
        kind=ScanProfileKind.PASSIVE,
        description=(
            "Nicht-intrusive Pruefungen fuer regelmaessige Automatisierungen: Container-, "
            "Dependency-, IaC-, Kubernetes-Config- und Secret-Scanning, SBOM, TLS-Konfig ohne "
            "aktive Exploitation, LLM-Endpoint-Konfigurationspruefung."
        ),
        allowed_scanner_ids=[
            "trivy", "kubescape", "kubelinter", "gitleaks", "checkov", "testssl",
        ],
    ),
    "standard": ScanProfile(
        id="standard",
        name="Standard",
        kind=ScanProfileKind.STANDARD,
        description=(
            "Kontrollierte Netzwerk- und Service-Pruefung: Service Discovery, begrenztes "
            "Port-Scanning, Nuclei Safe Templates, Web Passive Scan, HTTP Security Headers, "
            "Kubernetes Runtime Checks."
        ),
        allowed_scanner_ids=["nmap", "nuclei", "testssl", "kubescape", "kubelinter", "trivy"],
    ),
    "intrusive": ScanProfile(
        id="intrusive",
        name="Intrusive",
        kind=ScanProfileKind.INTRUSIVE,
        description=(
            "Aktive Web-Scans, aggressive Nuclei-Templates, Fuzzing, Credential Testing, "
            "Exploit-Validierung. Nur manuell mit expliziter, profilbezogener Freigabe — "
            "niemals zeitgesteuert (siehe ScanProfile.allow_scheduling)."
        ),
        allowed_scanner_ids=["nuclei", "garak"],
    ),
}


def get_scan_profile(profile_id: str) -> ScanProfile:
    profile = BUILTIN_SCAN_PROFILES.get(profile_id)
    if profile is None:
        raise ValueError(f"Unbekanntes Scan-Profil: {profile_id!r}")
    return profile


def scanner_allowed_in_profile(scanner_id: str, profile_id: str) -> bool:
    profile = get_scan_profile(profile_id)
    return scanner_id in profile.allowed_scanner_ids
