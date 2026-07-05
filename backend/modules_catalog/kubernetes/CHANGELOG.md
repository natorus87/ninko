# Changelog

All notable changes to this module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.2] - 2026-07-05

### Fixed
- Simple cluster-status requests from Telegram now ignore transport context prefixes
  such as `[Telegram Chat-ID: ...]` and use the deterministic `get_cluster_status`
  fast-path instead of falling into the LLM tool-retry loop.

## [1.3.0] - 2026-05-11

### Added
- Cluster-weite Abfrage-Tools (alle list_* akzeptieren namespace="" für All-Namespaces):
  - `list_nodes`, `describe_node` — Node-Übersicht und -Details (Capacity, Conditions, Taints)
  - `describe_pod` — Pod-Details inkl. Container-States, Conditions und letzte Events
  - `list_statefulsets`, `list_daemonsets`, `list_replicasets`, `list_jobs`, `list_cronjobs`
  - `list_configmaps`, `list_secrets` (nur Metadaten — Werte werden nie zurückgegeben)
  - `list_persistent_volumes`, `list_storage_classes` (cluster-scoped Storage)
  - `list_endpoints`, `list_network_policies`
  - `list_hpas` (HorizontalPodAutoscaler)
  - `get_top_nodes`, `get_top_pods` (via metrics-server)

### Changed
- `get_all_pods`, `list_deployments`, `list_services`, `list_ingresses`, `list_pvcs`,
  `get_recent_events`: Standard ist jetzt cluster-weit (`namespace=""`). Konkreter
  Namespace optional. Behebt Agent-Antworten der Form "kann keine globale Liste abfragen".

## [1.2.0] - 2026-04-06

### Added
- Initial release of Kubernetes module
- Kubernetes cluster management capabilities
- In-cluster configuration support (runs inside K8s cluster)
- Node metrics monitoring (CPU, Memory, Ready-Status)
- Failed pod detection (Error, CrashLoopBackOff, OOMKilled)
- Pod log retrieval
- Deployment scaling (replicas)
- Rollout restart functionality
- RBAC integration for service accounts
- Local ~/.kube/config fallback for development
- Dashboard integration with SVG icon

## Module Information

- **Name**: kubernetes
- **Description**: Kubernetes Cluster Management – Pods, Deployments, Services, Health-Monitoring
- **Author**: Ninko Team
