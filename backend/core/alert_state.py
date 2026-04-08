"""
Alert State Manager – Redis-basiertes Alert-Tracking mit Deduplication.

Dieses Modul implementiert ein deterministisches Alert-State-System für Ninko.
Es verhindert Duplicate-Alerts durch atomare Redis-Operationen (SET NX EX).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from core.redis_client import get_redis

logger = logging.getLogger("ninko.alerts")


class AlertStateManager:
    """
    Verwaltet Alert-States in Redis mit TTL-Support und atomaren Operationen.

    Key-Schema:
    - ninko:alerts:active:{alert_id}  → Alert-Metadaten (TTL 7d)
    - ninko:alerts:notify:{alert_id}  → Cooldown-Flag (TTL = cooldown_seconds)
    - ninko:alerts:history:{alert_id} → Archivierte Alerts (TTL 30d)
    """

    ACTIVE_PREFIX = "ninko:alerts:active:"
    NOTIFY_PREFIX = "ninko:alerts:notify:"
    HISTORY_PREFIX = "ninko:alerts:history:"

    DEFAULT_TTL = 604800
    HISTORY_TTL = 2592000
    DEFAULT_COOLDOWN = 86400

    def __init__(self) -> None:
        self._redis = get_redis()

    @staticmethod
    def make_id(module: str, resource: str, reason: str) -> str:
        """
        Erzeugt eine deterministische Alert-ID.

        Format: module:resource:reason (alles lowercase, alphanumerisch + Bindestrich)

        Args:
            module: Modul-Name (z.B. "kubernetes", "proxmox")
            resource: Resource-Name (z.B. "nginx-pod", "vm-100")
            reason: Fehlergrund (z.B. "CrashLoopBackOff")

        Returns:
            Sanitisierte Alert-ID

        Example:
            >>> AlertStateManager.make_id("kubernetes", "nginx-pod", "CrashLoopBackOff")
            'kubernetes:nginx-pod:crashloopbackoff'
        """

        def sanitize(s: str) -> str:
            s = s.lower().strip()
            s = re.sub(r"[^a-z0-9-]+", "-", s)
            s = re.sub(r"-+", "-", s)
            return s.strip("-")

        return f"{sanitize(module)}:{sanitize(resource)}:{sanitize(reason)}"

    async def get_state(self, alert_id: str) -> dict | None:
        """
        Gibt den aktiven Alert-State zurück oder None.

        Args:
            alert_id: Die Alert-ID

        Returns:
            Alert-Daten als dict oder None wenn nicht aktiv
        """
        key = f"{self.ACTIVE_PREFIX}{alert_id}"
        data = await self._redis.connection.get(key)
        if data:
            return json.loads(data)
        return None

    async def is_active(self, alert_id: str) -> bool:
        """
        Schneller Existenz-Check für einen aktiven Alert.

        Args:
            alert_id: Die Alert-ID

        Returns:
            True wenn Alert aktiv, False sonst
        """
        key = f"{self.ACTIVE_PREFIX}{alert_id}"
        exists = await self._redis.connection.exists(key)
        return bool(exists)

    async def record(
        self,
        alert_id: str,
        *,
        module: str,
        severity: str,
        summary: str,
        resource: str = "",
        reason: str = "",
        ticket_id: str = "",
        ttl: int = DEFAULT_TTL,
    ) -> dict:
        """
        Speichert oder aktualisiert einen Alert.

        Bei NEUEM Alert:
        - Erstellt Eintrag mit first_seen, last_seen, last_notified
        - Setzt notify_count auf 1

        Bei BESTEHENDEM Alert:
        - Aktualisiert nur last_seen und notify_count (falls Notification)
        - first_seen bleibt unverändert

        Args:
            alert_id: Die Alert-ID
            module: Modul-Name
            severity: Severity-Level (critical, warning, info)
            summary: Kurze Beschreibung
            resource: Optionale Resource-Info
            reason: Optionaler Fehlergrund
            ticket_id: Optionale Ticket-Referenz
            ttl: TTL in Sekunden (default 7 Tage)

        Returns:
            Alert-State-Daten mit is_new-Flag

        Raises:
            ValueError: Wenn severity ungültig
        """
        if severity not in ("critical", "warning", "info"):
            severity = "warning"

        key = f"{self.ACTIVE_PREFIX}{alert_id}"
        now = datetime.now(timezone.utc).isoformat()

        existing_data = await self._redis.connection.get(key)

        if existing_data:
            existing = json.loads(existing_data)
            existing["last_seen"] = now
            existing["notify_count"] = existing.get("notify_count", 0)

            if ticket_id and not existing.get("ticket_id"):
                existing["ticket_id"] = ticket_id

            await self._redis.connection.setex(key, ttl, json.dumps(existing))

            logger.debug("Alert %s aktualisiert (last_seen)", alert_id)
            return {**existing, "is_new": False}
        else:
            data = {
                "alert_id": alert_id,
                "module": module,
                "resource": resource or module,
                "reason": reason or "unknown",
                "severity": severity,
                "summary": summary,
                "ticket_id": ticket_id,
                "status": "active",
                "first_seen": now,
                "last_seen": now,
                "last_notified": now,
                "notify_count": 1,
            }

            await self._redis.connection.setex(key, ttl, json.dumps(data))

            logger.info("Neuer Alert aufgezeichnet: %s (%s)", alert_id, module)
            return {**data, "is_new": True}

    async def record_notification(
        self,
        alert_id: str,
        ticket_id: str = "",
    ) -> dict:
        """
        Aktualisiert Notification-Metadaten nach einem erfolgreichen Versand.

        Args:
            alert_id: Die Alert-ID
            ticket_id: Optionale Ticket-Referenz

        Returns:
            Aktualisierter Alert-State
        """
        key = f"{self.ACTIVE_PREFIX}{alert_id}"
        data = await self._redis.connection.get(key)

        if not data:
            logger.warning(
                "Versuch Notification für nicht-existierenden Alert %s zu recorden",
                alert_id,
            )
            return None

        alert = json.loads(data)
        now = datetime.now(timezone.utc).isoformat()

        alert["last_notified"] = now
        alert["notify_count"] = alert.get("notify_count", 0) + 1
        if ticket_id:
            alert["ticket_id"] = ticket_id

        await self._redis.connection.setex(key, self.DEFAULT_TTL, json.dumps(alert))

        logger.debug(
            "Notification für Alert %s recorded (count=%d)",
            alert_id,
            alert["notify_count"],
        )
        return alert

    async def resolve(self, alert_id: str, resolution: str = "") -> bool:
        """
        Markiert einen Alert als gelöst und archiviert ihn.

        Args:
            alert_id: Die Alert-ID
            resolution: Optionale Beschreibung der Resolution

        Returns:
            True wenn Alert existierte und resolved wurde, False sonst
        """
        active_key = f"{self.ACTIVE_PREFIX}{alert_id}"
        history_key = f"{self.HISTORY_PREFIX}{alert_id}"

        data = await self._redis.connection.get(active_key)
        if not data:
            logger.debug(
                "Resolve für nicht-existierenden Alert %s (idempotent)", alert_id
            )
            return False

        alert = json.loads(data)
        now = datetime.now(timezone.utc).isoformat()

        alert["status"] = "resolved"
        alert["resolved_at"] = now
        alert["resolution"] = resolution or "Manually resolved"

        pipe = self._redis.connection.pipeline()
        pipe.delete(active_key)
        pipe.setex(history_key, self.HISTORY_TTL, json.dumps(alert))
        await pipe.execute()

        logger.info("Alert %s resolved und archiviert", alert_id)
        return True

    async def should_notify(
        self,
        alert_id: str,
        cooldown_seconds: int = DEFAULT_COOLDOWN,
    ) -> bool:
        """
        Prüft ob eine Notification erlaubt ist (Cooldown-Check).

        Nutzt atomares SET NX EX für Race-Condition-freien Check:
        - Wenn notify-Key nicht existiert: Erstellt ihn mit TTL, gibt True zurück
        - Wenn notify-Key existiert: Gibt False zurück (Cooldown aktiv)

        Args:
            alert_id: Die Alert-ID
            cooldown_seconds: Cooldown in Sekunden (default 24h)

        Returns:
            True wenn Notification erlaubt, False wenn Cooldown aktiv
        """
        notify_key = f"{self.NOTIFY_PREFIX}{alert_id}"

        # Versuche atomar zu setzen - nur wenn Key nicht existiert
        success = await self._redis.connection.set(
            notify_key,
            "1",
            nx=True,
            ex=cooldown_seconds,
        )

        if success:
            logger.debug(
                "Notification erlaubt für %s (Cooldown: %ds)",
                alert_id,
                cooldown_seconds,
            )
            return True
        else:
            ttl = await self._redis.connection.ttl(notify_key)
            logger.debug(
                "Notification BLOCKIERT für %s (Cooldown aktiv, TTL: %ds)",
                alert_id,
                ttl,
            )
            return False

    async def list_active(self, module: str | None = None) -> list[dict]:
        """
        Listet alle aktiven Alerts (optional gefiltert nach Modul).

        Args:
            module: Optional Modul-Name zum Filtern

        Returns:
            Liste von Alert-Daten

        Note:
            Verwendet Redis KEYS Scan (nur für Dashboard/Admin, nicht für Hot-Path)
        """
        pattern = f"{self.ACTIVE_PREFIX}*"
        keys = []

        # Scan ist besser als KEYS bei vielen Einträgen
        async for key in self._redis.connection.scan_iter(match=pattern, count=100):
            keys.append(key)

        if not keys:
            return []

        values = await self._redis.connection.mget(keys)
        alerts = []

        for key, value in zip(keys, values):
            if value:
                alert = json.loads(value)
                if module is None or alert.get("module") == module:
                    alerts.append(alert)

        # Sort: critical first, then first_seen
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        alerts.sort(
            key=lambda a: (
                severity_order.get(a.get("severity", "info"), 3),
                a.get("first_seen", ""),
            )
        )

        return alerts

    async def get_stats(self) -> dict:
        """
        Gibt Statistiken über das Alert-System zurück.

        Returns:
            Dict mit counts für active, history, notify keys
        """
        active_count = 0
        notify_count = 0
        history_count = 0

        async for _ in self._redis.connection.scan_iter(
            match=f"{self.ACTIVE_PREFIX}*", count=100
        ):
            active_count += 1

        async for _ in self._redis.connection.scan_iter(
            match=f"{self.NOTIFY_PREFIX}*", count=100
        ):
            notify_count += 1

        async for _ in self._redis.connection.scan_iter(
            match=f"{self.HISTORY_PREFIX}*", count=100
        ):
            history_count += 1

        return {
            "active": active_count,
            "cooldowns": notify_count,
            "history": history_count,
        }


# Singleton-Instanz
_alert_manager: AlertStateManager | None = None


def get_alert_manager() -> AlertStateManager:
    """Gibt die globale AlertStateManager-Instanz zurück."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertStateManager()
    return _alert_manager
