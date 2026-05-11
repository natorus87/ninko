# Ninko Module: Kubernetes (☸)

Vollständiges Kubernetes-Cluster-Management in Ninko: cluster-weite Abfragen, Workload-Verwaltung, Health-Diagnose und Manifest-Apply.

**Version:** 1.3.0

## Architektur & Zugriff

Da Ninko primär *in* einem Kubernetes-Cluster betrieben wird, verwendet das Modul standardmäßig die **In-Cluster-Konfiguration** des Pods. Es sind keine zusätzlichen Anmeldedaten erforderlich, sofern der ServiceAccount über ausreichende RBAC-Rechte verfügt (siehe `k8s/rbac.yaml`).

Läuft Ninko lokal, wird die lokale `~/.kube/config` verwendet. Über die ConnectionManager-UI können zusätzliche Kontexte (`prod`, `staging`, …) als verschlüsselte Kubeconfigs im Vault hinterlegt werden — diese sind dann pro Chat-Sitzung wählbar.

## Konfiguration

| Wert | Beschreibung |
|------|--------------|
| `connection_id` | Optionale Connection-ID. Leer = Default (In-Cluster oder lokales `~/.kube/config`) |
| Vault-Key `kubeconfig` | Base64-kodierte Kubeconfig für nicht-lokale Connections |
| Env `K8S_IN_CLUSTER` | `true` (Default) für ServiceAccount-Auth |
| Env `K8S_KUBECONFIG_PATH` | Alternativer Kubeconfig-Pfad, falls nicht in-cluster |

**Required secrets:** keine. **Optional secrets:** `K8S_KUBECONFIG`.

## Features & Tools

### Cluster-weite Abfragen

Alle `list_*`-Tools akzeptieren `namespace=""` (Standard) für cluster-weite Ergebnisse über **alle Namespaces**. Wird ein konkreter Namespace übergeben, wird nur dieser durchsucht.

### Read / Inspect

| Tool | Beschreibung |
|------|--------------|
| `get_cluster_status` | Aggregierte Cluster-Übersicht (Nodes, Namespaces, Pods, Deployments, Failing) |
| `list_namespaces` | Alle Namespaces |
| `list_nodes` | Node-Übersicht (Status, Roles, Version, OS, Age) |
| `describe_node` | Node-Details: Capacity, Allocatable, Conditions, Taints, Addresses |
| `get_all_pods` | Pods cluster-weit oder pro Namespace |
| `describe_pod` | Pod-Details: Container-States, Conditions, Owner, letzte 20 Events |
| `get_failing_pods` | CrashLoopBackOff, ImagePullBackOff, OOMKilled, Failed-Pods |
| `get_pod_logs` | Tail der Container-Logs |
| `get_recent_events` | Kubernetes-Events der letzten N Minuten |
| `list_deployments` / `get_deployment_status` | Deployments und Detail-Status |
| `list_statefulsets` | StatefulSets mit Ready/Replicas |
| `list_daemonsets` | DaemonSets (desired/current/ready/up-to-date) |
| `list_replicasets` | ReplicaSets mit Owner |
| `list_jobs` / `list_cronjobs` | Batch-Workloads inkl. Schedule und Last-Run |
| `list_services` / `list_endpoints` | Services und ihre tatsächlichen Endpoints |
| `list_ingresses` | Ingress-Hosts und -Klassen |
| `list_network_policies` | NetworkPolicy-Selektoren und Regel-Count |
| `list_pvcs` / `list_persistent_volumes` | PVCs und cluster-scoped PVs |
| `list_storage_classes` | StorageClasses inkl. Default-Markierung |
| `list_configmaps` | ConfigMaps mit Key-Listen |
| `list_secrets` | Secrets — **nur Metadaten**, Werte werden nie zurückgegeben |
| `list_hpas` | HorizontalPodAutoscaler (current/desired/min/max) |
| `get_resource_yaml` | Live-YAML beliebiger Ressourcen (`managedFields` werden entfernt) |
| `get_top_nodes` / `get_top_pods` | CPU/Memory pro Node oder Pod (benötigt `metrics-server`) |

### Write / Mutate

| Tool | Beschreibung |
|------|--------------|
| `apply_manifest` | Server-Side-Apply beliebiger YAML-Manifeste (multi-doc unterstützt) |
| `delete_resource` | Generisches Delete (kind + name + namespace) |
| `create_namespace` | Neuer Namespace mit optionalen Labels |
| `create_deployment` | Full-Featured Deployment: Image, Ports, Env, Resources, Labels |
| `patch_deployment` | Update von Image, Replicas, Env oder Resources |
| `scale_deployment` | Replica-Count ändern |
| `rollout_restart` | Rollout-Restart via `kubectl.kubernetes.io/restartedAt` |
| `restart_pod` | Einzelnen Pod löschen (Controller erstellt neu) |
| `create_configmap` / `patch_configmap` | ConfigMaps anlegen oder aktualisieren |

Alle Read-Tools sind im Registry als `readonly=True` markiert und passieren den Safeguard ohne LLM-Klassifizierung. Write-Tools laufen durch die Safeguard-Profile.

## Beispiel-Prompts

- *"Zeig mir alle laufenden Pods im Cluster"* → `get_all_pods` cluster-weit
- *"Welche Nodes gibt es?"* → `list_nodes`
- *"Status von Deployment `frontend` im Namespace `prod`"* → `get_deployment_status`
- *"Skaliere `api` auf 5 Replicas hoch"* → `scale_deployment`
- *"Welche Pods crashen gerade?"* → `get_failing_pods` (cluster-weit)
- *"Zeig CPU-Auslastung der Nodes"* → `get_top_nodes`
- *"Welche StorageClasses sind verfügbar?"* → `list_storage_classes`
- *"Lege einen Test-Pod mit nginx an"* → `apply_manifest`
- *"Lösche das alte CronJob `cleanup-old`"* → `delete_resource`

## Sicherheitshinweise

- `list_secrets` liefert **nur** Namen, Typ und Key-Listen — Secret-Werte werden niemals an den Agenten oder Chat zurückgegeben. Für Werte: `get_resource_yaml` mit Safeguard-Prompt.
- Destruktive Tools (`delete_resource`, `scale_deployment` auf 0, `rollout_restart`) durchlaufen die Safeguard-Klassifizierung. Bei Prod-Connections ist eine Bestätigung empfohlen.
- `apply_manifest` nutzt Server-Side-Apply mit `field_manager="ninko"`, sodass parallele Änderungen anderer Manager nicht überschrieben werden.
