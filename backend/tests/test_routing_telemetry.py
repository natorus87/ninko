"""Tests für RoutingTelemetry (R12) – In-Memory-Mock statt echtem Redis."""
from __future__ import annotations

import json
from collections import defaultdict
from unittest.mock import MagicMock

import pytest

from core.routing_telemetry import RoutingTelemetry


# ── Redis-Mock ────────────────────────────────────────────────────────────────


class _FakeRedis:
    """Minimaler In-Memory-Redis-Ersatz für Telemetrie-Tests."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._lists: dict[str, list[str]] = defaultdict(list)
        self._hashes: dict[str, dict[str, int]] = defaultdict(dict)

    async def set(self, key: str, value: str, ex: int = 0) -> None:
        self._store[key] = value

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self._store.pop(key, None)
            self._lists.pop(key, None)
            self._hashes.pop(key, None)

    async def lpush(self, key: str, *values: str) -> None:
        for v in reversed(values):
            self._lists[key].insert(0, v)

    async def ltrim(self, key: str, start: int, stop: int) -> None:
        lst = self._lists[key]
        self._lists[key] = lst[start: stop + 1] if stop >= 0 else lst[start:]

    async def lrange(self, key: str, start: int, stop: int) -> list[str]:
        lst = self._lists[key]
        return lst[start: stop + 1] if stop >= 0 else lst[start:]

    async def hincrby(self, key: str, field: str, amount: int) -> int:
        self._hashes[key][field] = self._hashes[key].get(field, 0) + amount
        return self._hashes[key][field]

    async def hgetall(self, key: str) -> dict[str, str]:
        return {k: str(v) for k, v in self._hashes[key].items()}

    async def scan_iter(self, match: str = "*"):
        prefix = match.rstrip("*")
        for key in list(self._lists.keys()) + list(self._store.keys()):
            if key.startswith(prefix):
                yield key


def _make_telemetry() -> tuple[RoutingTelemetry, _FakeRedis]:
    fake_redis_conn = _FakeRedis()
    redis_client = MagicMock()
    redis_client.connection = fake_redis_conn
    return RoutingTelemetry(redis_client), fake_redis_conn


# ── record_auto_routing ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_record_auto_routing_stores_data() -> None:
    tel, fake = _make_telemetry()
    await tel.record_auto_routing("sess1", "docker", 2, 0.87, "Docker starten")
    raw = await fake.get("ninko:routing:last_auto:sess1")
    assert raw is not None
    data = json.loads(raw)
    assert data["module"] == "docker"
    assert data["tier"] == 2
    assert data["confidence"] == pytest.approx(0.87)


@pytest.mark.asyncio
async def test_record_auto_routing_truncates_message() -> None:
    tel, fake = _make_telemetry()
    long_msg = "x" * 300
    await tel.record_auto_routing("sess2", "docker", 2, 0.9, long_msg)
    raw = await fake.get("ninko:routing:last_auto:sess2")
    data = json.loads(raw)
    assert "msg" not in data  # Klartext nicht im Auto-Routing-State gespeichert


# ── check_and_record_correction ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_correction_detected_when_force_differs_from_auto() -> None:
    tel, fake = _make_telemetry()
    await tel.record_auto_routing("sess3", "docker", 2, 0.87, "VM starten")
    correction = await tel.check_and_record_correction("sess3", "proxmox", "VM starten")
    assert correction is not None
    assert correction["from"] == "docker"
    assert correction["to"] == "proxmox"


@pytest.mark.asyncio
async def test_no_correction_when_force_matches_auto() -> None:
    tel, _ = _make_telemetry()
    await tel.record_auto_routing("sess4", "docker", 2, 0.87, "Docker starten")
    correction = await tel.check_and_record_correction("sess4", "docker", "Docker starten")
    assert correction is None


@pytest.mark.asyncio
async def test_no_correction_without_prior_auto_routing() -> None:
    tel, _ = _make_telemetry()
    correction = await tel.check_and_record_correction("sess_new", "proxmox", "VM starten")
    assert correction is None


@pytest.mark.asyncio
async def test_no_correction_when_force_message_differs_from_auto_message() -> None:
    tel, _ = _make_telemetry()
    await tel.record_auto_routing("sess_msg", "docker", 2, 0.7, "Docker starten")
    correction = await tel.check_and_record_correction(
        "sess_msg",
        "proxmox",
        "VM starten",
    )
    assert correction is None


@pytest.mark.asyncio
async def test_force_module_consumes_last_auto_routing_state() -> None:
    tel, _ = _make_telemetry()
    await tel.record_auto_routing("sess_once", "docker", 2, 0.7, "Docker starten")

    first = await tel.check_and_record_correction("sess_once", "proxmox", "andere Anfrage")
    second = await tel.check_and_record_correction("sess_once", "proxmox", "Docker starten")

    assert first is None
    assert second is None


@pytest.mark.asyncio
async def test_correction_increments_stats() -> None:
    tel, fake = _make_telemetry()
    await tel.record_auto_routing("sess5", "docker", 2, 0.7, "VM starten")
    await tel.check_and_record_correction("sess5", "proxmox", "VM starten")
    stats = await fake.hgetall("ninko:routing:corrections:stats")
    assert stats.get("docker→proxmox") == "1"


@pytest.mark.asyncio
async def test_correction_stores_message_example() -> None:
    tel, fake = _make_telemetry()
    await tel.record_auto_routing("sess6", "docker", 2, 0.7, "VM starten")
    await tel.check_and_record_correction("sess6", "proxmox", "VM starten")
    msgs = await fake.lrange("ninko:routing:correction_msgs:proxmox", 0, -1)
    assert "VM starten" in msgs


@pytest.mark.asyncio
async def test_correction_appended_to_log() -> None:
    tel, fake = _make_telemetry()
    await tel.record_auto_routing("sess7", "docker", 2, 0.7, "VM starten")
    await tel.check_and_record_correction("sess7", "proxmox", "VM starten")
    log = await fake.lrange("ninko:routing:corrections:log", 0, -1)
    assert len(log) == 1
    entry = json.loads(log[0])
    assert entry["from"] == "docker"
    assert entry["to"] == "proxmox"


# ── get_stats ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_stats_returns_totals() -> None:
    tel, fake = _make_telemetry()
    for _ in range(3):
        await tel.record_auto_routing("sess8", "docker", 2, 0.7, "VM starten")
        await tel.check_and_record_correction("sess8", "proxmox", "VM starten")
    stats = await tel.get_stats()
    assert stats["total"] == 3
    assert stats["by_pair"]["docker→proxmox"] == 3


@pytest.mark.asyncio
async def test_get_stats_empty_returns_zero() -> None:
    tel, _ = _make_telemetry()
    stats = await tel.get_stats()
    assert stats["total"] == 0
    assert stats["by_pair"] == {}
    assert stats["recent"] == []


# ── reset_stats ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reset_clears_log_and_stats() -> None:
    tel, fake = _make_telemetry()
    await tel.record_auto_routing("sess9", "docker", 2, 0.7, "VM starten")
    await tel.check_and_record_correction("sess9", "proxmox", "VM starten")
    await tel.reset_stats()
    stats = await tel.get_stats()
    assert stats["total"] == 0
    log = await fake.lrange("ninko:routing:corrections:log", 0, -1)
    assert log == []


# ── get_correction_examples ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_correction_examples_returns_messages() -> None:
    tel, fake = _make_telemetry()
    await tel.record_auto_routing("s1", "docker", 2, 0.7, "VM erstellen")
    await tel.check_and_record_correction("s1", "proxmox", "VM erstellen")
    examples = await tel.get_correction_examples("proxmox")
    assert "VM erstellen" in examples
