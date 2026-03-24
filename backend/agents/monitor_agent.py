"""
Ninko Monitor Agent – Background-Monitoring aller aktiven Module.
Ruft zyklisch Health-Checks auf und sendet Alerts via WebSocket/Redis.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from core.config import get_settings
from core.redis_client import get_redis
from core.memory import get_memory

if TYPE_CHECKING:
    from core.module_registry import ModuleRegistry

logger = logging.getLogger("ninko.agents.monitor")


class MonitorAgent:
    """
    Periodischer Health-Check aller Module.
    Bei Fehlern: Alert via Redis PubSub → WebSocket → Dashboard.
    """

    def __init__(self, registry: ModuleRegistry) -> None:
        self.registry = registry
        self._settings = get_settings()
        self._redis = get_redis()
        self._memory = get_memory()
        self._running = False
        self._task: asyncio.Task | None = None

    async def start_loop(self) -> None:
        """Startet die Monitoring-Schleife als Background-Task."""
        self._running = True
        logger.info(
            "Monitor-Agent gestartet (Intervall: %ds, Auto-Remediation: %s)",
            self._settings.MONITOR_INTERVAL_SECONDS,
            self._settings.MONITOR_AUTO_REMEDIATE,
        )

        while self._running:
            try:
                await self.run_cycle()
            except Exception as exc:
                logger.error("Monitor-Cycle Fehler: %s", exc, exc_info=True)

            await asyncio.sleep(self._settings.MONITOR_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """Stoppt die Monitoring-Schleife."""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Monitor-Agent gestoppt.")

    async def run_cycle(self) -> dict:
        """
        Ein Monitoring-Zyklus:

        1. Iteriert über alle aktiven Module
        2. Ruft module.health_check() auf
        3. Bei Status "error": Alert via WebSocket + optional Auto-Remediation
        4. Schreibt Cycle-Ergebnis in Semantic Memory (Incident-Log)
        """
        logger.debug("Monitor-Cycle gestartet.")
        results: dict[str, dict] = {}
        alerts: list[dict] = []

        # Health-Checks aller Module
        health = await self.registry.get_health()

        for module_name, status in health.items():
            results[module_name] = status

            if status.get("status") == "error":
                alert = {
                    "type": "alert",
                    "module": module_name,
                    "severity": "critical",
                    "message": (
                        f"Modul '{module_name}' meldet Fehler: "
                        f"{status.get('detail', 'Unbekannt')}"
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                alerts.append(alert)

                # Alert via Redis PubSub (→ WebSocket → Dashboard)
                await self._redis.publish_event(alert)

                # Incident im Memory speichern
                await self._memory.store_incident(
                    module="monitor",
                    summary=f"Health-Check fehlgeschlagen: {module_name}",
                    details=json.dumps(status, default=str),
                    severity="critical",
                )

                logger.warning(
                    "ALERT: Modul '%s' – %s",
                    module_name,
                    status.get("detail", "Unbekannt"),
                )

                # Auto-Remediation (wenn aktiviert)
                if self._settings.MONITOR_AUTO_REMEDIATE:
                    await self._attempt_remediation(module_name, status)

        # Cycle-Zusammenfassung
        total = len(results)
        errors = len(alerts)
        ok = total - errors

        logger.info(
            "Monitor-Cycle abgeschlossen: %d Module geprüft, %d OK, %d Fehler",
            total,
            ok,
            errors,
        )

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_modules": total,
            "ok": ok,
            "errors": errors,
            "results": results,
            "alerts": alerts,
        }

    async def _attempt_remediation(
        self, module_name: str, status: dict
    ) -> None:
        """
        Versucht eine automatische Remediation.
        Aktuell: Loggt den Versuch und publisht ein Event.
        Module können auf das Event reagieren.
        """
        logger.info("Auto-Remediation für Modul '%s' wird versucht…", module_name)

        event = {
            "type": "remediation_requested",
            "source_module": "monitor",
            "target_module": module_name,
            "event_type": "auto_remediation",
            "severity": "critical",
            "data": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        await self._redis.publish_event(event)

        await self._memory.store_incident(
            module="monitor",
            summary=f"Auto-Remediation angefordert: {module_name}",
            details=json.dumps(event, default=str),
            severity="warning",
        )
