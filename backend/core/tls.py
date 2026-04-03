"""
TLS helper for module connections.

Supports:
- verify on/off via connection config key `verify_ssl`
- optional custom CA certificate from Vault secret (`ca_cert_pem` / `CA_CERT_PEM`)
"""

from __future__ import annotations

import base64
import binascii
import logging
from pathlib import Path

from core.vault import get_vault

logger = logging.getLogger("ninko.core.tls")


def _is_probably_base64(data: str) -> bool:
    s = "".join(data.strip().split())
    if not s or len(s) % 4 != 0:
        return False
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
    return all(ch in alphabet for ch in s)


def _decode_pem(secret_value: str) -> str:
    raw = (secret_value or "").strip()
    if not raw:
        return ""
    if "BEGIN CERTIFICATE" in raw:
        return raw
    if _is_probably_base64(raw):
        try:
            decoded = base64.b64decode(raw).decode("utf-8", errors="replace").strip()
            if "BEGIN CERTIFICATE" in decoded:
                return decoded
        except (ValueError, UnicodeDecodeError, binascii.Error):
            pass
    return raw


async def get_connection_verify_arg(
    conn,
    module_id: str,
    default_verify: bool = True,
) -> bool | str:
    """
    Returns value for httpx `verify` parameter:
    - False if verify_ssl is disabled in connection config
    - path to CA PEM file if configured
    - True otherwise
    """
    if conn is None:
        return default_verify

    verify_ssl = str(conn.config.get("verify_ssl", str(default_verify))).lower() == "true"
    if not verify_ssl:
        return False

    vault = get_vault()
    cert_vk = (
        conn.vault_keys.get("ca_cert_pem")
        or conn.vault_keys.get("CA_CERT_PEM")
    )
    if not cert_vk:
        return True

    cert_secret = await vault.get_secret(cert_vk)
    cert_pem = _decode_pem(cert_secret or "")
    if not cert_pem:
        return True

    cert_dir = Path("/tmp/ninko-certs")
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / f"{module_id}_{conn.id}_ca.pem"
    cert_path.write_text(cert_pem, encoding="utf-8")
    logger.info("TLS CA-Zertifikat für Modul '%s' geladen: %s", module_id, cert_path)
    return str(cert_path)
