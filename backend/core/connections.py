"""
Ninko Connection Manager.
Handhabt Multi-Connection CRUD Operationen mit Metadaten in Redis und Secrets in HashiCorp Vault.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import List, Optional

from core import status_bus
from core.redaction import is_sensitive_key
from core.redis_client import get_redis
from core.vault import get_vault
from schemas.connection import ConnectionCreate, ConnectionRead, ConnectionUpdate

# Per-module asyncio locks prevent concurrent R-M-W races on connections
_connection_locks: dict[str, asyncio.Lock] = {}


def _get_connection_lock(module_id: str) -> asyncio.Lock:
    if module_id not in _connection_locks:
        _connection_locks[module_id] = asyncio.Lock()
    return _connection_locks[module_id]


logger = logging.getLogger("ninko.core.connections")


def _has_sensitive_config_fields(config: dict) -> list[str]:
    if not config:
        return []
    return [key for key in config if is_sensitive_key(key)]


def _redact_connection_data(data: dict) -> dict:
    result = dict(data)
    config = result.get("config") or {}
    if config:
        suspicious = _has_sensitive_config_fields(config)
        if suspicious:
            redacted_config = dict(config)
            for key in suspicious:
                redacted_config[key] = "***REDACTED***"
            result["config"] = redacted_config
    return result


class ConnectionManager:
    """Manager für Modul-Verbindungen."""

    @staticmethod
    def _effective_tenant_id(tenant_id: str = "") -> str:
        t = (tenant_id or "").strip().lower()
        if t:
            return t
        try:
            from core.auth import get_current_tenant_id

            auth_tenant = (get_current_tenant_id() or "").strip().lower()
            if auth_tenant:
                return auth_tenant
        except (ImportError, AttributeError, RuntimeError):
            pass
        session_id = status_bus.get_session_id().strip()
        if ":" in session_id:
            return session_id.split(":", 1)[0].strip().lower() or "default"
        return "default"

    @staticmethod
    def _get_redis_key(module_id: str, tenant_id: str = "") -> str:
        tenant = ConnectionManager._effective_tenant_id(tenant_id)
        return f"ninko:connections:{tenant}:{module_id}"

    @staticmethod
    def _get_legacy_redis_key(module_id: str) -> str:
        # Legacy format (pre multi-tenant connections):
        # ninko:connections:<module_id>
        return f"ninko:connections:{module_id}"

    @staticmethod
    async def list_connections(module_id: str, tenant_id: str = "") -> List[ConnectionRead]:
        """Holt alle konfigurierten Verbindungen für ein Modul."""
        redis = get_redis()
        tenant = ConnectionManager._effective_tenant_id(tenant_id)
        key = ConnectionManager._get_redis_key(module_id, tenant)
        raw = await redis.connection.get(key)

        # Backward compatibility: migrate old key format into default tenant key.
        if not raw and tenant == "default":
            legacy_key = ConnectionManager._get_legacy_redis_key(module_id)
            legacy_raw = await redis.connection.get(legacy_key)
            if legacy_raw:
                raw = legacy_raw
                await redis.connection.set(key, legacy_raw)
                logger.info(
                    "Connection key auto-migrated: %s -> %s",
                    legacy_key,
                    key,
                )

        if not raw:
            return []

        data_list: List[dict] = json.loads(raw)
        connections = []
        for d in data_list:
            try:
                connections.append(ConnectionRead(**d))
            except (RuntimeError, ValueError, TypeError, KeyError) as e:
                logger.error("Fehler beim Parsen von Connection %s: %s", d.get("id"), e)

        # Sortiere so, dass default ganz oben steht
        connections.sort(key=lambda x: (not x.is_default, x.name))
        return connections

    @staticmethod
    async def get_connection(module_id: str, connection_id: str, tenant_id: str = "") -> Optional[ConnectionRead]:
        """Holt eine spezifische Verbindung per ID."""
        connections = await ConnectionManager.list_connections(module_id, tenant_id)
        for conn in connections:
            if conn.id == connection_id:
                return conn
        return None

    @staticmethod
    async def get_default_connection(module_id: str, tenant_id: str = "") -> Optional[ConnectionRead]:
        """Holt die Standardverbindung für ein Modul."""
        connections = await ConnectionManager.list_connections(module_id, tenant_id)
        if not connections:
            return None

        for conn in connections:
            if conn.is_default:
                return conn

        # Fallback auf die erste
        return connections[0]

    @staticmethod
    async def create_connection(module_id: str, data: ConnectionCreate, tenant_id: str = "") -> ConnectionRead:
        """Erstellt eine neue Verbindung und speichert Daten sicher ab."""
        tenant = ConnectionManager._effective_tenant_id(tenant_id)
        async with _get_connection_lock(module_id):
            connections = await ConnectionManager.list_connections(module_id, tenant)

            conn_id = str(uuid.uuid4())
            vault = get_vault()

            # Secrets im Vault ablegen und Keys notieren
            vault_keys = {}
            if data.secrets:
                for secret_key, secret_val in data.secrets.items():
                    if secret_val:
                        v_key = f"{module_id}_{conn_id}_{secret_key}".upper()
                        await vault.set_secret(v_key, secret_val)
                        vault_keys[secret_key] = v_key

            # Falls es die erste Verbindung ist, automatisch zum Default machen
            is_default = data.is_default or len(connections) == 0

            if is_default:
                for c in connections:
                    c.is_default = False

            new_conn = ConnectionRead(
                id=conn_id,
                module_id=module_id,
                name=data.name,
                environment=data.environment,
                description=data.description,
                is_default=is_default,
                config=data.config,
                vault_keys=vault_keys
            )

            connections.append(new_conn)
            await ConnectionManager._save_connections(module_id, connections, tenant)
            logger.info("Verbindung erstellt: %s im Modul %s (ID: %s)", data.name, module_id, conn_id)

            return new_conn

    @staticmethod
    async def update_connection(module_id: str, connection_id: str, data: ConnectionUpdate, tenant_id: str = "") -> Optional[ConnectionRead]:
        """Aktualisiert eine bestehende Verbindung."""
        tenant = ConnectionManager._effective_tenant_id(tenant_id)
        async with _get_connection_lock(module_id):
            connections = await ConnectionManager.list_connections(module_id, tenant)
            target = next((c for c in connections if c.id == connection_id), None)

            if not target:
                return None

            # Metadaten updaten
            if data.name is not None:
                target.name = data.name
            if data.environment is not None:
                target.environment = data.environment
            if data.description is not None:
                target.description = data.description
            if data.config is not None:
                target.config = data.config

            # Default Logik
            if data.is_default:
                target.is_default = True
                for c in connections:
                    if c.id != target.id:
                        c.is_default = False

            # Secrets updaten
            if data.secrets is not None:
                vault = get_vault()
                for secret_key, secret_val in data.secrets.items():
                    if secret_val:
                        v_key = f"{module_id}_{target.id}_{secret_key}".upper()
                        await vault.set_secret(v_key, secret_val)
                        target.vault_keys[secret_key] = v_key

            await ConnectionManager._save_connections(module_id, connections, tenant)
            logger.info("Verbindung aktualisiert: %s im Modul %s", target.name, module_id)
            return target

    @staticmethod
    async def delete_connection(module_id: str, connection_id: str, tenant_id: str = "") -> bool:
        """Löscht eine Verbindung komplett auf Basis ihrer ID, inklusive Secrets aus Vault."""
        tenant = ConnectionManager._effective_tenant_id(tenant_id)
        async with _get_connection_lock(module_id):
            logger.info("START delete_connection: module=%s, id=%s", module_id, connection_id)
            connections = await ConnectionManager.list_connections(module_id, tenant)
            target = next((c for c in connections if c.id == connection_id), None)

            if not target:
                logger.info("Target connection %s not found during delete. Existing: %s", connection_id, [c.id for c in connections])
                return False

            # Erst Redis aktualisieren, DANN Vault-Secrets löschen.
            # Sonst: Wenn _save_connections crasht (Redis-Disconnect etc.),
            # sind die Secrets bereits gelöscht → unwiederbringlich weg.
            connections = [c for c in connections if c.id != connection_id]

            # Wenn wir den Default gelöscht haben, ersten verbliebenen zum Default machen
            if target.is_default and connections:
                connections[0].is_default = True

            await ConnectionManager._save_connections(module_id, connections, tenant)

            # Secrets aus Vault löschen (erst nachdem Redis-Update erfolgreich war)
            vault = get_vault()
            for v_key in target.vault_keys.values():
                await vault.delete_secret(v_key)

            logger.info("Verbindung gelöscht: %s im Modul %s", target.name, module_id)
            return True

    @staticmethod
    async def _save_connections(module_id: str, connections: List[ConnectionRead], tenant_id: str = "") -> None:
        redis = get_redis()
        key = ConnectionManager._get_redis_key(module_id, tenant_id)
        data = [json.loads(c.model_dump_json()) for c in connections]

        # CWE-312: Warn if any connection's config contains sensitive field names.
        # These should be stored in 'secrets' + Vault, not in plaintext 'config'.
        for conn in connections:
            if hasattr(conn, 'config') and conn.config:
                suspicious = _has_sensitive_config_fields(conn.config)
                if suspicious:
                    logger.warning(
                        "CWE-312: Verbindung '%s' (Modul '%s') enthält möglicherweise "
                        "sensitive Felder in config (nicht in secrets): %s — "
                        "Diese Werte werden im Klartext in Redis gespeichert. "
                        "Bitte 'secrets' statt 'config' für Credentials verwenden.",
                        conn.name,
                        module_id,
                        suspicious,
                    )

        logger.info(
            "Speichere %d Verbindungen für %s in Redis Key %s",
            len(connections),
            module_id,
            key,
        )
        await redis.connection.set(key, json.dumps(data))
