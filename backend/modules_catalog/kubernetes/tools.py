"""
Kubernetes module — LangGraph @tool functions.
Full implementation using the kubernetes Python client.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta

import yaml as _yaml
from kubernetes import client, config, dynamic
from kubernetes.client import api_client as _api_client
from kubernetes.utils import create_from_dict
from langchain_core.tools import tool

logger = logging.getLogger("ninko.modules.kubernetes.tools")

TOOL_REGISTRY_DEFAULTS = {
    "required_bins": ("kubectl",),
    "required_envs": (),
}


async def _get_k8s_client(
    connection_id: str = "",
) -> tuple[client.CoreV1Api, client.AppsV1Api, client.NetworkingV1Api]:
    """Initialize the Kubernetes client via ConnectionManager."""
    from core.connections import ConnectionManager
    from core.vault import get_vault
    import base64
    import tempfile

    if connection_id:
        conn = await ConnectionManager.get_connection("kubernetes", connection_id)
        if not conn:
            raise ValueError(
                f"Kubernetes connection with ID '{connection_id}' not found."
            )
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
        raise ValueError(f"No kubeconfig in Vault for '{conn.name}' configured.")

    kubeconfig_b64 = await vault.get_secret(kubeconfig_key)
    if not kubeconfig_b64:
        raise ValueError(f"Kubeconfig for '{conn.name}' not found in Vault.")

    kubeconfig_bytes = base64.b64decode(kubeconfig_b64)
    kubeconfig_str = kubeconfig_bytes.decode("utf-8")

    import yaml

    try:
        config_dict = yaml.safe_load(kubeconfig_str)
        config.load_kube_config_from_dict(config_dict)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.error("Failed to parse kubeconfig: %s", e)
        raise ValueError(
            f"Invalid kubeconfig for connection '{conn.name}'. Please check the file."
        )

    return client.CoreV1Api(), client.AppsV1Api(), client.NetworkingV1Api()


async def _get_dynamic_client(connection_id: str = "") -> dynamic.DynamicClient:
    """Returns a DynamicClient for apply/delete of any resource kind."""
    # Re-use _get_k8s_client to trigger config loading
    await _get_k8s_client(connection_id)
    return dynamic.DynamicClient(_api_client.ApiClient())


def _pod_age(creation_timestamp) -> str:
    """Calculate the age of a pod as a readable string."""
    if not creation_timestamp:
        return "unknown"
    now = datetime.now(timezone.utc)
    delta = (
        now - creation_timestamp.replace(tzinfo=timezone.utc)
        if creation_timestamp.tzinfo is None
        else now - creation_timestamp
    )
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
    """Returns the overall status of the Kubernetes cluster: nodes, pods, deployments."""
    v1, apps_v1, _ = await _get_k8s_client(connection_id)

    nodes = v1.list_node()
    namespaces = v1.list_namespace()
    pods = v1.list_pod_for_all_namespaces()
    deployments = apps_v1.list_deployment_for_all_namespaces()

    running = sum(1 for p in pods.items if p.status.phase == "Running")
    failing = sum(
        1
        for p in pods.items
        if p.status.phase in ("Failed", "Unknown")
        or any(
            cs.state
            and cs.state.waiting
            and cs.state.waiting.reason
            in ("CrashLoopBackOff", "ErrImagePull", "ImagePullBackOff")
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
    """Lists all Kubernetes namespaces."""
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
async def get_all_pods(
    namespace: str = "default", connection_id: str = ""
) -> list[dict]:
    """Lists all pods in a namespace."""
    v1, _, _ = await _get_k8s_client(connection_id)
    pods = v1.list_namespaced_pod(namespace=namespace)

    result = []
    for p in pods.items:
        containers = p.status.container_statuses or []
        ready_count = sum(1 for c in containers if c.ready)
        total_count = len(containers)
        restarts = sum(c.restart_count for c in containers)

        result.append(
            {
                "name": p.metadata.name,
                "namespace": p.metadata.namespace,
                "status": p.status.phase,
                "ready": f"{ready_count}/{total_count}",
                "restarts": restarts,
                "age": _pod_age(p.metadata.creation_timestamp),
                "node": p.spec.node_name or "",
                "ip": p.status.pod_ip or "",
            }
        )

    return result


@tool
@tool
async def get_failing_pods(namespace: str = "", connection_id: str = "") -> list[dict]:
    """Finds all failing pods (CrashLoop, ImagePull, OOMKilled, Failed phase, Unknown phase)."""
    v1, _, _ = await _get_k8s_client(connection_id)

    if namespace:
        pods = v1.list_namespaced_pod(namespace=namespace)
    else:
        pods = v1.list_pod_for_all_namespaces()

    failing = []
    for p in pods.items:
        issues: list[str] = []
        is_failing = False

        if p.status.phase in ("Failed", "Unknown"):
            issues.append(f"Phase: {p.status.phase}")
            is_failing = True

        for cs in p.status.container_statuses or []:
            if cs.state and cs.state.waiting:
                reason = cs.state.waiting.reason or "Unknown"
                if reason in (
                    "CrashLoopBackOff",
                    "ErrImagePull",
                    "ImagePullBackOff",
                    "CreateContainerConfigError",
                ):
                    issues.append(f"{cs.name}: {reason}")
                    is_failing = True
            if cs.state and cs.state.terminated:
                reason = cs.state.terminated.reason or "Unknown"
                if reason in ("OOMKilled", "Error"):
                    issues.append(f"{cs.name}: {reason}")
                    is_failing = True

        if is_failing:
            containers = p.status.container_statuses or []
            ready_count = sum(1 for c in containers if c.ready)
            restart_count = sum(c.restart_count for c in containers)
            failing.append(
                {
                    "name": p.metadata.name,
                    "namespace": p.metadata.namespace,
                    "status": p.status.phase,
                    "ready": f"{ready_count}/{len(containers)}",
                    "restarts": restart_count,
                    "issues": issues,
                    "age": _pod_age(p.metadata.creation_timestamp),
                }
            )

    return failing


@tool
async def restart_pod(namespace: str, pod_name: str, connection_id: str = "") -> dict:
    """Restarts a single pod (deletes it — controller creates a new one)."""
    v1, _, _ = await _get_k8s_client(connection_id)

    try:
        v1.delete_namespaced_pod(name=pod_name, namespace=namespace)
        return {
            "action": "restart_pod",
            "target": pod_name,
            "namespace": namespace,
            "status": "success",
            "detail": f"Pod '{pod_name}' in namespace '{namespace}' is being restarted.",
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
async def get_pod_logs(
    namespace: str, pod_name: str, lines: int = 100, connection_id: str = ""
) -> dict:
    """Returns the last log lines of a pod."""
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
async def scale_deployment(
    namespace: str, name: str, replicas: int, connection_id: str = ""
) -> dict:
    """Scales a deployment to the specified number of replicas."""
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
            "detail": f"Deployment '{name}' scaled to {replicas} replicas.",
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
async def rollout_restart(
    namespace: str, deployment_name: str, connection_id: str = ""
) -> dict:
    """Performs a rollout restart of a deployment."""
    _, apps_v1, _ = await _get_k8s_client(connection_id)

    try:
        # Rollout Restart = update annotation
        now = datetime.now(timezone.utc).isoformat()
        body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {"kubectl.kubernetes.io/restartedAt": now}
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
            "detail": f"Rollout restart for '{deployment_name}' initiated.",
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
async def get_deployment_status(
    namespace: str, name: str, connection_id: str = ""
) -> dict:
    """Returns the detailed status of a deployment."""
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
            "image": dep.spec.template.spec.containers[0].image
            if dep.spec.template.spec.containers
            else "unknown",
        }
    except client.ApiException as e:
        return {"error": f"{e.reason} ({e.status})"}


@tool
async def get_recent_events(
    namespace: str = "default", last_minutes: int = 30, connection_id: str = ""
) -> list[dict]:
    """Returns the recent Kubernetes events of a namespace."""
    v1, _, _ = await _get_k8s_client(connection_id)

    events = v1.list_namespaced_event(namespace=namespace)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=last_minutes)

    recent = []
    for e in events.items:
        event_time = e.last_timestamp or e.event_time or e.metadata.creation_timestamp
        if event_time and event_time.replace(tzinfo=timezone.utc) >= cutoff:
            recent.append(
                {
                    "type": e.type,
                    "reason": e.reason,
                    "message": e.message,
                    "source": e.source.component if e.source else "",
                    "object": f"{e.involved_object.kind}/{e.involved_object.name}"
                    if e.involved_object
                    else "",
                    "timestamp": event_time.isoformat() if event_time else "",
                }
            )

    return sorted(recent, key=lambda x: x["timestamp"], reverse=True)


@tool
async def list_services(
    namespace: str = "default", connection_id: str = ""
) -> list[dict]:
    """Lists all services in a namespace."""
    v1, _, _ = await _get_k8s_client(connection_id)

    services = v1.list_namespaced_service(namespace=namespace)
    return [
        {
            "name": svc.metadata.name,
            "namespace": svc.metadata.namespace,
            "type": svc.spec.type,
            "cluster_ip": svc.spec.cluster_ip or "",
            "ports": [
                f"{p.port}/{p.protocol}"
                + (f"→{p.target_port}" if p.target_port else "")
                for p in (svc.spec.ports or [])
            ],
        }
        for svc in services.items
    ]


@tool
async def list_ingresses(
    namespace: str = "default", connection_id: str = ""
) -> list[dict]:
    """Lists all ingresses in a namespace."""
    _, _, net_v1 = await _get_k8s_client(connection_id)

    ingresses = net_v1.list_namespaced_ingress(namespace=namespace)
    return [
        {
            "name": ing.metadata.name,
            "namespace": ing.metadata.namespace,
            "hosts": [rule.host for rule in (ing.spec.rules or []) if rule.host],
            "class_name": ing.spec.ingress_class_name or "",
        }
        for ing in ingresses.items
    ]


@tool
async def list_pvcs(namespace: str = "default", connection_id: str = "") -> list[dict]:
    """Lists all PersistentVolumeClaims in a namespace."""
    v1, _, _ = await _get_k8s_client(connection_id)

    pvcs = v1.list_namespaced_persistent_volume_claim(namespace=namespace)
    return [
        {
            "name": pvc.metadata.name,
            "namespace": pvc.metadata.namespace,
            "status": pvc.status.phase,
            "capacity": (
                pvc.status.capacity.get("storage", "") if pvc.status.capacity else ""
            ),
            "storage_class": pvc.spec.storage_class_name or "",
        }
        for pvc in pvcs.items
    ]


@tool
async def list_deployments(
    namespace: str = "default", connection_id: str = ""
) -> list[dict]:
    """Lists all Deployments in a namespace with replica counts and image info."""
    _, apps_v1, _ = await _get_k8s_client(connection_id)
    deps = apps_v1.list_namespaced_deployment(namespace=namespace)
    return [
        {
            "name": d.metadata.name,
            "namespace": d.metadata.namespace,
            "ready": f"{d.status.ready_replicas or 0}/{d.spec.replicas}",
            "available": d.status.available_replicas or 0,
            "image": d.spec.template.spec.containers[0].image
            if d.spec.template.spec.containers
            else "",
            "age": _pod_age(d.metadata.creation_timestamp),
        }
        for d in deps.items
    ]


@tool
async def apply_manifest(
    yaml_content: str, namespace: str = "default", connection_id: str = ""
) -> dict:
    """Create or update any Kubernetes resource from a YAML manifest string.

    Accepts a YAML string describing one or more resources (Pod, Deployment, Service,
    ConfigMap, etc.). Uses server-side apply semantics: creates the resource if it does
    not exist, patches it if it does. Multi-document YAML (---) is supported.

    Args:
        yaml_content: Full YAML manifest as a string.
        namespace: Target namespace if not specified in the manifest metadata.
        connection_id: Optional Kubernetes connection ID.
    """
    dyn = await _get_dynamic_client(connection_id)
    results = []
    for doc in _yaml.safe_load_all(yaml_content):
        if not doc:
            continue
        api_version = doc.get("apiVersion", "v1")
        kind = doc.get("kind", "")
        name = doc.get("metadata", {}).get("name", "")
        ns = doc.get("metadata", {}).get("namespace", namespace)

        try:
            resource = dyn.resources.get(api_version=api_version, kind=kind)
            # server-side apply: creates or patches transparently
            resp = resource.server_side_apply(
                body=doc,
                name=name,
                namespace=ns if resource.namespaced else None,
                field_manager="ninko",
            )
            results.append(
                {
                    "kind": kind,
                    "name": name,
                    "namespace": ns,
                    "status": "applied",
                    "resource_version": resp.metadata.resourceVersion,
                }
            )
        except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
            results.append(
                {
                    "kind": kind,
                    "name": name,
                    "namespace": ns,
                    "status": "error",
                    "detail": str(e),
                }
            )
    return {
        "applied": len([r for r in results if r["status"] == "applied"]),
        "results": results,
    }


@tool
async def delete_resource(
    kind: str,
    name: str,
    namespace: str = "default",
    api_version: str = "v1",
    connection_id: str = "",
) -> dict:
    """Delete any Kubernetes resource by kind, name and namespace.

    Args:
        kind: Resource kind, e.g. 'Pod', 'Deployment', 'Service', 'ConfigMap'.
        name: Name of the resource to delete.
        namespace: Namespace of the resource (ignored for cluster-scoped resources).
        api_version: API version, e.g. 'v1', 'apps/v1'. Defaults to 'v1'.
        connection_id: Optional Kubernetes connection ID.
    """
    dyn = await _get_dynamic_client(connection_id)
    try:
        resource = dyn.resources.get(api_version=api_version, kind=kind)
        resource.delete(
            name=name,
            namespace=namespace if resource.namespaced else None,
        )
        return {
            "action": "delete",
            "kind": kind,
            "name": name,
            "namespace": namespace,
            "status": "deleted",
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        return {
            "action": "delete",
            "kind": kind,
            "name": name,
            "namespace": namespace,
            "status": "error",
            "detail": str(e),
        }


@tool
async def get_resource_yaml(
    kind: str,
    name: str,
    namespace: str = "default",
    api_version: str = "v1",
    connection_id: str = "",
) -> str:
    """Returns the live YAML manifest of any Kubernetes resource.

    Useful for inspecting the current state, editing, or debugging a resource.

    Args:
        kind: Resource kind, e.g. 'Pod', 'Deployment', 'Service'.
        name: Resource name.
        namespace: Namespace (ignored for cluster-scoped resources).
        api_version: API version, e.g. 'v1', 'apps/v1'.
        connection_id: Optional Kubernetes connection ID.
    """
    dyn = await _get_dynamic_client(connection_id)
    try:
        resource = dyn.resources.get(api_version=api_version, kind=kind)
        obj = resource.get(
            name=name,
            namespace=namespace if resource.namespaced else None,
        )
        # Strip managed fields to keep output readable
        obj_dict = obj.to_dict()
        obj_dict.get("metadata", {}).pop("managedFields", None)
        return _yaml.dump(obj_dict, default_flow_style=False, allow_unicode=True)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        return f"Error: {e}"


@tool
async def create_namespace(
    name: str, labels: dict | None = None, connection_id: str = ""
) -> dict:
    """Creates a new Kubernetes namespace.

    Args:
        name: Name of the namespace to create.
        labels: Optional dict of labels to attach.
        connection_id: Optional Kubernetes connection ID.
    """
    v1, _, _ = await _get_k8s_client(connection_id)
    body = client.V1Namespace(
        metadata=client.V1ObjectMeta(name=name, labels=labels or {})
    )
    try:
        ns = v1.create_namespace(body=body)
        return {
            "action": "create_namespace",
            "name": ns.metadata.name,
            "status": "created",
        }
    except client.ApiException as e:
        return {
            "action": "create_namespace",
            "name": name,
            "status": "error",
            "detail": f"{e.reason} ({e.status})",
        }


@tool
async def create_deployment(
    name: str,
    image: str,
    namespace: str = "default",
    replicas: int = 1,
    port: int | None = None,
    env_vars: list[dict] | None = None,
    resources: dict | None = None,
    labels: dict | None = None,
    connection_id: str = "",
) -> dict:
    """Creates a full Deployment with container configuration.

    Args:
        name: Name of the deployment.
        image: Container image (e.g., nginx:latest).
        namespace: Target namespace.
        replicas: Number of replicas (default: 1).
        port: Container port to expose.
        env_vars: List of env vars [{"name": "KEY", "value": "val"}].
        resources: Dict with "limits" and/or "requests" cpu/memory.
        labels: Dict of labels to attach.
        connection_id: Optional Kubernetes connection ID.
    """
    _, apps_v1, _ = await _get_k8s_client(connection_id)

    container = client.V1Container(
        name=name,
        image=image,
        ports=[client.V1ContainerPort(container_port=port)] if port else None,
        env=[
            client.V1EnvVar(name=e["name"], value=e.get("value"))
            for e in (env_vars or [])
        ],
        resources=client.V1ResourceRequirements(
            limits=resources.get("limits") if resources else None,
            requests=resources.get("requests") if resources else None,
        )
        if resources
        else None,
    )

    pod_spec = client.V1PodSpec(containers=[container])
    selector = {"app": name}
    pod_template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels=labels or selector),
        spec=pod_spec,
    )

    body = client.V1Deployment(
        metadata=client.V1ObjectMeta(
            name=name, namespace=namespace, labels=labels or None
        ),
        spec=client.V1DeploymentSpec(
            replicas=replicas,
            selector=client.V1LabelSelector(match_labels=selector),
            template=pod_template,
        ),
    )

    try:
        dep = apps_v1.create_namespaced_deployment(namespace=namespace, body=body)
        return {
            "action": "create_deployment",
            "name": dep.metadata.name,
            "namespace": namespace,
            "replicas": dep.spec.replicas,
            "image": dep.spec.template.spec.containers[0].image,
            "status": "created",
        }
    except client.ApiException as e:
        return {
            "action": "create_deployment",
            "name": name,
            "namespace": namespace,
            "status": "error",
            "detail": f"{e.reason} ({e.status})",
        }


@tool
async def patch_deployment(
    name: str,
    namespace: str = "default",
    image: str | None = None,
    replicas: int | None = None,
    env_vars: list[dict] | None = None,
    resources: dict | None = None,
    connection_id: str = "",
) -> dict:
    """Patches a Deployment with changes to image, replicas, env vars, or resources.

    Args:
        name: Name of the deployment to patch.
        namespace: Namespace of the deployment.
        image: New container image (e.g. nginx:1.25).
        replicas: New replica count.
        env_vars: List of env vars to set/update [{"name": "KEY", "value": "val"}].
        resources: Dict with "limits" and/or "requests" cpu/memory.
        connection_id: Optional Kubernetes connection ID.
    """
    if image is None and replicas is None and env_vars is None and resources is None:
        return {
            "action": "patch_deployment",
            "name": name,
            "namespace": namespace,
            "status": "error",
            "detail": "Keine Patch-Parameter angegeben. Mindestens einer benötigt: image, replicas, env_vars, oder resources. Für komplexere Änderungen (Ports, Config) verwende get_resource_yaml + apply_manifest.",
        }

    _, apps_v1, _ = await _get_k8s_client(connection_id)

    body: dict = {"spec": {}}

    if replicas is not None:
        body["spec"]["replicas"] = replicas

    if image or env_vars or resources:
        container_patch = {}
        env_list = None
        resources_obj = None

        if env_vars:
            env_list = [
                client.V1EnvVar(name=e["name"], value=e.get("value")) for e in env_vars
            ]

        if resources:
            resources_obj = client.V1ResourceRequirements(
                limits=resources.get("limits") if resources else None,
                requests=resources.get("requests") if resources else None,
            )

        if image or env_list or resources_obj:
            container_patch = {
                "name": name,
            }
            if image:
                container_patch["image"] = image
            if env_list:
                container_patch["env"] = env_list
            if resources_obj:
                container_patch["resources"] = resources_obj

        body["spec"]["template"] = {"spec": {"containers": [container_patch]}}

    try:
        apps_v1.patch_namespaced_deployment(name=name, namespace=namespace, body=body)
        return {
            "action": "patch_deployment",
            "name": name,
            "namespace": namespace,
            "status": "patched",
            "detail": "Deployment updated successfully.",
        }
    except client.ApiException as e:
        return {
            "action": "patch_deployment",
            "name": name,
            "namespace": namespace,
            "status": "error",
            "detail": f"{e.reason} ({e.status})",
        }


@tool
async def patch_configmap(
    name: str,
    namespace: str = "default",
    data: dict | None = None,
    connection_id: str = "",
) -> dict:
    """Patches a ConfigMap with new or updated data entries.

    Args:
        name: Name of the ConfigMap to patch.
        namespace: Namespace of the ConfigMap.
        data: Dict of key-value pairs to set/update.
        connection_id: Optional Kubernetes connection ID.
    """
    v1, _, _ = await _get_k8s_client(connection_id)

    body = {"data": data}
    try:
        v1.patch_namespaced_config_map(name=name, namespace=namespace, body=body)
        return {
            "action": "patch_configmap",
            "name": name,
            "namespace": namespace,
            "status": "patched",
        }
    except client.ApiException as e:
        return {
            "action": "patch_configmap",
            "name": name,
            "namespace": namespace,
            "status": "error",
            "detail": f"{e.reason} ({e.status})",
        }


@tool
async def create_configmap(
    name: str,
    namespace: str = "default",
    data: dict | None = None,
    labels: dict | None = None,
    connection_id: str = "",
) -> dict:
    """Creates a ConfigMap with key-value data.

    Args:
        name: Name of the ConfigMap.
        namespace: Target namespace.
        data: Dict of key-value pairs.
        labels: Optional dict of labels.
        connection_id: Optional Kubernetes connection ID.
    """
    v1, _, _ = await _get_k8s_client(connection_id)

    body = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(
            name=name, namespace=namespace, labels=labels or {}
        ),
        data=data or {},
    )
    try:
        cm = v1.create_namespaced_config_map(namespace=namespace, body=body)
        return {
            "action": "create_configmap",
            "name": cm.metadata.name,
            "namespace": namespace,
            "status": "created",
        }
    except client.ApiException as e:
        return {
            "action": "create_configmap",
            "name": name,
            "namespace": namespace,
            "status": "error",
            "detail": f"{e.reason} ({e.status})",
        }
