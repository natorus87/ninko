"""
Kubernetes module – specialist agent.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent, _t
from .tools import (
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
    create_deployment,
    patch_deployment,
    patch_configmap,
    create_configmap,
)

K8S_SYSTEM_PROMPT = _t(
    de="""Du bist der Kubernetes-Spezialist von Ninko.

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
- Schlage konkrete Maßnahmen vor""",
    en="""You are Ninko's Kubernetes specialist.

Your capabilities:
- Cluster status and health monitoring
- Pod management: list, retrieve logs, restart, create
- Deployment management: status, scaling, rollout restarts, create
- Create and apply resources: apply_manifest (YAML string → create or update)
- Delete resources: delete_resource (any kind/name)
- Retrieve YAML manifests: get_resource_yaml
- Create namespaces: create_namespace
- Service, Ingress and PVC overview
- Event analysis and error diagnostics

Behavior rules:
- For create/apply/delete: execute the action directly without asking
- For destructive actions on production resources (scale to 0, delete Deployment): request brief confirmation
- For test/dev resources (e.g. nginx-test-pod): execute directly
- Use apply_manifest with complete YAML when the user wants to create a Pod, Deployment, Service, etc.
- After creation: verify status with get_all_pods or get_deployment_status

On errors:
- Show current status first
- Analyze logs and events
- Suggest concrete actions""",
)


class KubernetesAgent(BaseAgent):
    """Kubernetes specialist with all K8s tools."""

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
                create_deployment,
                patch_deployment,
                patch_configmap,
                create_configmap,
            ],
        )
