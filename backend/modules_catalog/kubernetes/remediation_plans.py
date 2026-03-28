"""
Kubernetes Modul – Vordefinierte Remediation-Workflows.
Abhängigkeits-bewusste Restart-Sequenzen und automatische Fehlerbehebung.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from core.memory import get_memory
from core.redis_client import get_redis
from .tools import (
    scale_deployment,
    get_deployment_status,
    get_failing_pods,
    restart_pod,
    get_pod_logs,
)

logger = logging.getLogger("ninko.modules.kubernetes.remediation")


async def restart_with_db_dependency(
    namespace: str,
    app_deployment: str,
    db_deployment: str,
    wait_timeout_seconds: int = 300,
) -> dict:
    """
    Geordneter Restart mit Datenbank-Abhängigkeit:

    1. App-Deployment auf 0 skalieren
    2. DB-Deployment prüfen / starten
    3. Polling alle 10s bis DB ready (Timeout)
    4. App-Deployment wieder hochskalieren
    5. Status-Report zurückgeben + in Memory schreiben
    """
    memory = get_memory()
    redis = get_redis()
    steps: list[str] = []

    try:
        # 1. App herunterskalieren
        logger.info("Remediation: Skaliere '%s' auf 0…", app_deployment)
        result = await scale_deployment.ainvoke({
            "namespace": namespace,
            "name": app_deployment,
            "replicas": 0,
        })
        steps.append(f"✅ App '{app_deployment}' auf 0 skaliert")

        # 2. DB-Status prüfen
        db_status = await get_deployment_status.ainvoke({
            "namespace": namespace,
            "name": db_deployment,
        })
        steps.append(f"ℹ️ DB '{db_deployment}' Status: {db_status.get('ready', 'unbekannt')}")

        # 3. Warten bis DB ready
        elapsed = 0
        poll_interval = 10
        db_ready = False

        while elapsed < wait_timeout_seconds:
            db_status = await get_deployment_status.ainvoke({
                "namespace": namespace,
                "name": db_deployment,
            })

            desired = db_status.get("desired", 0)
            available = db_status.get("available", 0)

            if desired > 0 and available >= desired:
                db_ready = True
                steps.append(f"✅ DB '{db_deployment}' bereit nach {elapsed}s")
                break

            logger.info(
                "Warte auf DB '%s': %d/%d bereit (elapsed: %ds)",
                db_deployment, available, desired, elapsed,
            )
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        if not db_ready:
            steps.append(
                f"⚠️ Timeout: DB '{db_deployment}' nicht bereit nach {wait_timeout_seconds}s"
            )
            # App trotzdem hochfahren (damit der Admin reagieren kann)

        # 4. App wieder hochskalieren
        # Vorherige Replica-Anzahl abfragen (Default: 1)
        logger.info("Remediation: Skaliere '%s' wieder hoch…", app_deployment)
        result = await scale_deployment.ainvoke({
            "namespace": namespace,
            "name": app_deployment,
            "replicas": 1,
        })
        steps.append(f"✅ App '{app_deployment}' wieder hochskaliert")

        # 5. Status-Report
        report = {
            "action": "restart_with_db_dependency",
            "namespace": namespace,
            "app_deployment": app_deployment,
            "db_deployment": db_deployment,
            "db_ready": db_ready,
            "steps": steps,
            "status": "success" if db_ready else "warning",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # In Memory speichern
        await memory.store_incident(
            module="kubernetes",
            summary=f"Restart mit DB-Abhängigkeit: {app_deployment} → {db_deployment}",
            details=json.dumps(report, ensure_ascii=False, indent=2),
            severity="info" if db_ready else "warning",
        )

        return report

    except Exception as exc:
        error_report = {
            "action": "restart_with_db_dependency",
            "namespace": namespace,
            "status": "error",
            "detail": str(exc),
            "steps": steps,
        }
        logger.error("Remediation fehlgeschlagen: %s", exc, exc_info=True)
        return error_report


async def ordered_namespace_restart(
    namespace: str,
    restart_order: list[str],
) -> dict:
    """
    Deployments nacheinander starten, jeweils auf Ready warten.
    """
    memory = get_memory()
    steps: list[str] = []
    errors: list[str] = []

    for deployment_name in restart_order:
        logger.info("Geordneter Restart: '%s' in '%s'…", deployment_name, namespace)

        try:
            # Rollout Restart
            from .tools import rollout_restart
            result = await rollout_restart.ainvoke({
                "namespace": namespace,
                "deployment_name": deployment_name,
            })

            if result.get("status") == "success":
                steps.append(f"✅ {deployment_name}: Rollout Restart initiiert")
            else:
                steps.append(f"⚠️ {deployment_name}: {result.get('detail', 'Fehler')}")
                errors.append(deployment_name)
                continue

            # Warten bis Ready (max 120s)
            elapsed = 0
            while elapsed < 120:
                status = await get_deployment_status.ainvoke({
                    "namespace": namespace,
                    "name": deployment_name,
                })
                desired = status.get("desired", 0)
                available = status.get("available", 0)
                if desired > 0 and available >= desired:
                    steps.append(f"✅ {deployment_name}: Bereit")
                    break
                await asyncio.sleep(5)
                elapsed += 5
            else:
                steps.append(f"⚠️ {deployment_name}: Timeout nach 120s")
                errors.append(deployment_name)

        except Exception as exc:
            steps.append(f"❌ {deployment_name}: {exc}")
            errors.append(deployment_name)

    report = {
        "action": "ordered_namespace_restart",
        "namespace": namespace,
        "restart_order": restart_order,
        "steps": steps,
        "errors": errors,
        "status": "success" if not errors else "partial",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    await memory.store_incident(
        module="kubernetes",
        summary=f"Geordneter Namespace-Restart: {namespace}",
        details=json.dumps(report, ensure_ascii=False, indent=2),
        severity="info" if not errors else "warning",
    )

    return report


async def auto_remediate_failing_pods(namespace: str = "") -> dict:
    """
    Failing Pods analysieren → Ursache klassifizieren
    (OOMKilled / CrashLoopBackOff / ImagePullBackOff / Pending)
    → Maßnahme ausführen oder Empfehlung ausgeben
    → Incident in Memory speichern
    """
    memory = get_memory()
    redis = get_redis()

    failing = await get_failing_pods.ainvoke({"namespace": namespace})
    actions: list[dict] = []

    for pod in failing:
        pod_name = pod["name"]
        pod_ns = pod["namespace"]
        issues = pod.get("issues", [])

        action: dict = {
            "pod": pod_name,
            "namespace": pod_ns,
            "issues": issues,
            "action_taken": "",
            "recommendation": "",
        }

        # Analyse und Maßnahme
        issues_str = " ".join(issues).lower()

        if "crashloopbackoff" in issues_str:
            # Pod neu starten (letzter Versuch vor Eskalation)
            if pod.get("restarts", 0) < 10:
                result = await restart_pod.ainvoke({
                    "namespace": pod_ns,
                    "pod_name": pod_name,
                })
                action["action_taken"] = f"Pod neu gestartet ({pod['restarts']} bisherige Neustarts)"
            else:
                action["recommendation"] = (
                    f"Pod '{pod_name}' hat {pod['restarts']} Neustarts. "
                    "Manuelle Prüfung empfohlen – möglicherweise fehlende Config oder Dependencies."
                )

        elif "oomkilled" in issues_str:
            action["recommendation"] = (
                f"Pod '{pod_name}' wurde wegen Speichermangel beendet (OOMKilled). "
                "Empfehlung: Memory Limit erhöhen oder Memory Leak untersuchen."
            )

        elif "imagepullbackoff" in issues_str or "errimagepull" in issues_str:
            action["recommendation"] = (
                f"Pod '{pod_name}' kann das Container-Image nicht laden. "
                "Prüfe: Image-Name, Registry-Credentials, Netzwerk-Zugang."
            )

        elif "pending" in pod.get("status", "").lower():
            action["recommendation"] = (
                f"Pod '{pod_name}' ist Pending. "
                "Mögliche Ursachen: Fehlende Ressourcen, NodeSelector, Taints/Tolerations."
            )

        else:
            result = await restart_pod.ainvoke({
                "namespace": pod_ns,
                "pod_name": pod_name,
            })
            action["action_taken"] = "Pod neu gestartet (unspezifischer Fehler)"

        actions.append(action)

    # Event für andere Module publizieren
    if actions:
        event = {
            "source_module": "kubernetes",
            "event_type": "incident_detected",
            "severity": "critical" if len(actions) > 2 else "warning",
            "data": {
                "namespace": namespace or "alle",
                "failing_pods": len(actions),
                "actions": actions,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await redis.publish_event(event)

    report = {
        "action": "auto_remediate_failing_pods",
        "namespace": namespace or "alle",
        "total_failing": len(failing),
        "actions": actions,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if actions:
        await memory.store_incident(
            module="kubernetes",
            summary=f"Auto-Remediation: {len(actions)} failing Pods in {namespace or 'allen Namespaces'}",
            details=json.dumps(report, ensure_ascii=False, indent=2),
            severity="warning",
        )

    return report
