# Changelog

All notable changes to this module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
