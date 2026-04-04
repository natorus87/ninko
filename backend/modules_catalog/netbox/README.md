# NetBox Module

NetBox DCIM & IPAM – Devices, Circuits, IP-Addresses, VLANs, Rack-Management.

## Features

- Get server status and version
- List/create sites and racks
- List/query devices and device details
- List VLANs, prefixes, and IP addresses
- List circuits and cables
- List clusters and virtual machines
- Query device interfaces

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `NETBOX_URL` | NetBox API URL (e.g., `http://netbox.local/api/`) |
| `NETBOX_TOKEN` | NetBox API Token |

### Connection Manager

Create a connection via the Ninko dashboard with:
- **URL**: NetBox API URL
- **Token**: NetBox API Token

## Routing Keywords

`netbox`, `dcim`, `ipam`, `device`, `rack`, `vlan`, `ipaddress`, `circuit`