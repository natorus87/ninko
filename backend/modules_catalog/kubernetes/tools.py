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
        ) from e

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
    namespace: str = "", connection_id: str = ""
) -> list[dict]:
    """Lists pods. Empty namespace returns pods from ALL namespaces (cluster-wide)."""
    v1, _, _ = await _get_k8s_client(connection_id)
    pods = (
        v1.list_pod_for_all_namespaces()
        if not namespace
        else v1.list_namespaced_pod(namespace=namespace)
    )

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
    """Restarts a single pod.

    Use for 'Pod Neustart', 'Pod neustarten', or 'Pod neu starten'.
    Deletes the pod; the controller creates a new one.
    """
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
    """Performs a rollout restart of a deployment.

    Use for 'Rollout Neustart', 'Deployment neustarten', or 'Deployment neu starten'.
    """
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
    namespace: str = "", last_minutes: int = 30, connection_id: str = ""
) -> list[dict]:
    """Returns recent Kubernetes events. Empty namespace returns events from ALL namespaces."""
    v1, _, _ = await _get_k8s_client(connection_id)

    events = (
        v1.list_event_for_all_namespaces()
        if not namespace
        else v1.list_namespaced_event(namespace=namespace)
    )
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
    namespace: str = "", connection_id: str = ""
) -> list[dict]:
    """Lists services. Empty namespace returns services from ALL namespaces."""
    v1, _, _ = await _get_k8s_client(connection_id)

    services = (
        v1.list_service_for_all_namespaces()
        if not namespace
        else v1.list_namespaced_service(namespace=namespace)
    )
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
    namespace: str = "", connection_id: str = ""
) -> list[dict]:
    """Lists ingresses. Empty namespace returns ingresses from ALL namespaces."""
    _, _, net_v1 = await _get_k8s_client(connection_id)

    ingresses = (
        net_v1.list_ingress_for_all_namespaces()
        if not namespace
        else net_v1.list_namespaced_ingress(namespace=namespace)
    )
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
async def list_pvcs(namespace: str = "", connection_id: str = "") -> list[dict]:
    """Lists PersistentVolumeClaims. Empty namespace returns PVCs from ALL namespaces."""
    v1, _, _ = await _get_k8s_client(connection_id)

    pvcs = (
        v1.list_persistent_volume_claim_for_all_namespaces()
        if not namespace
        else v1.list_namespaced_persistent_volume_claim(namespace=namespace)
    )
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
    namespace: str = "", connection_id: str = ""
) -> list[dict]:
    """Lists Deployments. Empty namespace returns deployments from ALL namespaces."""
    _, apps_v1, _ = await _get_k8s_client(connection_id)
    deps = (
        apps_v1.list_deployment_for_all_namespaces()
        if not namespace
        else apps_v1.list_namespaced_deployment(namespace=namespace)
    )
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


# ─────────────────────────────────────────────────────────────────────────────
# Nodes (cluster-scoped)
# ─────────────────────────────────────────────────────────────────────────────


def _node_roles(node) -> list[str]:
    labels = node.metadata.labels or {}
    roles = [
        k.split("/", 1)[1]
        for k in labels
        if k.startswith("node-role.kubernetes.io/")
    ]
    return roles or ["<none>"]


def _node_ready(node) -> str:
    for cond in node.status.conditions or []:
        if cond.type == "Ready":
            return "Ready" if cond.status == "True" else f"NotReady ({cond.reason})"
    return "Unknown"


@tool
async def list_nodes(connection_id: str = "") -> list[dict]:
    """Lists all cluster nodes with status, roles, version and age."""
    v1, _, _ = await _get_k8s_client(connection_id)
    nodes = v1.list_node()
    return [
        {
            "name": n.metadata.name,
            "status": _node_ready(n),
            "roles": _node_roles(n),
            "version": (n.status.node_info.kubelet_version if n.status.node_info else ""),
            "os_image": (n.status.node_info.os_image if n.status.node_info else ""),
            "kernel": (n.status.node_info.kernel_version if n.status.node_info else ""),
            "container_runtime": (
                n.status.node_info.container_runtime_version
                if n.status.node_info
                else ""
            ),
            "internal_ip": next(
                (
                    a.address
                    for a in (n.status.addresses or [])
                    if a.type == "InternalIP"
                ),
                "",
            ),
            "age": _pod_age(n.metadata.creation_timestamp),
        }
        for n in nodes.items
    ]


@tool
async def describe_node(name: str, connection_id: str = "") -> dict:
    """Returns detailed node info: capacity, allocatable, conditions, taints, addresses."""
    v1, _, _ = await _get_k8s_client(connection_id)
    try:
        n = v1.read_node(name=name)
    except client.ApiException as e:
        return {"name": name, "error": f"{e.reason} ({e.status})"}

    return {
        "name": n.metadata.name,
        "status": _node_ready(n),
        "roles": _node_roles(n),
        "labels": dict(n.metadata.labels or {}),
        "annotations": dict(n.metadata.annotations or {}),
        "age": _pod_age(n.metadata.creation_timestamp),
        "node_info": {
            "kubelet_version": n.status.node_info.kubelet_version,
            "os_image": n.status.node_info.os_image,
            "kernel_version": n.status.node_info.kernel_version,
            "container_runtime": n.status.node_info.container_runtime_version,
            "architecture": n.status.node_info.architecture,
        }
        if n.status.node_info
        else {},
        "capacity": dict(n.status.capacity or {}),
        "allocatable": dict(n.status.allocatable or {}),
        "addresses": [
            {"type": a.type, "address": a.address} for a in (n.status.addresses or [])
        ],
        "conditions": [
            {
                "type": c.type,
                "status": c.status,
                "reason": c.reason or "",
                "message": c.message or "",
            }
            for c in (n.status.conditions or [])
        ],
        "taints": [
            {"key": t.key, "value": t.value, "effect": t.effect}
            for t in (n.spec.taints or [])
        ],
        "unschedulable": bool(n.spec.unschedulable),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Describe Pod (detailed)
# ─────────────────────────────────────────────────────────────────────────────


@tool
async def describe_pod(
    namespace: str, name: str, connection_id: str = ""
) -> dict:
    """Returns detailed pod info: containers, conditions, recent events, init containers."""
    v1, _, _ = await _get_k8s_client(connection_id)
    try:
        p = v1.read_namespaced_pod(name=name, namespace=namespace)
    except client.ApiException as e:
        return {"name": name, "namespace": namespace, "error": f"{e.reason} ({e.status})"}

    def _container_state(cs) -> dict:
        if cs.state and cs.state.running:
            return {"state": "running", "started_at": str(cs.state.running.started_at or "")}
        if cs.state and cs.state.waiting:
            return {
                "state": "waiting",
                "reason": cs.state.waiting.reason or "",
                "message": cs.state.waiting.message or "",
            }
        if cs.state and cs.state.terminated:
            return {
                "state": "terminated",
                "reason": cs.state.terminated.reason or "",
                "exit_code": cs.state.terminated.exit_code,
                "message": cs.state.terminated.message or "",
            }
        return {"state": "unknown"}

    containers = []
    for c in p.spec.containers or []:
        cs = next(
            (s for s in (p.status.container_statuses or []) if s.name == c.name),
            None,
        )
        containers.append(
            {
                "name": c.name,
                "image": c.image,
                "ready": cs.ready if cs else False,
                "restarts": cs.restart_count if cs else 0,
                "state": _container_state(cs) if cs else {"state": "pending"},
                "ports": [
                    f"{port.container_port}/{port.protocol or 'TCP'}"
                    for port in (c.ports or [])
                ],
                "env": [
                    {"name": e.name, "value": e.value}
                    for e in (c.env or [])
                    if e.value is not None
                ],
                "resources": {
                    "requests": dict(c.resources.requests or {})
                    if c.resources
                    else {},
                    "limits": dict(c.resources.limits or {}) if c.resources else {},
                },
            }
        )

    # Recent events involving this pod
    events_raw = v1.list_namespaced_event(
        namespace=namespace,
        field_selector=f"involvedObject.name={name},involvedObject.kind=Pod",
    )
    events = sorted(
        [
            {
                "type": ev.type,
                "reason": ev.reason,
                "message": ev.message,
                "timestamp": (
                    ev.last_timestamp or ev.event_time or ev.metadata.creation_timestamp
                ).isoformat()
                if (ev.last_timestamp or ev.event_time or ev.metadata.creation_timestamp)
                else "",
            }
            for ev in events_raw.items
        ],
        key=lambda x: x["timestamp"],
        reverse=True,
    )[:20]

    return {
        "name": p.metadata.name,
        "namespace": p.metadata.namespace,
        "node": p.spec.node_name or "",
        "status": p.status.phase,
        "pod_ip": p.status.pod_ip or "",
        "host_ip": p.status.host_ip or "",
        "age": _pod_age(p.metadata.creation_timestamp),
        "service_account": p.spec.service_account_name or "",
        "qos_class": p.status.qos_class or "",
        "labels": dict(p.metadata.labels or {}),
        "annotations": dict(p.metadata.annotations or {}),
        "containers": containers,
        "init_containers": [
            {"name": c.name, "image": c.image} for c in (p.spec.init_containers or [])
        ],
        "conditions": [
            {
                "type": c.type,
                "status": c.status,
                "reason": c.reason or "",
                "message": c.message or "",
            }
            for c in (p.status.conditions or [])
        ],
        "owner": [
            {"kind": o.kind, "name": o.name}
            for o in (p.metadata.owner_references or [])
        ],
        "events": events,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Additional workload types
# ─────────────────────────────────────────────────────────────────────────────


@tool
async def list_statefulsets(
    namespace: str = "", connection_id: str = ""
) -> list[dict]:
    """Lists StatefulSets. Empty namespace returns StatefulSets from ALL namespaces."""
    _, apps_v1, _ = await _get_k8s_client(connection_id)
    sts = (
        apps_v1.list_stateful_set_for_all_namespaces()
        if not namespace
        else apps_v1.list_namespaced_stateful_set(namespace=namespace)
    )
    return [
        {
            "name": s.metadata.name,
            "namespace": s.metadata.namespace,
            "ready": f"{s.status.ready_replicas or 0}/{s.spec.replicas}",
            "service_name": s.spec.service_name or "",
            "image": s.spec.template.spec.containers[0].image
            if s.spec.template.spec.containers
            else "",
            "age": _pod_age(s.metadata.creation_timestamp),
        }
        for s in sts.items
    ]


@tool
async def list_daemonsets(
    namespace: str = "", connection_id: str = ""
) -> list[dict]:
    """Lists DaemonSets. Empty namespace returns DaemonSets from ALL namespaces."""
    _, apps_v1, _ = await _get_k8s_client(connection_id)
    ds = (
        apps_v1.list_daemon_set_for_all_namespaces()
        if not namespace
        else apps_v1.list_namespaced_daemon_set(namespace=namespace)
    )
    return [
        {
            "name": d.metadata.name,
            "namespace": d.metadata.namespace,
            "desired": d.status.desired_number_scheduled or 0,
            "current": d.status.current_number_scheduled or 0,
            "ready": d.status.number_ready or 0,
            "up_to_date": d.status.updated_number_scheduled or 0,
            "available": d.status.number_available or 0,
            "image": d.spec.template.spec.containers[0].image
            if d.spec.template.spec.containers
            else "",
            "age": _pod_age(d.metadata.creation_timestamp),
        }
        for d in ds.items
    ]


@tool
async def list_replicasets(
    namespace: str = "", connection_id: str = ""
) -> list[dict]:
    """Lists ReplicaSets. Empty namespace returns ReplicaSets from ALL namespaces."""
    _, apps_v1, _ = await _get_k8s_client(connection_id)
    rs = (
        apps_v1.list_replica_set_for_all_namespaces()
        if not namespace
        else apps_v1.list_namespaced_replica_set(namespace=namespace)
    )
    return [
        {
            "name": r.metadata.name,
            "namespace": r.metadata.namespace,
            "desired": r.spec.replicas or 0,
            "current": r.status.replicas or 0,
            "ready": r.status.ready_replicas or 0,
            "owner": (
                f"{r.metadata.owner_references[0].kind}/{r.metadata.owner_references[0].name}"
                if r.metadata.owner_references
                else ""
            ),
            "age": _pod_age(r.metadata.creation_timestamp),
        }
        for r in rs.items
    ]


@tool
async def list_jobs(namespace: str = "", connection_id: str = "") -> list[dict]:
    """Lists Jobs. Empty namespace returns Jobs from ALL namespaces."""
    await _get_k8s_client(connection_id)
    batch_v1 = client.BatchV1Api()
    jobs = (
        batch_v1.list_job_for_all_namespaces()
        if not namespace
        else batch_v1.list_namespaced_job(namespace=namespace)
    )
    return [
        {
            "name": j.metadata.name,
            "namespace": j.metadata.namespace,
            "completions": f"{j.status.succeeded or 0}/{j.spec.completions or 1}",
            "active": j.status.active or 0,
            "failed": j.status.failed or 0,
            "duration": _pod_age(j.status.start_time) if j.status.start_time else "",
            "age": _pod_age(j.metadata.creation_timestamp),
        }
        for j in jobs.items
    ]


@tool
async def list_cronjobs(namespace: str = "", connection_id: str = "") -> list[dict]:
    """Lists CronJobs. Empty namespace returns CronJobs from ALL namespaces."""
    await _get_k8s_client(connection_id)
    batch_v1 = client.BatchV1Api()
    cjs = (
        batch_v1.list_cron_job_for_all_namespaces()
        if not namespace
        else batch_v1.list_namespaced_cron_job(namespace=namespace)
    )
    return [
        {
            "name": c.metadata.name,
            "namespace": c.metadata.namespace,
            "schedule": c.spec.schedule,
            "suspend": bool(c.spec.suspend),
            "active": len(c.status.active or []),
            "last_schedule": c.status.last_schedule_time.isoformat()
            if c.status.last_schedule_time
            else "",
            "age": _pod_age(c.metadata.creation_timestamp),
        }
        for c in cjs.items
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Config and Secrets (metadata only — secret values never returned)
# ─────────────────────────────────────────────────────────────────────────────


@tool
async def list_configmaps(
    namespace: str = "", connection_id: str = ""
) -> list[dict]:
    """Lists ConfigMaps (names and key counts). Empty namespace returns ALL namespaces."""
    v1, _, _ = await _get_k8s_client(connection_id)
    cms = (
        v1.list_config_map_for_all_namespaces()
        if not namespace
        else v1.list_namespaced_config_map(namespace=namespace)
    )
    return [
        {
            "name": cm.metadata.name,
            "namespace": cm.metadata.namespace,
            "data_keys": list((cm.data or {}).keys()),
            "binary_keys": list((cm.binary_data or {}).keys()),
            "age": _pod_age(cm.metadata.creation_timestamp),
        }
        for cm in cms.items
    ]


@tool
async def list_secrets(
    namespace: str = "", connection_id: str = ""
) -> list[dict]:
    """Lists Secrets (METADATA ONLY — secret values are never returned). Empty namespace = ALL."""
    v1, _, _ = await _get_k8s_client(connection_id)
    secs = (
        v1.list_secret_for_all_namespaces()
        if not namespace
        else v1.list_namespaced_secret(namespace=namespace)
    )
    return [
        {
            "name": s.metadata.name,
            "namespace": s.metadata.namespace,
            "type": s.type or "",
            "data_keys": list((s.data or {}).keys()),
            "age": _pod_age(s.metadata.creation_timestamp),
        }
        for s in secs.items
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Cluster-scoped storage
# ─────────────────────────────────────────────────────────────────────────────


@tool
async def list_persistent_volumes(connection_id: str = "") -> list[dict]:
    """Lists all PersistentVolumes (cluster-scoped)."""
    v1, _, _ = await _get_k8s_client(connection_id)
    pvs = v1.list_persistent_volume()
    return [
        {
            "name": pv.metadata.name,
            "capacity": (pv.spec.capacity.get("storage") if pv.spec.capacity else ""),
            "access_modes": pv.spec.access_modes or [],
            "reclaim_policy": pv.spec.persistent_volume_reclaim_policy or "",
            "status": pv.status.phase,
            "claim": (
                f"{pv.spec.claim_ref.namespace}/{pv.spec.claim_ref.name}"
                if pv.spec.claim_ref
                else ""
            ),
            "storage_class": pv.spec.storage_class_name or "",
            "age": _pod_age(pv.metadata.creation_timestamp),
        }
        for pv in pvs.items
    ]


@tool
async def list_storage_classes(connection_id: str = "") -> list[dict]:
    """Lists all StorageClasses (cluster-scoped)."""
    await _get_k8s_client(connection_id)
    storage_v1 = client.StorageV1Api()
    scs = storage_v1.list_storage_class()
    return [
        {
            "name": sc.metadata.name,
            "provisioner": sc.provisioner,
            "reclaim_policy": sc.reclaim_policy or "",
            "volume_binding_mode": sc.volume_binding_mode or "",
            "default": (sc.metadata.annotations or {}).get(
                "storageclass.kubernetes.io/is-default-class", "false"
            )
            == "true",
            "age": _pod_age(sc.metadata.creation_timestamp),
        }
        for sc in scs.items
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Networking
# ─────────────────────────────────────────────────────────────────────────────


@tool
async def list_endpoints(
    namespace: str = "", connection_id: str = ""
) -> list[dict]:
    """Lists Endpoints. Empty namespace returns Endpoints from ALL namespaces."""
    v1, _, _ = await _get_k8s_client(connection_id)
    eps = (
        v1.list_endpoints_for_all_namespaces()
        if not namespace
        else v1.list_namespaced_endpoints(namespace=namespace)
    )
    return [
        {
            "name": ep.metadata.name,
            "namespace": ep.metadata.namespace,
            "endpoints": [
                f"{addr.ip}:{port.port}"
                for subset in (ep.subsets or [])
                for addr in (subset.addresses or [])
                for port in (subset.ports or [])
            ]
            or ["<none>"],
            "age": _pod_age(ep.metadata.creation_timestamp),
        }
        for ep in eps.items
    ]


@tool
async def list_network_policies(
    namespace: str = "", connection_id: str = ""
) -> list[dict]:
    """Lists NetworkPolicies. Empty namespace returns NetworkPolicies from ALL namespaces."""
    _, _, net_v1 = await _get_k8s_client(connection_id)
    nps = (
        net_v1.list_network_policy_for_all_namespaces()
        if not namespace
        else net_v1.list_namespaced_network_policy(namespace=namespace)
    )
    return [
        {
            "name": np.metadata.name,
            "namespace": np.metadata.namespace,
            "pod_selector": dict(np.spec.pod_selector.match_labels or {})
            if np.spec.pod_selector
            else {},
            "policy_types": list(np.spec.policy_types or []),
            "ingress_rules": len(np.spec.ingress or []),
            "egress_rules": len(np.spec.egress or []),
            "age": _pod_age(np.metadata.creation_timestamp),
        }
        for np in nps.items
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Autoscaling
# ─────────────────────────────────────────────────────────────────────────────


@tool
async def list_hpas(namespace: str = "", connection_id: str = "") -> list[dict]:
    """Lists HorizontalPodAutoscalers. Empty namespace returns HPAs from ALL namespaces."""
    await _get_k8s_client(connection_id)
    autoscaling_v2 = client.AutoscalingV2Api()
    hpas = (
        autoscaling_v2.list_horizontal_pod_autoscaler_for_all_namespaces()
        if not namespace
        else autoscaling_v2.list_namespaced_horizontal_pod_autoscaler(namespace=namespace)
    )
    return [
        {
            "name": h.metadata.name,
            "namespace": h.metadata.namespace,
            "reference": f"{h.spec.scale_target_ref.kind}/{h.spec.scale_target_ref.name}",
            "min_replicas": h.spec.min_replicas or 0,
            "max_replicas": h.spec.max_replicas,
            "current_replicas": h.status.current_replicas or 0,
            "desired_replicas": h.status.desired_replicas or 0,
            "age": _pod_age(h.metadata.creation_timestamp),
        }
        for h in hpas.items
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Metrics (requires metrics-server)
# ─────────────────────────────────────────────────────────────────────────────


@tool
async def get_top_nodes(connection_id: str = "") -> list[dict]:
    """Returns CPU/memory usage per node (requires metrics-server installed in cluster)."""
    await _get_k8s_client(connection_id)
    custom = client.CustomObjectsApi()
    try:
        data = custom.list_cluster_custom_object(
            group="metrics.k8s.io", version="v1beta1", plural="nodes"
        )
    except client.ApiException as e:
        return [
            {
                "error": f"Metrics API unavailable: {e.reason} ({e.status}). "
                "Install metrics-server: kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml"
            }
        ]
    return [
        {
            "name": item.get("metadata", {}).get("name", ""),
            "cpu": item.get("usage", {}).get("cpu", ""),
            "memory": item.get("usage", {}).get("memory", ""),
            "timestamp": item.get("timestamp", ""),
            "window": item.get("window", ""),
        }
        for item in data.get("items", [])
    ]


@tool
async def get_top_pods(
    namespace: str = "", connection_id: str = ""
) -> list[dict]:
    """Returns CPU/memory usage per pod (requires metrics-server). Empty namespace = ALL."""
    await _get_k8s_client(connection_id)
    custom = client.CustomObjectsApi()
    try:
        if namespace:
            data = custom.list_namespaced_custom_object(
                group="metrics.k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="pods",
            )
        else:
            data = custom.list_cluster_custom_object(
                group="metrics.k8s.io", version="v1beta1", plural="pods"
            )
    except client.ApiException as e:
        return [
            {
                "error": f"Metrics API unavailable: {e.reason} ({e.status}). "
                "Install metrics-server in the cluster."
            }
        ]
    return [
        {
            "name": item.get("metadata", {}).get("name", ""),
            "namespace": item.get("metadata", {}).get("namespace", ""),
            "containers": [
                {
                    "name": c.get("name", ""),
                    "cpu": c.get("usage", {}).get("cpu", ""),
                    "memory": c.get("usage", {}).get("memory", ""),
                }
                for c in item.get("containers", [])
            ],
            "timestamp": item.get("timestamp", ""),
            "window": item.get("window", ""),
        }
        for item in data.get("items", [])
    ]
