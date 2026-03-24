"""
Kubernetes Modul – LangGraph @tool-Funktionen.
Vollständige Implementierung mit kubernetes Python-Client.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta

from kubernetes import client, config
from langchain_core.tools import tool

logger = logging.getLogger("ninko.modules.kubernetes.tools")


async def _get_k8s_client(
    connection_id: str = "",
) -> tuple[client.CoreV1Api, client.AppsV1Api, client.NetworkingV1Api]:
    """Initialisiert den Kubernetes-Client via ConnectionManager."""
    from core.connections import ConnectionManager
    from core.vault import get_vault
    import base64
    import tempfile

    if connection_id:
        conn = await ConnectionManager.get_connection("kubernetes", connection_id)
        if not conn:
            raise ValueError(f"Kubernetes Verbindung mit ID '{connection_id}' nicht gefunden.")
    else:
        conn = await ConnectionManager.get_default_connection("kubernetes")
        # Fallback to local
        if not conn:
            try:
                if os.environ.get("K8S_IN_CLUSTER", "true").lower() == "true":
                    config.load_incluster_config()
                else:
                    kubeconfig = os.environ.get("K8S_KUBECONFIG_PATH", "")
                    config.load_kube_config(config_file=kubeconfig or None)
                return client.CoreV1Api(), client.AppsV1Api(), client.NetworkingV1Api()
            except config.ConfigException:
                config.load_kube_config()
                return client.CoreV1Api(), client.AppsV1Api(), client.NetworkingV1Api()

    # Get kubeconfig from Vault
    vault = get_vault()
    kubeconfig_key = conn.vault_keys.get("kubeconfig")
    
    if not kubeconfig_key:
        # Maybe local context indicated by environment
        if conn.environment == "local":
            config.load_kube_config()
            return client.CoreV1Api(), client.AppsV1Api(), client.NetworkingV1Api()
        raise ValueError(f"Keine Kubeconfig in Vault für '{conn.name}' hinterlegt.")

    kubeconfig_b64 = await vault.get_secret(kubeconfig_key)
    if not kubeconfig_b64:
        raise ValueError(f"Kubeconfig für '{conn.name}' nicht im Vault gefunden.")

    kubeconfig_bytes = base64.b64decode(kubeconfig_b64)
    kubeconfig_str = kubeconfig_bytes.decode("utf-8")
    
    import yaml
    try:
        config_dict = yaml.safe_load(kubeconfig_str)
        config.load_kube_config_from_dict(config_dict)
    except Exception as e:
        logger.error(f"Fehler beim Parsen der Kubeconfig: {e}")
        raise ValueError(f"Ungültige Kubeconfig für Verbindung '{conn.name}'. Bitte überprüfe die Datei.")

    return client.CoreV1Api(), client.AppsV1Api(), client.NetworkingV1Api()


def _pod_age(creation_timestamp) -> str:
    """Berechnet das Alter eines Pods als lesbaren String."""
    if not creation_timestamp:
        return "unbekannt"
    now = datetime.now(timezone.utc)
    delta = now - creation_timestamp.replace(tzinfo=timezone.utc) if creation_timestamp.tzinfo is None else now - creation_timestamp
    days = delta.days
    hours = delta.seconds // 3600
    if days > 0:
        return f"{days}d{hours}h"
    minutes = delta.seconds // 60
    if hours > 0:
        return f"{hours}h{minutes % 60}m"
    return f"{minutes}m"


@tool
async def get_cluster_status(connection_id: str = "") -> dict:
    """Gibt den Gesamtstatus des Kubernetes-Clusters zurück: Nodes, Pods, Deployments."""
    v1, apps_v1, _ = await _get_k8s_client(connection_id)

    nodes = v1.list_node()
    namespaces = v1.list_namespace()
    pods = v1.list_pod_for_all_namespaces()
    deployments = apps_v1.list_deployment_for_all_namespaces()

    running = sum(1 for p in pods.items if p.status.phase == "Running")
    failing = sum(
        1 for p in pods.items
        if p.status.phase in ("Failed", "Unknown")
        or any(
            cs.state and cs.state.waiting and cs.state.waiting.reason in ("CrashLoopBackOff", "ErrImagePull", "ImagePullBackOff")
            for cs in (p.status.container_statuses or [])
        )
    )

    return {
        "nodes": len(nodes.items),
        "namespaces": len(namespaces.items),
        "total_pods": len(pods.items),
        "running_pods": running,
        "failing_pods": failing,
        "deployments": len(deployments.items),
    }


@tool
async def list_namespaces(connection_id: str = "") -> list[dict]:
    """Listet alle Kubernetes-Namespaces auf."""
    v1, _, _ = await _get_k8s_client(connection_id)
    ns_list = v1.list_namespace()

    return [
        {
            "name": ns.metadata.name,
            "status": ns.status.phase,
            "labels": dict(ns.metadata.labels or {}),
        }
        for ns in ns_list.items
    ]


@tool
async def get_all_pods(namespace: str = "default", connection_id: str = "") -> list[dict]:
    """Listet alle Pods in einem Namespace auf."""
    v1, _, _ = await _get_k8s_client(connection_id)
    pods = v1.list_namespaced_pod(namespace=namespace)

    result = []
    for p in pods.items:
        containers = p.status.container_statuses or []
        ready_count = sum(1 for c in containers if c.ready)
        total_count = len(containers)
        restarts = sum(c.restart_count for c in containers)

        result.append({
            "name": p.metadata.name,
            "namespace": p.metadata.namespace,
            "status": p.status.phase,
            "ready": f"{ready_count}/{total_count}",
            "restarts": restarts,
            "age": _pod_age(p.metadata.creation_timestamp),
            "node": p.spec.node_name or "",
            "ip": p.status.pod_ip or "",
        })

    return result


@tool
async def get_failing_pods(namespace: str = "", connection_id: str = "") -> list[dict]:
    """Findet alle fehlerhaften Pods (CrashLoop, ImagePull, OOMKilled, etc.)."""
    v1, _, _ = await _get_k8s_client(connection_id)

    if namespace:
        pods = v1.list_namespaced_pod(namespace=namespace)
    else:
        pods = v1.list_pod_for_all_namespaces()

    failing = []
    for p in pods.items:
        issues: list[str] = []

        if p.status.phase in ("Failed", "Unknown"):
            issues.append(f"Phase: {p.status.phase}")

        for cs in (p.status.container_statuses or []):
            if cs.state and cs.state.waiting:
                reason = cs.state.waiting.reason or "Unknown"
                if reason in ("CrashLoopBackOff", "ErrImagePull", "ImagePullBackOff", "CreateContainerConfigError"):
                    issues.append(f"{cs.name}: {reason}")
            if cs.state and cs.state.terminated:
                reason = cs.state.terminated.reason or "Unknown"
                if reason in ("OOMKilled", "Error"):
                    issues.append(f"{cs.name}: {reason}")
            if cs.restart_count > 5:
                issues.append(f"{cs.name}: {cs.restart_count} Neustarts")

        if issues:
            containers = p.status.container_statuses or []
            ready_count = sum(1 for c in containers if c.ready)
            failing.append({
                "name": p.metadata.name,
                "namespace": p.metadata.namespace,
                "status": p.status.phase,
                "ready": f"{ready_count}/{len(containers)}",
                "restarts": sum(c.restart_count for c in containers),
                "issues": issues,
                "age": _pod_age(p.metadata.creation_timestamp),
            })

    return failing


@tool
async def restart_pod(namespace: str, pod_name: str, connection_id: str = "") -> dict:
    """Startet einen einzelnen Pod neu (löscht ihn – Controller erstellt neuen)."""
    v1, _, _ = await _get_k8s_client(connection_id)

    try:
        v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
        return {
            "action": "restart_pod",
            "target": pod_name,
            "namespace": namespace,
            "status": "success",
            "detail": f"Pod '{pod_name}' im Namespace '{namespace}' wird neu gestartet.",
        }
    except client.ApiException as e:
        return {
            "action": "restart_pod",
            "target": pod_name,
            "namespace": namespace,
            "status": "error",
            "detail": f"Fehler: {e.reason} ({e.status})",
        }


@tool
async def get_pod_logs(namespace: str, pod_name: str, lines: int = 100, connection_id: str = "") -> dict:
    """Gibt die letzten Logzeilen eines Pods zurück."""
    v1, _, _ = await _get_k8s_client(connection_id)

    try:
        logs = v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            tail_lines=lines,
        )
        return {
            "pod": pod_name,
            "namespace": namespace,
            "lines": lines,
            "logs": logs,
        }
    except client.ApiException as e:
        return {
            "pod": pod_name,
            "namespace": namespace,
            "error": f"{e.reason} ({e.status})",
        }


@tool
async def scale_deployment(namespace: str, name: str, replicas: int, connection_id: str = "") -> dict:
    """Skaliert ein Deployment auf die angegebene Anzahl Replicas."""
    _, apps_v1, _ = await _get_k8s_client(connection_id)

    try:
        body = {"spec": {"replicas": replicas}}
        apps_v1.patch_namespaced_deployment_scale(
            name=name, namespace=namespace, body=body
        )
        return {
            "action": "scale",
            "target": name,
            "namespace": namespace,
            "status": "success",
            "detail": f"Deployment '{name}' auf {replicas} Replicas skaliert.",
        }
    except client.ApiException as e:
        return {
            "action": "scale",
            "target": name,
            "namespace": namespace,
            "status": "error",
            "detail": f"Fehler: {e.reason} ({e.status})",
        }


@tool
async def rollout_restart(namespace: str, deployment_name: str, connection_id: str = "") -> dict:
    """Führt einen Rollout-Restart eines Deployments durch."""
    _, apps_v1, _ = await _get_k8s_client(connection_id)

    try:
        # Rollout Restart = Annotation aktualisieren
        now = datetime.now(timezone.utc).isoformat()
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": now
                        }
                    }
                }
            }
        }
        apps_v1.patch_namespaced_deployment(
            name=deployment_name, namespace=namespace, body=body
        )
        return {
            "action": "rollout_restart",
            "target": deployment_name,
            "namespace": namespace,
            "status": "success",
            "detail": f"Rollout-Restart für '{deployment_name}' initiiert.",
        }
    except client.ApiException as e:
        return {
            "action": "rollout_restart",
            "target": deployment_name,
            "namespace": namespace,
            "status": "error",
            "detail": f"Fehler: {e.reason} ({e.status})",
        }


@tool
async def get_deployment_status(namespace: str, name: str, connection_id: str = "") -> dict:
    """Gibt den detaillierten Status eines Deployments zurück."""
    _, apps_v1, _ = await _get_k8s_client(connection_id)

    try:
        dep = apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
        return {
            "name": dep.metadata.name,
            "namespace": dep.metadata.namespace,
            "ready": f"{dep.status.ready_replicas or 0}/{dep.spec.replicas}",
            "available": dep.status.available_replicas or 0,
            "desired": dep.spec.replicas,
            "updated": dep.status.updated_replicas or 0,
            "age": _pod_age(dep.metadata.creation_timestamp),
            "strategy": dep.spec.strategy.type if dep.spec.strategy else "unknown",
            "image": dep.spec.template.spec.containers[0].image if dep.spec.template.spec.containers else "unknown",
        }
    except client.ApiException as e:
        return {"error": f"{e.reason} ({e.status})"}


@tool
async def get_recent_events(namespace: str = "default", last_minutes: int = 30, connection_id: str = "") -> list[dict]:
    """Gibt die letzten Kubernetes-Events eines Namespaces zurück."""
    v1, _, _ = await _get_k8s_client(connection_id)

    events = v1.list_namespaced_event(namespace=namespace)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=last_minutes)

    recent = []
    for e in events.items:
        event_time = e.last_timestamp or e.event_time or e.metadata.creation_timestamp
        if event_time and event_time.replace(tzinfo=timezone.utc) >= cutoff:
            recent.append({
                "type": e.type,
                "reason": e.reason,
                "message": e.message,
                "source": e.source.component if e.source else "",
                "object": f"{e.involved_object.kind}/{e.involved_object.name}" if e.involved_object else "",
                "timestamp": event_time.isoformat() if event_time else "",
            })

    return sorted(recent, key=lambda x: x["timestamp"], reverse=True)


@tool
async def list_services(namespace: str = "default", connection_id: str = "") -> list[dict]:
    """Listet alle Services in einem Namespace auf."""
    v1, _, _ = await _get_k8s_client(connection_id)

    services = v1.list_namespaced_service(namespace=namespace)
    return [
        {
            "name": svc.metadata.name,
            "namespace": svc.metadata.namespace,
            "type": svc.spec.type,
            "cluster_ip": svc.spec.cluster_ip or "",
            "ports": [
                f"{p.port}/{p.protocol}" + (f"→{p.target_port}" if p.target_port else "")
                for p in (svc.spec.ports or [])
            ],
        }
        for svc in services.items
    ]


@tool
async def list_ingresses(namespace: str = "default", connection_id: str = "") -> list[dict]:
    """Listet alle Ingresses in einem Namespace auf."""
    _, _, net_v1 = await _get_k8s_client(connection_id)

    ingresses = net_v1.list_namespaced_ingress(namespace=namespace)
    return [
        {
            "name": ing.metadata.name,
            "namespace": ing.metadata.namespace,
            "hosts": [
                rule.host for rule in (ing.spec.rules or []) if rule.host
            ],
            "class_name": ing.spec.ingress_class_name or "",
        }
        for ing in ingresses.items
    ]


@tool
async def list_pvcs(namespace: str = "default", connection_id: str = "") -> list[dict]:
    """Listet alle PersistentVolumeClaims in einem Namespace auf."""
    v1, _, _ = await _get_k8s_client(connection_id)

    pvcs = v1.list_namespaced_persistent_volume_claim(namespace=namespace)
    return [
        {
            "name": pvc.metadata.name,
            "namespace": pvc.metadata.namespace,
            "status": pvc.status.phase,
            "capacity": (
                pvc.status.capacity.get("storage", "")
                if pvc.status.capacity
                else ""
            ),
            "storage_class": pvc.spec.storage_class_name or "",
        }
        for pvc in pvcs.items
    ]
