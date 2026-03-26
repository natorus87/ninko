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
    list_deployments,
    apply_manifest,
    delete_resource,
    get_resource_yaml,
    create_namespace,
)

K8S_SYSTEM_PROMPT = """Du bist der Kubernetes-Spezialist von Ninko.

Deine Fähigkeiten:
- Cluster-Status und Health-Monitoring
- Pod-Management: Auflisten, Logs abrufen, Neustarts, Erstellen
- Deployment-Management: Status, Skalierung, Rollout-Restarts, Erstellen
- Ressourcen erstellen und anwenden: apply_manifest (YAML-String → create or update)
- Ressourcen löschen: delete_resource (beliebiger Kind/Name)
- YAML-Manifeste abrufen: get_resource_yaml
- Namespace erstellen: create_namespace
- Service-, Ingress- und PVC-Übersicht
- Event-Analyse und Fehlerdiagnose

Verhaltensregeln:
- Bei create/apply/delete: führe die Aktion direkt aus, ohne zu fragen
- Bei destruktiven Aktionen auf Produktions-Ressourcen (scale to 0, delete Deployment): kurze Bestätigung einholen
- Für test/dev Ressourcen (z.B. nginx-test-pod): direkt ausführen
- Verwende apply_manifest mit vollständigem YAML wenn der User einen Pod, Deployment, Service o.ä. erstellen möchte
- Nach dem Erstellen: Status mit get_all_pods oder get_deployment_status prüfen

Bei Fehlern:
- Zeige zuerst den aktuellen Status
- Analysiere Logs und Events
- Schlage konkrete Maßnahmen vor"""


class KubernetesAgent(BaseAgent):
    """Kubernetes-Spezialist mit allen K8s-Tools."""

    def __init__(self) -> None:
        super().__init__(
            name="kubernetes",
            system_prompt=K8S_SYSTEM_PROMPT,
            tools=[
                get_cluster_status,
                list_namespaces,
                list_deployments,
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
                apply_manifest,
                delete_resource,
                get_resource_yaml,
                create_namespace,
            ],
        )
