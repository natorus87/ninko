# Changelog

All notable changes to this module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.9] - 2026-07-04

### Fixed
- `_detect_target_type` misclassified LXC containers as QEMU VMs: `/cluster/resources?type=vm`
  returns both guest types, but the code returned `"qemu"` for any match and used an invalid
  `type="lxc"` query. `smart_reboot` / `smart_start` / `smart_stop` therefore called the wrong
  API endpoint for containers. Now the guest type is read from the resource's own `type` field.
- `get_node_status` always showed node status `unknown` (the detail endpoint has no online/offline
  field); a successful status query now reports `online`.

### Changed
- `get_vm_status` QEMU result now includes an explicit `type: "qemu"` field for consistency.

### Tests
- Added regression tests for LXC-vs-QEMU type detection and `smart_*` endpoint selection.

## [1.1.4] - 2026-06-10

### Added
- Read-only IP discovery tools for Proxmox nodes, QEMU VMs, and LXC containers.
- API routes for single/all node IPs and single/all guest IPs.
- Network adapter and static IP hints in `get_vm_config`.

## [1.1.1] - 2026-04-06

### Added
- Initial release of Proxmox module
- Proxmox Virtual Environment (PVE) management
- API Token authentication support
- Cluster status monitoring (nodes and resources)
- VM and LXC container listing
- VM status monitoring (CPU, RAM, Uptime)
- Power management: start, stop, reset VMs
- Recent tasks and logs viewing
- SSL fallback for self-signed certificates
- Dashboard integration with SVG icon

## Module Information

- **Name**: proxmox
- **Description**: Proxmox VE Management – VMs, Container, Nodes, Snapshots
- **Author**: Ninko Team
