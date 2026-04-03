# Cisco Network Devices Module

Cisco Network Devices – Switches, Routers, Nexus Management via REST API.

## Features

- Get device information (hostname, model, version, uptime)
- List interfaces and status
- Interface details and statistics
- List VLANs
- List routing table
- MAC address table
- PoE status
- Enable/disable interfaces
- Create VLANs
- Set port VLAN membership

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `CISCO_HOST` | Cisco device hostname/IP |
| `CISCO_USER` | Username |
| `CISCO_PASSWORD` | Password (stored in Vault) |

### Connection Manager

Create a connection via the Ninko dashboard with:
- **Host**: Device hostname/IP
- **User**: Username
- **Password**: Password

## Routing Keywords

- `cisco`, `switch`, `router`, `cisco switch`, `cisco router`, `ios`, `nexus`, `catalyst`, `network port`, `vlan`

## API Endpoints

- `GET /api/cisco/health` – Health check
- `GET /api/cisco/status` – Device status

## Tools

| Tool | Description |
|------|-------------|
| `get_cisco_device_info` | Get device info |
| `list_cisco_interfaces` | List all interfaces |
| `get_cisco_interface_details` | Get interface details |
| `list_cisco_vlans` | List VLANs |
| `list_cisco_routes` | List routes |
| `list_cisco_mac_addresses` | List MAC table |
| `get_cisco_poe_status` | Get PoE status |
| `enable_cisco_interface` | Enable port |
| `disable_cisco_interface` | Disable port |
| `create_cisco_vlan` | Create VLAN |
| `set_cisco_interface_vlan` | Set port VLAN |