"""
Ninko – Auto-Sync zwischen Workflow-Cron-Triggern und Scheduler-Tasks.

Ein Trigger-Node mit config {"mode": "cron", "cron": "..."} erzeugt beim
Speichern des Workflows automatisch einen Scheduler-Task (source =
'workflow_trigger'). Ändert oder entfernt der User den Trigger, wird der
Task aktualisiert bzw. gelöscht.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("ninko.workflow_cron_sync")

WORKFLOW_TRIGGER_SOURCE = "workflow_trigger"


def _public_workflow_id(workflow_id: str) -> str:
    return workflow_id.split("::", 1)[1] if "::" in workflow_id else workflow_id


def _find_cron_trigger(workflow: dict) -> str | None:
    """Gibt den Cron-Ausdruck des ersten Cron-Trigger-Nodes zurück (oder None)."""
    for node in workflow.get("nodes", []):
        if node.get("type") != "trigger":
            continue
        config = node.get("config") or {}
        if str(config.get("mode", "manual")) != "cron":
            continue
        cron_expr = str(config.get("cron", "")).strip()
        if cron_expr:
            return cron_expr
    return None


def _matching_tasks(tasks: list[dict], public_wf_id: str, tenant_id: str) -> list[dict]:
    tenant = (tenant_id or "default").strip().lower() or "default"
    return [
        t
        for t in tasks
        if t.get("source") == WORKFLOW_TRIGGER_SOURCE
        and t.get("workflow_id") == public_wf_id
        and ((t.get("tenant_id") or "default").strip().lower() or "default") == tenant
    ]


async def sync_workflow_cron_trigger(workflow: dict, tenant_id: str) -> str | None:
    """Synchronisiert den Scheduler-Task zu einem Workflow-Cron-Trigger.

    Gibt den aktiven Cron-Ausdruck zurück, wenn ein Task angelegt/aktualisiert
    wurde, sonst None. Fehler werden geloggt, nie geworfen — der Workflow-Save
    darf daran nicht scheitern.
    """
    from agents.scheduler_agent import get_scheduler_agent

    scheduler = get_scheduler_agent()
    if scheduler is None:
        logger.warning("Scheduler nicht verfügbar — Cron-Trigger-Sync übersprungen.")
        return None

    public_wf_id = _public_workflow_id(str(workflow.get("id", "")))
    cron_expr = _find_cron_trigger(workflow)
    workflow_enabled = bool(workflow.get("enabled", True))

    try:
        tasks = await scheduler.get_all_tasks()
        existing = _matching_tasks(tasks, public_wf_id, tenant_id)

        if not cron_expr or not workflow_enabled:
            for task in existing:
                await scheduler.delete_task(task["id"])
                logger.info(
                    "Workflow-Trigger-Task entfernt: %s (Workflow %s)",
                    task["id"],
                    public_wf_id,
                )
            return None

        task_name = f"Workflow-Trigger: {workflow.get('name', public_wf_id)}"
        if existing:
            primary = existing[0]
            await scheduler.update_task(
                primary["id"],
                {"name": task_name, "cron": cron_expr, "enabled": True},
            )
            # Dubletten (sollten nicht vorkommen) aufräumen
            for duplicate in existing[1:]:
                await scheduler.delete_task(duplicate["id"])
        else:
            await scheduler.create_task(
                {
                    "name": task_name,
                    "cron": cron_expr,
                    "workflow_id": public_wf_id,
                    "tenant_id": tenant_id,
                    "source": WORKFLOW_TRIGGER_SOURCE,
                }
            )
        logger.info(
            "Workflow-Cron-Trigger synchronisiert: %s → '%s'", public_wf_id, cron_expr
        )
        return cron_expr

    except Exception as exc:
        logger.warning("Cron-Trigger-Sync für Workflow '%s' fehlgeschlagen: %s", public_wf_id, exc)
        return None


async def remove_workflow_cron_trigger(tenant_id: str, public_workflow_id: str) -> None:
    """Entfernt alle auto-synchronisierten Tasks eines gelöschten Workflows."""
    from agents.scheduler_agent import get_scheduler_agent

    scheduler = get_scheduler_agent()
    if scheduler is None:
        return

    try:
        tasks = await scheduler.get_all_tasks()
        for task in _matching_tasks(tasks, public_workflow_id, tenant_id):
            await scheduler.delete_task(task["id"])
            logger.info(
                "Workflow-Trigger-Task entfernt: %s (Workflow %s gelöscht)",
                task["id"],
                public_workflow_id,
            )
    except Exception as exc:
        logger.warning(
            "Cron-Trigger-Cleanup für Workflow '%s' fehlgeschlagen: %s",
            public_workflow_id,
            exc,
        )
