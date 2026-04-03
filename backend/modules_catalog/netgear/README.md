# Netgear Module

Netgear Network Devices – Switches, Routers, Access Points Management via HTTP API.

## Features

- Get system information
- List ports and status
- Get port statistics
- List VLANs
- List ARP table
- List LLDP neighbors
- Enable/disable ports
- Reboot device

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `NETGEAR_HOST` | Netgear device hostname/IP |
| `NETGEAR_USER` | Username (default: admin) |
| `NETGEAR_PASSWORD` | Password (stored in Vault) |

### Connection Manager

Create a connection via the Ninko dashboard with:
- **Host**: Device hostname/IP
- **User**: Username
- **Password**: Password

## Routing Keywords

- `netgear`, `netgear switch`, `netgear router`, `netgear ap`, `netgear access point`, `gs108`, `gs110`, `gs116`, `prosafe`

## API Endpoints

- `GET /api/netgear/health` – Health check
- `GET /api/netgear/status` – Device status

## Tools

| Tool | Description |
|------|-------------|
| `get_netgear_sysinfo` | Get device info |
| `list_netgear_ports` | List all ports |
| `list_netgear_vlans` | List VLANs |
| `get_netgear_port_stats` | Get port stats |
| `list_netgear_arp` | List ARP table |
| `list_netgear_lldp` | List LLDP neighbors |
| `enable_netgear_port` | Enable port |
| `disable_netgear_port` | Disable port |
| `reboot_netgear` | Reboot device |