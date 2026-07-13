# Changelog

All notable changes to this module will be documented in this file.

## [0.1.1] - 2026-07-13

### Fixed

- **Chat/agent tools never propagated tenant_id** (`tools.py`): all 11 `@tool`
  functions called `db.*`/service functions without a `tenant_id`, so every
  chat-driven scan/target/finding operation ran against `tenant_id=""` while
  UI-created targets are stored under `tenant_id="default"`. The chat agent
  could therefore never find a target that visibly existed in the UI. Fixed
  by resolving the tenant via `core.auth.get_current_tenant_id()`, the same
  contextvar-based mechanism already used elsewhere in Ninko for tools that
  have no direct HTTP request object.

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

### Fixed

- **Link-local/cloud-metadata block only applied to http(s)-shaped locators**
  (`policy.py`): `enforce_network_scope()` now runs the same hard block for
  every network target type (IP_ADDRESS/HOSTNAME/CIDR/SSH_HOST/TLS_ENDPOINT),
  not just URLs — previously an IP/hostname target without an explicit
  `cidr_allowlist` had no automated protection at all.
- **Empty NetworkPolicy allowlist silently fell back to open egress**
  (`executor.py`): a job's NetworkPolicy now denies non-DNS egress by default
  when no allowlist is present, regardless of the declared `mode` — the
  previous behavior allowed everything whenever an adapter forgot to populate
  `allowlist`, defeating the `egress_allowlist`/`target_only` mode names. A new
  explicit `mode="open"` covers adapters that genuinely need an unpredictable
  destination (Trivy/Kubescape/Checkov/KubeLinter/Gitleaks); Nmap/testssl.sh/
  Nuclei/Garak now resolve their scan target to a real CIDR allowlist at build
  time (`resolve_locator_egress_allowlist()`, new in `scanner_adapter.py`)
  instead of leaving it empty.
- **Command-injection guard missed disguised `sh -c`/`bash -c` invocations**
  (`scanner_adapter.py`): `assert_no_shell_string()` only rejected a single-
  element shell string; it now also rejects a multi-element shell-interpreter
  invocation with `-c`/`-lc`/`--command`.
- 12 new regression tests for the three fixes above (363 unit tests total).

### Known limitations

See "Bekannte Grenzen & Folgearbeiten" in
`.claude/memory/project_security_core.md` — most notably: cluster RBAC is not
currently enforced on the target microk8s cluster (external issue), and only
Trivy and Gitleaks have been verified against live scan runs.
