"""
Kubernetes Modul – Spezialist-Agent.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent
from modules.kubernetes.tools import (
    get_cluster_status,
    list_namespaces,
    get_all_pods,
    get_failing_pods,
    restart_pod,
    get_pod_logs,
    scale_deployment,
    rollout_restart,
    get_deployment_status,
    get_recent_events,
    list_services,
    list_ingresses,
    list_pvcs,
)

K8S_SYSTEM_PROMPT = """Du bist der Kubernetes-Spezialist von Kumio.

Deine Fähigkeiten:
- Cluster-Status und Health-Monitoring
- Pod-Management: Auflisten, Logs abrufen, Neustarts
- Deployment-Management: Status, Skalierung, Rollout-Restarts
- Service-, Ingress- und PVC-Übersicht
- Event-Analyse und Fehlerdiagnose
- Automatisierte Remediation bei erkannten Problemen

Verhaltensregeln:
- Sei präzise und sicherheitsbewusst
- Bei destruktiven Aktionen (Neustart, Skalierung auf 0): kurze Bestätigung einholen
- Dokumentiere jeden Eingriff als Incident
- Analysiere Fehler gründlich bevor du Maßnahmen vorschlägst
- Verwende Fachbegriffe, aber erkläre wenn nötig

Bei Fehlern:
- Zeige zuerst den aktuellen Status
- Analysiere Logs und Events
- Schlage konkrete Maßnahmen vor
- Führe Maßnahmen erst nach Bestätigung aus (außer bei Auto-Remediation)"""


class KubernetesAgent(BaseAgent):
    """Kubernetes-Spezialist mit allen K8s-Tools."""

    def __init__(self) -> None:
        super().__init__(
            name="kubernetes",
            system_prompt=K8S_SYSTEM_PROMPT,
            tools=[
                get_cluster_status,
                list_namespaces,
                get_all_pods,
                get_failing_pods,
                restart_pod,
                get_pod_logs,
                scale_deployment,
                rollout_restart,
                get_deployment_status,
                get_recent_events,
                list_services,
                list_ingresses,
                list_pvcs,
            ],
        )
