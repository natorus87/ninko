# Changelog

All notable changes to this module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
