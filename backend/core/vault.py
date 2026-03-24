"""
Ninko Vault – Secrets Store mit HashiCorp Vault und SQLite-Fallback.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path

import aiosqlite
from cryptography.fernet import Fernet, InvalidToken

from core.config import get_settings

logger = logging.getLogger("ninko.vault")


class VaultClient:
    """
    Secrets Store – unterstützt:
    - HashiCorp Vault (Production)
    - SQLite-Fallback (Entwicklung)
    """

    VAULT_MOUNT = "secret"
    VAULT_PATH_PREFIX = "ninko"
    SQLITE_DB_PATH = "/app/data/secrets.db"

    def __init__(self) -> None:
        self._settings = get_settings()
        self._backend: str = "vault"
        self._hvac_client = None
        self._fernet: Fernet | None = None

        if self._settings.VAULT_TOKEN and self._settings.VAULT_ADDR:
            self._init_vault()
        elif self._settings.VAULT_FALLBACK == "sqlite":
            self._init_sqlite()
        else:
            logger.warning(
                "Kein Secrets-Backend konfiguriert. "
                "Setze VAULT_TOKEN oder VAULT_FALLBACK=sqlite."
            )

    def _init_vault(self) -> None:
        """Initialisiert den HashiCorp Vault Client."""
        try:
            import hvac

            self._hvac_client = hvac.Client(
                url=self._settings.VAULT_ADDR,
                token=self._settings.VAULT_TOKEN,
            )
            if self._hvac_client.is_authenticated():
                self._backend = "vault"
                logger.info("Vault-Backend initialisiert: %s", self._settings.VAULT_ADDR)
            else:
                logger.warning("Vault-Authentifizierung fehlgeschlagen – Fallback auf SQLite.")
                self._init_sqlite()
        except Exception as exc:
            logger.warning("Vault nicht erreichbar (%s) – Fallback auf SQLite.", exc)
            self._init_sqlite()

    def _init_sqlite(self) -> None:
        """Initialisiert den SQLite-Fallback."""
        self._backend = "sqlite"
        key_str = self._settings.SQLITE_SECRETS_KEY
        if not key_str:
            raise ValueError(
                "SQLITE_SECRETS_KEY ist nicht gesetzt. "
                "Bitte die Umgebungsvariable konfigurieren, um Secrets zu verschlüsseln."
            )
        key_bytes = hashlib.sha256(key_str.encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(key_bytes))

        # Sicherstellen, dass das Verzeichnis existiert
        db_dir = Path(self.SQLITE_DB_PATH).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        logger.info("SQLite Secrets-Backend initialisiert: %s", self.SQLITE_DB_PATH)

    async def _ensure_sqlite_table(self, db: aiosqlite.Connection) -> None:
        """Erstellt die Secrets-Tabelle falls nötig."""
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS secrets (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.commit()

    def _encrypt(self, data: str) -> str:
        """Fernet-Verschlüsselung (AES-128-CBC + HMAC-SHA256)."""
        if not self._fernet:
            raise RuntimeError("Kein Verschlüsselungs-Backend initialisiert.")
        return self._fernet.encrypt(data.encode()).decode()

    def _decrypt(self, data: str) -> str:
        """Fernet-Entschlüsselung."""
        if not self._fernet:
            raise RuntimeError("Kein Verschlüsselungs-Backend initialisiert.")
        try:
            return self._fernet.decrypt(data.encode()).decode()
        except InvalidToken:
            logger.error(
                "Entschlüsselung fehlgeschlagen – Token ungültig oder mit altem Schlüssel verschlüsselt."
            )
            raise

    # ── Read ───────────────────────────────────────────
    async def get_secret(self, key: str) -> str | None:
        """Liest ein Secret aus dem konfigurierten Backend."""
        if self._backend == "vault":
            return self._get_vault_secret(key)
        return await self._get_sqlite_secret(key)

    def _get_vault_secret(self, key: str) -> str | None:
        """Liest ein Secret aus Vault."""
        try:
            path = f"{self.VAULT_PATH_PREFIX}/{key}"
            result = self._hvac_client.secrets.kv.v2.read_secret_version(
                path=path, mount_point=self.VAULT_MOUNT
            )
            data = result.get("data", {}).get("data", {})
            return data.get("value")
        except Exception as exc:
            logger.debug("Vault-Secret '%s' nicht gefunden: %s", key, exc)
            return None

    async def _get_sqlite_secret(self, key: str) -> str | None:
        """Liest ein Secret aus SQLite."""
        async with aiosqlite.connect(self.SQLITE_DB_PATH) as db:
            await self._ensure_sqlite_table(db)
            async with db.execute(
                "SELECT value FROM secrets WHERE key = ?", (key,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._decrypt(row[0])
        return None

    # ── Write ──────────────────────────────────────────
    async def set_secret(self, key: str, value: str) -> None:
        """Schreibt ein Secret in das konfigurierte Backend."""
        if self._backend == "vault":
            self._set_vault_secret(key, value)
        else:
            await self._set_sqlite_secret(key, value)

    def _set_vault_secret(self, key: str, value: str) -> None:
        """Schreibt ein Secret in Vault."""
        path = f"{self.VAULT_PATH_PREFIX}/{key}"
        self._hvac_client.secrets.kv.v2.create_or_update_secret(
            path=path,
            secret={"value": value},
            mount_point=self.VAULT_MOUNT,
        )
        logger.info("Vault-Secret geschrieben: %s", key)

    async def _set_sqlite_secret(self, key: str, value: str) -> None:
        """Schreibt ein Secret in SQLite."""
        encrypted = self._encrypt(value)
        async with aiosqlite.connect(self.SQLITE_DB_PATH) as db:
            await self._ensure_sqlite_table(db)
            await db.execute(
                """
                INSERT INTO secrets (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, encrypted),
            )
            await db.commit()
        logger.info("SQLite-Secret geschrieben: %s", key)

    # ── Delete ─────────────────────────────────────────
    async def delete_secret(self, key: str) -> bool:
        """Löscht ein Secret."""
        if self._backend == "vault":
            return self._delete_vault_secret(key)
        return await self._delete_sqlite_secret(key)

    def _delete_vault_secret(self, key: str) -> bool:
        """Löscht ein Secret aus Vault."""
        try:
            path = f"{self.VAULT_PATH_PREFIX}/{key}"
            self._hvac_client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=path, mount_point=self.VAULT_MOUNT
            )
            logger.info("Vault-Secret gelöscht: %s", key)
            return True
        except Exception as exc:
            logger.warning("Vault-Secret '%s' konnte nicht gelöscht werden: %s", key, exc)
            return False

    async def _delete_sqlite_secret(self, key: str) -> bool:
        """Löscht ein Secret aus SQLite."""
        async with aiosqlite.connect(self.SQLITE_DB_PATH) as db:
            await self._ensure_sqlite_table(db)
            cursor = await db.execute("DELETE FROM secrets WHERE key = ?", (key,))
            await db.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info("SQLite-Secret gelöscht: %s", key)
            return deleted

    # ── List ───────────────────────────────────────────
    async def list_secrets(self) -> list[str]:
        """Listet alle Secret-Keys auf."""
        if self._backend == "vault":
            return self._list_vault_secrets()
        return await self._list_sqlite_secrets()

    def _list_vault_secrets(self) -> list[str]:
        """Listet alle Secret-Keys in Vault auf."""
        try:
            result = self._hvac_client.secrets.kv.v2.list_secrets(
                path=self.VAULT_PATH_PREFIX, mount_point=self.VAULT_MOUNT
            )
            return result.get("data", {}).get("keys", [])
        except Exception:
            return []

    async def _list_sqlite_secrets(self) -> list[str]:
        """Listet alle Secret-Keys in SQLite auf."""
        async with aiosqlite.connect(self.SQLITE_DB_PATH) as db:
            await self._ensure_sqlite_table(db)
            async with db.execute("SELECT key FROM secrets ORDER BY key") as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]

    # ── Health ─────────────────────────────────────────
    async def health_check(self) -> dict:
        """Prüft das Secrets-Backend."""
        if self._backend == "vault":
            try:
                if self._hvac_client and self._hvac_client.is_authenticated():
                    return {"status": "ok", "backend": "vault"}
                return {"status": "error", "backend": "vault", "detail": "Nicht authentifiziert"}
            except Exception as exc:
                return {"status": "error", "backend": "vault", "detail": str(exc)}
        else:
            try:
                async with aiosqlite.connect(self.SQLITE_DB_PATH) as db:
                    await db.execute("SELECT 1")
                return {"status": "ok", "backend": "sqlite"}
            except Exception as exc:
                return {"status": "error", "backend": "sqlite", "detail": str(exc)}

    @property
    def backend_type(self) -> str:
        """Gibt den aktuellen Backend-Typ zurück."""
        return self._backend


# Singleton
_vault: VaultClient | None = None


def get_vault() -> VaultClient:
    """Gibt die globale Vault-Instanz zurück (lazy init)."""
    global _vault
    if _vault is None:
        _vault = VaultClient()
    return _vault
