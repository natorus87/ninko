"""
Alert State Tools – LLM-erreichbare Tools für Alert-Management.

Diese Tools ermöglichen es dem Orchestrator und Workflows, Alerts zu prüfen,
aufzuzeichnen und zu resolven. Sie bauen auf dem AlertStateManager auf.
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from core.alert_state import get_alert_manager

logger = logging.getLogger("ninko.tools.alerts")


@tool
async def check_alert_state(alert_id: str) -> str:
    """
    Prüft den Status eines Alerts anhand seiner ID.

    Gibt zurück ob der Alert aktiv ist, wann er zuerst gesehen wurde,
    wann zuletzt benachrichtigt wurde, und wie oft bereits benachrichtigt wurde.

    Parameter:
        alert_id: Die Alert-ID, z.B. 'kubernetes:nginx-pod:crashloopbackoff'

    Returns:
        JSON-String mit Alert-Status Informationen

    Beispiel:
        check_alert_state("kubernetes:nginx-pod:crashloopbackoff")
    """
    try:
        mgr = get_alert_manager()
        state = await mgr.get_state(alert_id)

        if state:
            return json.dumps(
                {
                    "exists": True,
                    "alert_id": alert_id,
                    "status": state.get("status"),
                    "severity": state.get("severity"),
                    "module": state.get("module"),
                    "first_seen": state.get("first_seen"),
                    "last_seen": state.get("last_seen"),
                    "last_notified": state.get("last_notified"),
                    "notify_count": state.get("notify_count", 0),
                    "ticket_id": state.get("ticket_id", ""),
                },
                indent=2,
            )
        else:
            return json.dumps(
                {
                    "exists": False,
                    "alert_id": alert_id,
                    "message": "Alert nicht aktiv (entweder neu oder bereits resolved)",
                },
                indent=2,
            )

    except Exception as exc:
        logger.error("Fehler bei check_alert_state: %s", exc)
        return json.dumps(
            {"error": f"Fehler beim Prüfen des Alert-Status: {exc}"},
            indent=2,
        )


@tool
async def record_alert(
    alert_id: str,
    module: str,
    severity: str,
    summary: str,
    ticket_id: str = "",
    check_cooldown: bool = True,
    cooldown_hours: int = 24,
) -> str:
    """
    Zeichnet einen neuen Alert auf oder aktualisiert einen bestehenden.

    Dieses Tool prüft automatisch ob eine Notification erlaubt ist (Cooldown-Logik).
    Es erstellt oder aktualisiert den Alert und gibt zurück ob eine Benachrichtigung
    gesendet werden sollte.

    Parameter:
        alert_id: Eindeutige Alert-ID (z.B. 'kubernetes:nginx-pod:crashloopbackoff')
        module: Modul-Name (z.B. 'kubernetes', 'proxmox')
        severity: Severity-Level ('critical', 'warning', 'info')
        summary: Kurze Beschreibung des Problems
        ticket_id: Optionale Ticket-Referenz (z.B. 'GLPI-12345')
        check_cooldown: Ob Cooldown geprüft werden soll (default: True)
        cooldown_hours: Cooldown-Zeit in Stunden (default: 24)

    Returns:
        JSON-String mit Alert-Status und should_notify Flag

    Beispiel:
        record_alert(
            alert_id="kubernetes:nginx-pod:crashloopbackoff",
            module="kubernetes",
            severity="critical",
            summary="Pod nginx-pod ist im CrashLoopBackOff",
            ticket_id="GLPI-12345"
        )
    """
    try:
        mgr = get_alert_manager()

        should_notify = True
        if check_cooldown:
            should_notify = await mgr.should_notify(
                alert_id, cooldown_seconds=cooldown_hours * 3600
            )

        state = await mgr.record(
            alert_id=alert_id,
            module=module,
            severity=severity,
            summary=summary,
            ticket_id=ticket_id,
        )

        if should_notify and ticket_id:
            await mgr.record_notification(alert_id, ticket_id)
        elif should_notify and check_cooldown and not ticket_id:
            # should_notify hat den Cooldown-Slot atomar reserviert, aber es erfolgt
            # keine ticketbasierte Notification → Slot freigeben, damit ein echter
            # Folge-Alert im Fenster nicht fälschlich unterdrückt wird.
            await mgr.release_notify_cooldown(alert_id)

        is_new = state.get("is_new", False)

        if is_new:
            message = f"Neuer Alert aufgezeichnet: {alert_id}"
        else:
            message = f"Bestehender Alert aktualisiert: {alert_id}"

        return json.dumps(
            {
                "success": True,
                "alert_id": alert_id,
                "is_new": is_new,
                "should_notify": should_notify,
                "notify_count": state.get("notify_count", 1),
                "cooldown_hours": cooldown_hours if check_cooldown else 0,
                "message": message,
            },
            indent=2,
        )

    except Exception as exc:
        logger.error("Fehler bei record_alert: %s", exc)
        return json.dumps(
            {"error": f"Fehler beim Aufzeichnen des Alerts: {exc}"},
            indent=2,
        )


@tool
async def resolve_alert(alert_id: str, resolution: str = "") -> str:
    """
    Markiert einen Alert als gelöst.

    Der Alert wird aus den aktiven Alerts entfernt und in die Historie verschoben.
    Dies ist idempotent - es gibt keinen Fehler wenn der Alert nicht existiert.

    Parameter:
        alert_id: Die Alert-ID die resolved werden soll
        resolution: Optionale Beschreibung der Lösung

    Returns:
        JSON-String mit Erfolgsstatus

    Beispiel:
        resolve_alert(
            alert_id="kubernetes:nginx-pod:crashloopbackoff",
            resolution="Pod wurde erfolgreich neu gestartet"
        )
    """
    try:
        mgr = get_alert_manager()
        resolved = await mgr.resolve(alert_id, resolution=resolution)

        if resolved:
            return json.dumps(
                {
                    "success": True,
                    "alert_id": alert_id,
                    "resolved": True,
                    "message": f"Alert {alert_id} wurde als gelöst markiert",
                },
                indent=2,
            )
        else:
            return json.dumps(
                {
                    "success": True,
                    "alert_id": alert_id,
                    "resolved": False,
                    "was_active": False,
                    "message": (
                        f"Alert {alert_id} war nicht aktiv "
                        "(bereits resolved oder nie existiert)"
                    ),
                },
                indent=2,
            )

    except Exception as exc:
        logger.error("Fehler bei resolve_alert: %s", exc)
        return json.dumps(
            {"error": f"Fehler beim Resolven des Alerts: {exc}"},
            indent=2,
        )
