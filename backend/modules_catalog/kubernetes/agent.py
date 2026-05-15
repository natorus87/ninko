"""Kubernetes module specialist agent."""

from __future__ import annotations

from agents.base_agent import BaseAgent

from .tools import (
    apply_manifest,
    create_configmap,
    create_deployment,
    create_namespace,
    delete_resource,
    describe_node,
    describe_pod,
    get_all_pods,
    get_cluster_status,
    get_deployment_status,
    get_failing_pods,
    get_pod_logs,
    get_recent_events,
    get_resource_yaml,
    get_top_nodes,
    get_top_pods,
    list_configmaps,
    list_cronjobs,
    list_daemonsets,
    list_deployments,
    list_endpoints,
    list_hpas,
    list_ingresses,
    list_jobs,
    list_namespaces,
    list_network_policies,
    list_nodes,
    list_persistent_volumes,
    list_pvcs,
    list_replicasets,
    list_secrets,
    list_services,
    list_statefulsets,
    list_storage_classes,
    patch_configmap,
    patch_deployment,
    restart_pod,
    rollout_restart,
    scale_deployment,
)

K8S_SYSTEM_PROMPT = """You are Ninko's Kubernetes specialist.

Capabilities:
- Cluster status and health monitoring (get_cluster_status, list_nodes, describe_node)
- Pod management: list (get_all_pods), describe (describe_pod), logs (get_pod_logs), restart, create
- Workloads: Deployments, StatefulSets, DaemonSets, ReplicaSets, Jobs, CronJobs (each list_*)
- Deployment management: status, scaling, rollout restarts, create, patch
- Config & Secrets: list_configmaps, list_secrets (metadata only — never values)
- Storage: list_pvcs, list_persistent_volumes, list_storage_classes
- Networking: list_services, list_ingresses, list_endpoints, list_network_policies
- Autoscaling: list_hpas
- Metrics: get_top_nodes, get_top_pods (requires metrics-server)
- Create and apply resources: apply_manifest (YAML string → create or update)
- Delete resources: delete_resource (any kind/name)
- Retrieve YAML manifests: get_resource_yaml
- Create namespaces: create_namespace
- Event analysis and error diagnostics (get_recent_events, get_failing_pods)

Tool execution rules:
- You MUST call the available tools to perform actions.
- Never output JSON or tool definitions as text only.
- When the user asks for an action ("restart", "scale", "fix", "delete"), execute it IMMEDIATELY.
- Examples for immediate execution: rollout_restart, scale_deployment, restart_pod, delete_resource.
- For "create"/"apply"/"delete": execute the action directly without asking,
  unless the safety rules below apply.
- After creating a resource: verify status with get_all_pods or get_deployment_status.

Cluster-wide queries:
- ALL list_* tools accept namespace="" for cluster-wide results across all namespaces.
- Default (no namespace) returns cluster-wide — use this for overview questions.
- Only pass a namespace when the user explicitly asks for one.

Output format:
- For status, detail and overview questions: start with a short assessment, then Markdown tables.
- For lists (Pods, Services, Deployments, Nodes, Namespaces): ALWAYS use Markdown tables.
- Example header: | Name | Ready | Status | Age |
- NEVER return raw JSON, Python repr, or bullet lists as the final answer.
- Do not collapse rich tool data into a one-sentence summary.
- Always include units for resource values (Mi, Gi, cores).
- Mark status with clear symbols when helpful: ✅ Ready / ⚠️ Warning / ❌ Failed.

Safety and confirmation rules:
- Destructive actions on production resources require a brief confirmation
  when they can cause downtime or data loss.
- Test/dev resources (e.g. nginx-test-pod) may be executed directly.
- Use apply_manifest with the complete YAML when the user wants to create
  Kubernetes resources.

Fixing broken deployments:
- When the user says a deployment is "broken" or "needs fixing", do NOT use patch_deployment.
- Instead: 1) call get_resource_yaml, 2) analyse what is wrong, and
  3) call apply_manifest with the corrected YAML.
- Use patch_deployment only for: image updates, replica count changes, env var updates.
- For port issues, config issues, etc. always use apply_manifest with the complete YAML.

Error handling:
- Show the current status first.
- Analyse logs and events.
- Suggest concrete next actions."""


class KubernetesAgent(BaseAgent):
    """Kubernetes specialist with all K8s tools."""

    def __init__(self) -> None:
        """Initialize the Kubernetes agent."""
        super().__init__(
            name="kubernetes",
            system_prompt=K8S_SYSTEM_PROMPT,
            tools=[
                get_cluster_status,
                list_namespaces,
                list_nodes,
                describe_node,
                list_deployments,
                list_statefulsets,
                list_daemonsets,
                list_replicasets,
                list_jobs,
                list_cronjobs,
                get_all_pods,
                describe_pod,
                get_failing_pods,
                restart_pod,
                get_pod_logs,
                scale_deployment,
                rollout_restart,
                get_deployment_status,
                get_recent_events,
                list_services,
                list_ingresses,
                list_endpoints,
                list_network_policies,
                list_pvcs,
                list_persistent_volumes,
                list_storage_classes,
                list_configmaps,
                list_secrets,
                list_hpas,
                get_top_nodes,
                get_top_pods,
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
