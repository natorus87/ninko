"""
Network Analysis Module – Tools.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any

from langchain.tools import tool

logger = logging.getLogger("ninko.modules.network_analysis")


@tool
async def dns_lookup(hostname: str) -> str:
    """
    Führt einen DNS-Lookup für einen Hostnamen durch und gibt IP-Adresse(n) zurück.
    Nutze dieses Tool wenn der Benutzer die IP-Adresse einer Webseite oder eines Servers wissen möchte.
    """
    try:
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC)
        ips = sorted({info[4][0] for info in addr_info})
        return f"DNS-Lookup für {hostname}:\n" + "\n".join(f"  {ip}" for ip in ips)
    except socket.gaierror as exc:
        return f"DNS-Lookup für {hostname} fehlgeschlagen: {exc}"
    except Exception as exc:
        logger.exception("dns_lookup fehlgeschlagen")
        return f"DNS-Lookup fehlgeschlagen: {exc}"


@tool
async def reverse_dns(ip_address: str) -> str:
    """
    Führt einen Reverse-DNS-Lookup für eine IP-Adresse durch.
    Nutze dieses Tool wenn der Benutzer den Hostnamen zu einer IP-Adresse wissen möchte.
    """
    try:
        hostname, aliaslist, ipaddrlist = socket.gethostbyaddr(ip_address)
        return f"Reverse-DNS für {ip_address}:\n  Hostname: {hostname}\n  Aliases: {aliaslist or 'keine'}"
    except socket.herror as exc:
        args = exc.args if exc.args else []
        return f"Reverse-DNS für {ip_address} fehlgeschlagen: {args[1] if len(args) > 1 else exc}"
    except Exception as exc:
        logger.exception("reverse_dns fehlgeschlagen")
        return f"Reverse-DNS fehlgeschlagen: {exc}"


@tool
async def traceroute(hostname: str, max_hops: int = 30) -> str:
    """
    Führt einen Traceroute zu einem Host durch.
    Nutze dieses Tool wenn der Benutzer den Netzwerkpfad zu einem Server analysieren möchte.
    """
    try:
        result = await asyncio.create_subprocess_exec(
            "traceroute",
            "-m", str(max_hops),
            "-w", "2",
            hostname,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await result.communicate()
        if result.returncode != 0:
            err = stderr.decode().strip() or "unbekannter Fehler"
            return f"traceroute fehlgeschlagen: {err}"
        output = stdout.decode()
        lines = output.splitlines()
        if len(lines) > 60:
            lines = lines[:60]
            lines.append(f"[…{len(output.splitlines()) - 60} Zeilen gekürzt]")
        return f"Traceroute zu {hostname} ({max_hops} Hops):\n" + "\n".join(lines)
    except FileNotFoundError:
        return "traceroute: Kommando nicht gefunden (nicht installiert)"
    except Exception as exc:
        logger.exception("traceroute fehlgeschlagen")
        return f"Traceroute fehlgeschlagen: {exc}"


@tool
async def ping_host(hostname: str, count: int = 4) -> str:
    """
    Pingt einen Host an und zeigt Statistiken.
    Nutze dieses Tool wenn der Benutzer die Erreichbarkeit eines Servers prüfen möchte.
    """
    try:
        result = await asyncio.create_subprocess_exec(
            "ping",
            "-c", str(count),
            "-W", "2",
            hostname,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await result.communicate()
        err = stderr.decode().strip()
        if result.returncode != 0:
            if "Operation not permitted" in err or "cap_net_raw" in err:
                return _ping_socket_fallback(hostname, count)
            return f"Ping zu {hostname} fehlgeschlagen: {err or 'Host nicht erreichbar'}"
        return f"Ping zu {hostname}:\n{stdout.decode()}"
    except FileNotFoundError:
        return "ping: Kommando nicht gefunden (nicht installiert)"
    except OSError as exc:
        if exc.errno == 1 or "Operation not permitted" in str(exc):
            return _ping_socket_fallback(hostname, count)
        raise
    except Exception as exc:
        if "Operation not permitted" in str(exc) or "cap_net_raw" in str(exc):
            return _ping_socket_fallback(hostname, count)
        logger.exception("ping fehlgeschlagen")
        return f"Ping fehlgeschlagen: {exc}"


def _ping_socket_fallback(hostname: str, count: int = 4) -> str:
    """Fallback-Ping via socket.SOCK_DGRAM (kein Root/RAW-Socket nötig)."""
    import time

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        port = 33434
        sent = 0
        received = 0
        results = []

        for i in range(count):
            try:
                sock.sendto(b"", (hostname, port + i))
                sent += 1
                start = time.time()
                data, addr = sock.recvfrom(512)
                elapsed = (time.time() - start) * 1000
                received += 1
                results.append(f"{addr[0]} udp_seq={i} time={elapsed:.2f}ms")
            except socket.timeout:
                results.append(f"{hostname} udp_seq={i} time=timeout")
            except Exception as e:
                results.append(f"{hostname} udp_seq={i} error={e}")
        sock.close()

        summary = f"Ping-Simulation für {hostname} ({count} UDP-Pakete auf Port 33434+):\n"
        summary += "\n".join(results)
        summary += f"\nGesendet: {sent}, Empfangen: {received}, Verloren: {sent - received}"
        return summary
    except Exception as exc:
        return f"Socket-Fallback-Ping fehlgeschlagen: {exc}"


@tool
async def get_network_info(hostname: str) -> dict[str, Any]:
    """
    Sammelt Netzwerkinformationen für einen Host: IP(s), Reverse-DNS, Host-Typ.
    Nutze dieses Tool für eine umfassende Netzwerkanalyse einer Webseite.
    """
    try:
        addr_info = socket.getaddrinfo(hostname, 80, socket.AF_UNSPEC)
        ips = sorted({info[4][0] for info in addr_info})

        info: dict[str, Any] = {
            "hostname": hostname,
            "ip_addresses": ips,
            "resolved": True,
        }

        if ips:
            try:
                hostname, aliaslist, _ = socket.gethostbyaddr(ips[0])
                info["reverse_dns"] = hostname
                info["aliases"] = aliaslist or []
            except socket.herror:
                info["reverse_dns"] = None

        return info
    except socket.gaierror as exc:
        return {"hostname": hostname, "resolved": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("get_network_info fehlgeschlagen")
        return {"hostname": hostname, "resolved": False, "error": str(exc)}
