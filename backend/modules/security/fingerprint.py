"""Security Core — stabile Fingerprints fuer Finding-Deduplizierung.

Ein Finding, das in einem spaeteren Run erneut auftritt, muss denselben
Fingerprint erzeugen, damit es aktualisiert statt dupliziert wird. Der
Fingerprint ist bewusst scanner- und target-spezifisch, aber unabhaengig
von Scan-Run-ID oder Zeitstempel.
"""

from __future__ import annotations

import hashlib


def compute_fingerprint(
    *,
    scanner_id: str,
    target_id: str,
    rule_id: str,
    resource_identifier: str = "",
    location: str = "",
    cve: str | None = None,
    cwe: str | None = None,
) -> str:
    """Baut einen stabilen SHA-256-Fingerprint aus normalisierten Identifikatoren.

    Enthaelt bewusst KEINE laufzeitabhaengigen Werte (Zeitstempel, Scan-Run-ID,
    Severity) — nur Werte, die ein erneuter Fund fuer dasselbe Problem am
    selben Ort wieder identisch liefern wuerde.
    """
    parts = [
        scanner_id.strip().lower(),
        target_id.strip().lower(),
        rule_id.strip().lower(),
        resource_identifier.strip().lower(),
        location.strip().lower(),
        (cve or "").strip().upper(),
        (cwe or "").strip().upper(),
    ]
    canonical = "|".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
