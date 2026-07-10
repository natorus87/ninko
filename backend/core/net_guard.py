"""
Ninko – SSRF-Schutz für serverseitig aufgerufene, benutzerkonfigurierte URLs.

Ninko lässt Nutzer (Rolle admin) Backend-URLs für LLM-, OCR-Vision- und
Embedding-Provider konfigurieren, die der Server dann aufruft. Self-hosted
Endpunkte (Ollama, LM Studio) laufen legitim auf privaten oder Loopback-
Adressen — ein pauschaler SSRF-Block würde diese Kernfunktion brechen.

Deshalb der pragmatische Kompromiss:
- **Hart blockiert** wird ausschließlich der Link-Local-Bereich (169.254.0.0/16,
  fe80::/10) inklusive der Cloud-Metadata-Endpunkte (AWS/GCP/Azure 169.254.169.254).
  Diese sind nie ein legitimes Provider-Ziel, aber das gefährlichste SSRF-Ziel
  (Credential-Exfiltration).
- Für private/Loopback-Adressen wird nur eine Warnung geloggt (self-hosted erlaubt).

Zustandslos und ohne Import-Zeit-Seiteneffekte — unit-testbar.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger("ninko.net_guard")


class BlockedOutboundURLError(ValueError):
    """Wird geworfen, wenn eine ausgehende URL auf einen gesperrten Bereich zeigt."""


def _resolve_host_ips(host: str) -> list[ipaddress._BaseAddress]:
    """Löst einen Hostnamen zu allen IP-Adressen auf (IPv4 + IPv6)."""
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


def assert_safe_outbound_url(url: str, *, purpose: str = "provider") -> None:
    """Validiert eine benutzerkonfigurierte URL vor einem serverseitigen Request.

    Blockiert Link-Local/Cloud-Metadata-Ziele hart (SSRF), warnt bei privaten
    Adressen. Wirft BlockedOutboundURLError bei gesperrtem Ziel oder ungültigem
    Schema.
    """
    if not url or not url.strip():
        return

    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise BlockedOutboundURLError(
            f"Nur http/https-URLs erlaubt (erhalten: '{parsed.scheme or '—'}')."
        )
    host = parsed.hostname
    if not host:
        raise BlockedOutboundURLError("URL enthält keinen Host.")

    resolved = _resolve_host_ips(host)
    # DNS-Auflösung fehlgeschlagen: nicht blockieren (kann transient sein),
    # der nachfolgende HTTP-Client scheitert dann ohnehin sichtbar.
    for ip in resolved:
        if ip.is_link_local or (ip.version == 6 and ip.is_site_local):
            raise BlockedOutboundURLError(
                f"Ziel-Adresse {ip} (Link-Local/Metadata) ist für {purpose}-URLs gesperrt."
            )
        if ip.is_private or ip.is_loopback:
            logger.warning(
                "%s-URL zeigt auf interne Adresse %s (Host: %s) — erlaubt für "
                "self-hosted Endpunkte, aber Vorsicht bei nicht vertrauenswürdiger Konfiguration.",
                purpose,
                ip,
                host,
            )
