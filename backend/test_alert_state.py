"""
Tests für den AlertStateManager.

Unit-Tests mit FakeRedis (kein echter Redis nötig)
Integration-Tests gegen laufenden Redis (optional, nur wenn REDIS_URL erreichbar)
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis.asyncio as aioredis

SKIP_INTEGRATION = os.getenv("SKIP_INTEGRATION_TESTS", "false").lower() == "true"


@pytest.fixture
def fake_redis():
    """Ein Fake-Redis für Unit-Tests (einfacher In-Memory Store)."""
    store = {}
    ttl = {}

    class FakeRedis:
        async def get(self, key):
            # Prüfe TTL
            if key in ttl and ttl[key] < asyncio.get_event_loop().time():
                store.pop(key, None)
                ttl.pop(key, None)
                return None
            return store.get(key)

        async def setex(self, key, seconds, value):
            store[key] = value
            ttl[key] = asyncio.get_event_loop().time() + seconds

        async def set(self, key, value, nx=False, ex=None):
            if nx and key in store:
                # Prüfe TTL
                if key in ttl and ttl[key] < asyncio.get_event_loop().time():
                    store.pop(key, None)
                    ttl.pop(key, None)
                else:
                    return None  # Key existiert
            store[key] = value
            if ex:
                ttl[key] = asyncio.get_event_loop().time() + ex
            return True

        async def exists(self, key):
            # Prüfe TTL
            if key in ttl and ttl[key] < asyncio.get_event_loop().time():
                store.pop(key, None)
                ttl.pop(key, None)
                return 0
            return 1 if key in store else 0

        async def delete(self, *keys):
            count = 0
            for key in keys:
                if key in store:
                    store.pop(key, None)
                    ttl.pop(key, None)
                    count += 1
            return count

        async def ttl(self, key):
            if key in ttl:
                remaining = ttl[key] - asyncio.get_event_loop().time()
                return int(remaining) if remaining > 0 else -2
            return -2

        async def mget(self, keys):
            return [await self.get(k) for k in keys]

        async def pipeline(self):
            pipe = MagicMock()
            pipe.delete = lambda k: None
            pipe.setex = lambda k, s, v: None
            pipe.execute = AsyncMock(return_value=[1, 1])
            return pipe

        async def scan_iter(self, match, count=100):
            pattern = match.replace("*", "")
            for key in list(store.keys()):
                if key.startswith(pattern):
                    yield key

    return FakeRedis()


@pytest.fixture
def alert_mgr(fake_redis):
    """AlertStateManager mit FakeRedis."""
    from core.alert_state import AlertStateManager

    mgr = AlertStateManager()
    mgr._redis.connection = fake_redis
    return mgr


class TestAlertIdGeneration:
    """Tests für die Alert-ID Generierung."""

    def test_make_id_basic(self, alert_mgr):
        """Einfache ID-Generierung."""
        alert_id = alert_mgr.make_id("kubernetes", "nginx-pod", "CrashLoopBackOff")
        assert alert_id == "kubernetes:nginx-pod:crashloopbackoff"

    def test_make_id_sanitization(self, alert_mgr):
        """Sonderzeichen werden entfernt."""
        alert_id = alert_mgr.make_id(
            "K8s_Module", "nginx_pod_123", "Error: Connection failed!!!"
        )
        assert alert_id == "k8s-module:nginx-pod-123:error-connection-failed"

    def test_make_id_deterministic(self, alert_mgr):
        """Gleiche Inputs = gleiche Outputs."""
        id1 = alert_mgr.make_id("mod", "res", "reason")
        id2 = alert_mgr.make_id("mod", "res", "reason")
        assert id1 == id2

        # Case-insensitive
        id3 = alert_mgr.make_id("MOD", "RES", "REASON")
        assert id1 == id3


class TestRecordAlert:
    """Tests für das Aufzeichnen von Alerts."""

    @pytest.mark.asyncio
    async def test_record_new_alert(self, alert_mgr):
        """Neuer Alert wird korrekt gespeichert."""
        result = await alert_mgr.record(
            alert_id="test:pod:error",
            module="test",
            severity="critical",
            summary="Test error",
        )

        assert result["is_new"] is True
        assert result["alert_id"] == "test:pod:error"
        assert result["status"] == "active"
        assert result["notify_count"] == 1
        assert "first_seen" in result
        assert "last_seen" in result

    @pytest.mark.asyncio
    async def test_record_existing_updates_last_seen(self, alert_mgr):
        """Bestehender Alert aktualisiert last_seen."""
        # Erst erstellen
        first = await alert_mgr.record(
            alert_id="test:pod:error",
            module="test",
            severity="critical",
            summary="Test error",
        )

        # Kurz warten (simuliert)
        await asyncio.sleep(0.01)

        # Dann aktualisieren
        second = await alert_mgr.record(
            alert_id="test:pod:error",
            module="test",
            severity="critical",
            summary="Test error",
        )

        assert second["is_new"] is False
        assert first["first_seen"] == second["first_seen"]
        assert second["last_seen"] > first["last_seen"]

    @pytest.mark.asyncio
    async def test_is_active(self, alert_mgr):
        """Existenz-Check funktioniert."""
        # Nicht existent
        assert await alert_mgr.is_active("test:pod:error") is False

        # Erstellen
        await alert_mgr.record(
            alert_id="test:pod:error",
            module="test",
            severity="critical",
            summary="Test error",
        )

        # Jetzt existent
        assert await alert_mgr.is_active("test:pod:error") is True

    @pytest.mark.asyncio
    async def test_get_state(self, alert_mgr):
        """State-Abruf funktioniert."""
        # Nicht existent
        state = await alert_mgr.get_state("test:pod:error")
        assert state is None

        # Erstellen
        await alert_mgr.record(
            alert_id="test:pod:error",
            module="test",
            severity="critical",
            summary="Test error",
            ticket_id="TICKET-123",
        )

        # Abrufen
        state = await alert_mgr.get_state("test:pod:error")
        assert state is not None
        assert state["module"] == "test"
        assert state["severity"] == "critical"
        assert state["ticket_id"] == "TICKET-123"


class TestResolveAlert:
    """Tests für das Resolven von Alerts."""

    @pytest.mark.asyncio
    async def test_resolve_active_alert(self, alert_mgr):
        """Aktiver Alert wird resolved."""
        # Erstellen
        await alert_mgr.record(
            alert_id="test:pod:error",
            module="test",
            severity="critical",
            summary="Test error",
        )

        # Resolve
        resolved = await alert_mgr.resolve("test:pod:error", "Fixed")
        assert resolved is True

        # Nicht mehr aktiv
        assert await alert_mgr.is_active("test:pod:error") is False

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_idempotent(self, alert_mgr):
        """Resolve nicht-existierenden Alert ist idempotent."""
        resolved = await alert_mgr.resolve("test:does:not:exist", "Fixed")
        assert resolved is False  # Kein Fehler geworfen


class TestNotificationCooldown:
    """Tests für den Notification-Cooldown."""

    @pytest.mark.asyncio
    async def test_should_notify_first_time(self, alert_mgr):
        """Erstmalig sollte Notification erlaubt sein."""
        allowed = await alert_mgr.should_notify("test:pod:error", cooldown_seconds=3600)
        assert allowed is True

    @pytest.mark.asyncio
    async def test_should_notify_within_cooldown(self, alert_mgr):
        """Innerhalb Cooldown sollte Notification blockiert sein."""
        # Erstmal erlaubt
        await alert_mgr.should_notify("test:pod:error", cooldown_seconds=3600)

        # Zweites Mal blockiert
        allowed = await alert_mgr.should_notify("test:pod:error", cooldown_seconds=3600)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_should_notify_after_cooldown_expires(self, alert_mgr):
        """Nach Ablauf des Cooldowns wieder erlaubt."""
        # Kurzer Cooldown für Test
        await alert_mgr.should_notify("test:pod:error", cooldown_seconds=1)

        # Warten bis Cooldown abläuft
        await asyncio.sleep(1.1)

        # Jetzt wieder erlaubt
        allowed = await alert_mgr.should_notify("test:pod:error", cooldown_seconds=3600)
        assert allowed is True


class TestListActive:
    """Tests für das Listen aktiver Alerts."""

    @pytest.mark.asyncio
    async def test_list_active_empty(self, alert_mgr):
        """Leere Liste wenn keine Alerts."""
        alerts = await alert_mgr.list_active()
        assert alerts == []

    @pytest.mark.asyncio
    async def test_list_active_multiple(self, alert_mgr):
        """Mehrere Alerts werden aufgelistet."""
        await alert_mgr.record("test:pod1:error", "test", "critical", "Error 1")
        await alert_mgr.record("test:pod2:error", "test", "warning", "Error 2")
        await alert_mgr.record("other:pod:error", "other", "info", "Error 3")

        # Alle
        alerts = await alert_mgr.list_active()
        assert len(alerts) == 3

        # Gefiltert nach Modul
        test_alerts = await alert_mgr.list_active(module="test")
        assert len(test_alerts) == 2

        # Severity-Sortierung: critical first
        assert test_alerts[0]["severity"] == "critical"


class TestRecordNotification:
    """Tests für record_notification."""

    @pytest.mark.asyncio
    async def test_record_notification(self, alert_mgr):
        """Notification-Tracking funktioniert."""
        # Alert erstellen
        await alert_mgr.record(
            alert_id="test:pod:error",
            module="test",
            severity="critical",
            summary="Test",
        )

        # Notification recorden
        await alert_mgr.record_notification("test:pod:error", "TICKET-123")

        # Prüfen
        state = await alert_mgr.get_state("test:pod:error")
        assert state["notify_count"] == 2  # Initial + 1
        assert state["ticket_id"] == "TICKET-123"


@pytest.mark.skipif(SKIP_INTEGRATION, reason="Integration tests disabled")
@pytest.mark.asyncio
class TestIntegration:
    """Integration-Tests gegen echten Redis."""

    async def get_real_alert_mgr(self):
        """Erstellt AlertStateManager mit echtem Redis."""
        from core.alert_state import AlertStateManager
        from core.redis_client import get_redis

        mgr = AlertStateManager()
        # Test-Keys mit Prefix um Konflikte zu vermeiden
        mgr.ACTIVE_PREFIX = "ninko:test:alerts:active:"
        mgr.NOTIFY_PREFIX = "ninko:test:alerts:notify:"
        mgr.HISTORY_PREFIX = "ninko:test:alerts:history:"

        # Cleanup vorher
        redis = get_redis().connection
        for pattern in [
            "ninko:test:alerts:active:*",
            "ninko:test:alerts:notify:*",
            "ninko:test:alerts:history:*",
        ]:
            keys = []
            async for key in redis.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await redis.delete(*keys)

        return mgr

    async def test_full_flow(self):
        """Kompletter Flow mit echtem Redis."""
        mgr = await self.get_real_alert_mgr()

        # 1. Record
        state = await mgr.record(
            alert_id="integration:test:error",
            module="integration",
            severity="critical",
            summary="Test error",
        )
        assert state["is_new"] is True

        # 2. Check exists
        assert await mgr.is_active("integration:test:error") is True

        # 3. Cooldown check (erstes Mal erlaubt)
        allowed = await mgr.should_notify("integration:test:error", cooldown_seconds=60)
        assert allowed is True

        # 4. Cooldown check (zweites Mal blockiert)
        allowed = await mgr.should_notify("integration:test:error", cooldown_seconds=60)
        assert allowed is False

        # 5. Resolve
        resolved = await mgr.resolve("integration:test:error", "Fixed")
        assert resolved is True

        # 6. Check gone
        assert await mgr.is_active("integration:test:error") is False

        # Cleanup
        await mgr.resolve("integration:test:error")  # Idempotent


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
