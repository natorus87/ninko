"""Nmap-Adapter — Port-Scanning und Service-Discovery (Standard-Profil).

Nutzt die stdlib xml.etree.ElementTree fuer das Parsing — laut Python-Doku
werden externe Entities dort NICHT aufgeloest (kein klassisches XXE-Risiko,
im Gegensatz zu xml.dom.minidom/lxml in manchen Konfigurationen).
"""

from __future__ import annotations

import ipaddress
import xml.etree.ElementTree as ET

from ..models import ScannerCategory, ScannerDefinition, ScanProfileKind, Severity, TargetType
from ..scanner_adapter import (
    ExecutionSpec,
    NetworkPolicy,
    NormalizedFinding,
    ScannerExecutionResult,
    ValidationResult,
)

NMAP_DEFINITION = ScannerDefinition(
    id="nmap",
    name="Nmap",
    description="Port-Scanning und Service-Discovery innerhalb definierter Grenzen.",
    category=ScannerCategory.NETWORK,
    container_image="instrumentisto/nmap:7.95",
    version="7.95",
    output_format="xml",
    parser="nmap_xml",
    required_capabilities=["NET_RAW"],  # fuer SYN-Scans; Default-Profil nutzt Connect-Scan ohne NET_RAW
    required_network_access=True,
    default_timeout=300.0,
    risk_level=ScanProfileKind.STANDARD,
    supported_target_types=[TargetType.IP_ADDRESS, TargetType.CIDR, TargetType.HOSTNAME],
    enabled=True,
)

_MAX_PORTS = 1000  # "Port Scanning innerhalb definierter Grenzen" — harte Obergrenze


class NmapAdapter:
    scanner_id = "nmap"

    def validate_target(self, target, profile, parameters) -> ValidationResult:
        errors = []
        if target.target_type not in (TargetType.IP_ADDRESS, TargetType.CIDR, TargetType.HOSTNAME):
            errors.append("Nmap unterstuetzt nur ip_address/cidr/hostname.")
        top_ports = (parameters or {}).get("top_ports", 1000)
        if not isinstance(top_ports, int) or not (1 <= top_ports <= _MAX_PORTS):
            errors.append(f"top_ports muss zwischen 1 und {_MAX_PORTS} liegen.")
        return ValidationResult(valid=not errors, errors=errors)

    def build_execution_spec(self, target, profile, parameters) -> ExecutionSpec:
        top_ports = (parameters or {}).get("top_ports", 1000)
        if not isinstance(top_ports, int) or not (1 <= top_ports <= _MAX_PORTS):
            raise ValueError(f"top_ports muss zwischen 1 und {_MAX_PORTS} liegen.")

        # Connect-Scan (-sT) statt SYN-Scan (-sS) im Default-Profil, damit KEIN
        # NET_RAW-Capability noetig ist (Least-Privilege) — SYN-Scan bleibt optional
        # ueber parameters["syn_scan"]=True verfuegbar, braucht dann NET_RAW.
        syn_scan = bool((parameters or {}).get("syn_scan", False))
        command = ["nmap", "-oX", "-", "-Pn", "--top-ports", str(top_ports)]
        capabilities: list[str] = []
        if syn_scan:
            command.insert(1, "-sS")
            capabilities = ["NET_RAW"]
        else:
            command.insert(1, "-sT")
        command.append(target.locator)

        allowlist = []
        try:
            ipaddress.ip_network(target.locator, strict=False)
            allowlist = [target.locator if "/" in target.locator else f"{target.locator}/32"]
        except ValueError:
            pass  # Hostname: kein statisches CIDR-Allowlist moeglich, DNS-Aufloesung zur Laufzeit

        return ExecutionSpec(
            scanner_id=self.scanner_id,
            container_image=NMAP_DEFINITION.container_image,
            command=command,
            capabilities=capabilities,
            resource_limits={"cpu": "500m", "memory": "256Mi"},
            timeout_s=NMAP_DEFINITION.default_timeout,
            network_policy=NetworkPolicy(
                mode="target_only" if allowlist else "egress_allowlist", allowlist=allowlist
            ),
            max_output_bytes=5_000_000,
        )

    async def execute(self, execution_spec: ExecutionSpec, context) -> ScannerExecutionResult:
        return await context.executor.run(execution_spec, scan_run_id=context.scan_run_id)

    def parse_results(self, result: ScannerExecutionResult) -> list[NormalizedFinding]:
        try:
            root = ET.fromstring(result.stdout)
        except ET.ParseError as exc:
            raise ValueError(f"Nmap-Output ist kein gueltiges XML: {exc}") from exc

        findings: list[NormalizedFinding] = []
        for host in root.findall("host"):
            address_el = host.find("address")
            host_addr = address_el.get("addr") if address_el is not None else "unknown"

            ports_el = host.find("ports")
            if ports_el is None:
                continue
            for port_el in ports_el.findall("port"):
                state_el = port_el.find("state")
                if state_el is None or state_el.get("state") != "open":
                    continue
                port_id = port_el.get("portid", "")
                protocol = port_el.get("protocol", "tcp")
                service_el = port_el.find("service")
                service_name = service_el.get("name", "") if service_el is not None else ""
                product = service_el.get("product", "") if service_el is not None else ""

                findings.append(
                    NormalizedFinding(
                        rule_id=f"open-port-{protocol}-{port_id}",
                        title=f"Open port {port_id}/{protocol}" + (f" ({service_name})" if service_name else ""),
                        description=f"Service discovery found an open {protocol} port.",
                        severity=Severity.INFO,
                        confidence=1.0,
                        category="open_port",
                        resource_type="network_service",
                        resource_identifier=f"{port_id}/{protocol}",
                        location=host_addr,
                        metadata={"service": service_name, "product": product},
                    )
                )
        return findings
