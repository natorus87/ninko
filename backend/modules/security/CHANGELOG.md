# Changelog

All notable changes to this module will be documented in this file.

## [0.1.0] - 2026-07-13

### Added

- Security Core domain model (`SecurityTarget`, `ScannerDefinition`, `ScanProfile`,
  `ScanRun`, `Finding`, `FindingEnrichment`) with fingerprint-based dedupe and a
  full finding-status lifecycle.
- SQLite persistence (`db.py`) for targets, scan runs, findings, and enrichments.
- Typed `SecurityScannerAdapter` protocol and `ExecutionSpec` — no shell strings,
  only argument arrays, guarded by `assert_no_shell_string()`.
- `K8sJobExecutor`: one isolated, short-lived Kubernetes Job per scan, non-root,
  read-only root filesystem, capabilities dropped by default, no token automount,
  per-job NetworkPolicy, dedicated `ninko-security` namespace.
- 9 scanner adapters: Trivy, Gitleaks, Checkov, Kubescape, KubeLinter, Nmap,
  Nuclei, testssl.sh, Garak.
- Policy engine (`policy.py`): network scope enforcement (net_guard reuse + CIDR
  allowlist + DNS re-resolve), target/profile allowlists, trigger policy,
  approval gate for intrusive scans.
- Security Orchestrator Agent plus 7 domain specialist agent profiles
  (Kubernetes, Container, Network, Web, Repository, Host, AI Security), a
  Remediation Agent (proposals only, never auto-applied), and a Security Report
  Agent — 9 dynamic agent profiles total, none with `execute_cli_command`.
- 5 curated multi-scanner audit workflows plus matching Ninko workflow templates
  and scheduler integration (intrusive profiles are always skipped in scheduled
  runs, never auto-executed).
- LLM finding enrichment (`enrichment.py`) with a structured, validated output
  schema stored separately from the original finding.
- Notification fan-out (`notify.py`) reusing `core.alert_state.AlertStateManager`
  for dedup/cooldown.
- REST API under `/api/security/*` (17 routes) with RBAC via the generic
  `api_security_policy` fallback.
- Security dashboard tab (Overview/Targets/Runs/Findings) using DOM-safe event
  delegation.
- 351 unit tests covering registry/validation, agents, workflows, findings, and
  permission/tenant-isolation boundaries.

### Known limitations

See "Bekannte Grenzen & Folgearbeiten" in
`.claude/memory/project_security_core.md` — most notably: cluster RBAC is not
currently enforced on the target microk8s cluster (external issue), and only
Trivy and Gitleaks have been verified against live scan runs.
