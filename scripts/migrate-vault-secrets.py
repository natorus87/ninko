#!/usr/bin/env python3
"""
Vault Secrets Migration Script
==============================

Migriert SQLite-Vault-Secrets von älteren Verschlüsselungsmethoden zu PBKDF2-210k.

Unterstützt Migration von:
1. SHA256-direct (v1.0.0 original)
2. PBKDF2-100k (zwischenzeitlicher Standard)
3. PBKDF2-210k (aktuell, CWE-326 compliant)

Usage:
    # Lokale SQLite-DB migrieren
    python3 scripts/migrate-vault-secrets.py --db /app/data/secrets.db --key "$SQLITE_SECRETS_KEY"

    # Kubernetes Pod
    kubectl exec -n ninko deployment/ninko-backend -- python3 /app/scripts/migrate-vault-secrets.py --db /app/data/secrets.db --key "$SQLITE_SECRETS_KEY"

    # Dry-run (nur analysieren, nichts ändern)
    python3 scripts/migrate-vault-secrets.py --db /app/data/secrets.db --key "$SQLITE_SECRETS_KEY" --dry-run

Args:
    --db PATH       Pfad zur SQLite-Datenbank (default: /app/data/secrets.db)
    --key KEY       Der SQLITE_SECRETS_KEY für Verschlüsselung
    --dry-run       Nur analysieren, keine Änderungen vornehmen
    --verbose       Detaillierte Ausgabe

Exit Codes:
    0 - Alle Secrets erfolgreich migriert oder keine zu migrieren
    1 - Fehler bei der Migration (Details in Logs)
    2 - Einige Secrets konnten nicht migriert werden (manuelle Neu-Konfiguration nötig)
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import sys
from pathlib import Path

import aiosqlite
from cryptography.fernet import Fernet, InvalidToken


def create_fernet_keys(key_str: str) -> dict[str, Fernet]:
    """Erstellt alle unterstützten Fernet-Keys für die Migration."""
    keys: dict[str, Fernet] = {}

    # V1: SHA256-direct (original v1.0.0)
    v1_key = hashlib.sha256(key_str.encode()).digest()
    keys["v1_sha256"] = Fernet(base64.urlsafe_b64encode(v1_key))

    # V2: PBKDF2-100k (zwischenzeitlicher Standard)
    v2_key = hashlib.pbkdf2_hmac(
        "sha256", key_str.encode(), b"ninko_sqlite_secrets_v1", 100_000
    )
    keys["v2_pbkdf2_100k"] = Fernet(base64.urlsafe_b64encode(v2_key))

    # V3: PBKDF2-210k (aktuell, CWE-326 compliant)
    v3_key = hashlib.pbkdf2_hmac(
        "sha256", key_str.encode(), b"ninko_sqlite_secrets_v1", 210_000
    )
    keys["v3_pbkdf2_210k"] = Fernet(base64.urlsafe_b64encode(v3_key))

    return keys


def decrypt_with_any_key(
    encrypted: str, keys: dict[str, Fernet]
) -> tuple[str | None, str | None]:
    """
    Versucht das Secret mit allen verfügbaren Keys zu entschlüsseln.

    Returns:
        (value, version) - value ist None wenn keine Entschlüsselung möglich
    """
    for version, fernet in keys.items():
        try:
            decrypted = fernet.decrypt(encrypted.encode()).decode()
            return decrypted, version
        except InvalidToken:
            continue
    return None, None


def encrypt_with_v3(value: str, keys: dict[str, Fernet]) -> str:
    """Verschlüsselt mit dem aktuellen V3-Key (PBKDF2-210k)."""
    return keys["v3_pbkdf2_210k"].encrypt(value.encode()).decode()


async def migrate_secrets(
    db_path: str, key_str: str, dry_run: bool = False, verbose: bool = False
) -> int:
    """
    Migriert alle Secrets in der Datenbank.

    Returns:
        Exit-Code (0 = success, 2 = partial success)
    """
    keys = create_fernet_keys(key_str)

    if not Path(db_path).exists():
        print(f"❌ Datenbank nicht gefunden: {db_path}")
        return 1

    stats = {
        "total": 0,
        "migrated": 0,
        "already_v3": 0,
        "failed": 0,
        "by_version": {},
    }

    failed_secrets: list[str] = []

    async with aiosqlite.connect(db_path) as db:
        # Prüfe ob Tabelle existiert
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='secrets'"
        ) as cur:
            if not await cur.fetchone():
                print("ℹ️  Keine secrets-Tabelle gefunden (leere Datenbank)")
                return 0

        # Lade alle Secrets
        async with db.execute("SELECT key, value FROM secrets") as cur:
            rows = await cur.fetchall()

        stats["total"] = len(rows)

        if verbose:
            print(f"\n🔍 Gefundene Secrets: {len(rows)}")
            print("=" * 60)

        for key, encrypted_value in rows:
            # Versuche zu entschlüsseln
            decrypted, version = decrypt_with_any_key(encrypted_value, keys)

            if decrypted is None:
                # Konnte nicht entschlüsselt werden
                stats["failed"] += 1
                failed_secrets.append(key)
                if verbose:
                    print(f"❌ {key}: Konnte nicht entschlüsselt werden")
                continue

            if version == "v3_pbkdf2_210k":
                # Bereits aktuell
                stats["already_v3"] += 1
                if verbose:
                    print(f"✅ {key}: Bereits V3 (PBKDF2-210k)")
                continue

            # Migrations-Statistik
            stats["by_version"][version] = stats["by_version"].get(version, 0) + 1

            if dry_run:
                if verbose:
                    print(f"📋 {key}: Würde migrieren {version} → v3_pbkdf2_210k")
                stats["migrated"] += 1
                continue

            # Echte Migration
            new_encrypted = encrypt_with_v3(decrypted, keys)

            await db.execute(
                "UPDATE secrets SET value = ? WHERE key = ?", (new_encrypted, key)
            )

            stats["migrated"] += 1
            if verbose:
                print(f"✅ {key}: Migriert {version} → v3_pbkdf2_210k")

    # Zusammenfassung
    print("\n" + "=" * 60)
    print("📊 Migrations-Zusammenfassung")
    print("=" * 60)
    print(f"  Total Secrets:       {stats['total']}")
    print(f"  Bereits V3:          {stats['already_v3']}")
    print(f"  Migriert:            {stats['migrated']}")

    if stats["by_version"]:
        print("\n  Migriert von:")
        for version, count in sorted(stats["by_version"].items()):
            print(f"    - {version}: {count}")

    if stats["failed"] > 0:
        print(f"\n  ⚠️  Fehlgeschlagen:   {stats['failed']}")
        print("\n  Folgende Secrets müssen neu konfiguriert werden:")
        for key in failed_secrets:
            print(f"    - {key}")

    if dry_run:
        print("\n📋 DRY-RUN: Keine Änderungen vorgenommen")
        print("   Führe ohne --dry-run aus um zu migrieren")
    else:
        print(
            f"\n✅ Migration {'teilweise ' if stats['failed'] > 0 else ''}abgeschlossen"
        )

    # Exit-Code
    if stats["failed"] > 0:
        return 2  # Teilweise erfolgreich
    return 0  # Vollständig erfolgreich


def main():
    parser = argparse.ArgumentParser(
        description="Migriert Vault Secrets zu PBKDF2-210k (CWE-326 compliant)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  # Standard-DB migrieren
  python3 migrate-vault-secrets.py --key "mein-schluessel"
  
  # Mit benutzerdefiniertem DB-Pfad
  python3 migrate-vault-secrets.py --db /pfad/zu/secrets.db --key "schluessel"
  
  # Nur analysieren (dry-run)
  python3 migrate-vault-secrets.py --key "schluessel" --dry-run --verbose
  
  # In Kubernetes
  kubectl exec -n ninko deployment/ninko-backend -- \
    python3 /app/scripts/migrate-vault-secrets.py --key "$SQLITE_SECRETS_KEY"
        """,
    )

    parser.add_argument(
        "--db",
        default="/app/data/secrets.db",
        help="Pfad zur SQLite-Datenbank (default: /app/data/secrets.db)",
    )
    parser.add_argument(
        "--key", required=True, help="SQLITE_SECRETS_KEY für die Verschlüsselung"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur analysieren, keine Änderungen vornehmen",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Detaillierte Ausgabe pro Secret"
    )

    args = parser.parse_args()

    print("🔐 Vault Secrets Migration")
    print("=" * 60)
    print(f"Datenbank: {args.db}")
    print(f"Dry-Run:   {'Ja' if args.dry_run else 'Nein'}")
    print(f"Verbose:   {'Ja' if args.verbose else 'Nein'}")
    print("=" * 60)

    try:
        exit_code = asyncio.run(
            migrate_secrets(
                db_path=args.db,
                key_str=args.key,
                dry_run=args.dry_run,
                verbose=args.verbose,
            )
        )
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
