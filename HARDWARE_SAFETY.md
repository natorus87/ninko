# Hardware Safety Baseline

This runbook defines the minimum physical safeguards for critical infrastructure operated through Ninko.

## Goals
- Prevent a single software failure from causing irreversible production damage.
- Guarantee manual recovery paths independent from API access.

## Baseline Controls
- Management plane separation:
  - Dedicated management VLAN/network for BMC/iLO/iDRAC/switch/firewall admin.
  - No direct exposure of management interfaces to user networks.
- Break-glass access:
  - Documented console access path (IPMI/iLO/KVM/serial) per critical system.
  - At least two operators with tested access.
- Immutable backups:
  - Snapshot + backup retention with offline/immutable copy (3-2-1 minimum).
  - Restore test schedule (at least quarterly).
- Read-only guardrails:
  - Monitoring dashboards/users default to read-only roles.
  - Write-capable credentials limited to dedicated operator accounts.
- Dual control for critical changes:
  - Changes affecting firewall, routing, storage, hypervisor power state, or identity provider need second-person approval.
- Operational logging:
  - Keep operation transaction history (`/api/operations/transactions`) and safeguard audit (`/api/safeguard/audit`) enabled and retained.

## Pre-Change Checklist (Critical Systems)
- Confirm latest backup/snapshot exists and restore path is documented.
- Record rollback command/path before execution.
- Verify out-of-band console works.
- Define blast radius (host, cluster, tenant, network segment).
- Execute during change window with observer on standby.

## Incident Recovery Checklist
- Stop further automation on affected scope.
- Roll back using documented restore/snapshot path.
- Record rollback notes in operation journal.
- Perform postmortem: root cause, containment, prevention action.

