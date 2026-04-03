# MikroTik Module

MikroTik RouterOS – Switches, Routers, Wireless Management via REST API.

## Features

- Get device identity and system info
- List interfaces and status
- Get interface statistics (traffic counters)
- List routing table
- List DHCP leases
- List firewall rules
- List queues
- List wireless clients
- Enable/disable interfaces
- Reboot router
- Create firewall rules
- Add IP addresses

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `MIKROTIK_HOST` | MikroTik device hostname/IP |
| `MIKROTIK_USER` | Username (default: admin) |
| `MIKROTIK_PASSWORD` | Password (stored in Vault) |

### Connection Manager

Create a connection via the Ninko dashboard with:
- **Host**: Device hostname/IP
- **User**: Username
- **Password**: Password

## Routing Keywords

- `mikrotik`, `routeros`, `router board`, `mikrotik router`, `mikrotik switch`, `wireguard`, `wireless`, `capsman`

## API Endpoints

- `GET /api/mikrotik/health` – Health check
- `GET /api/mikrotik/status` – Device status

## Tools

| Tool | Description |
|------|-------------|
| `get_mikrotik_identity` | Get device info |
| `list_mikrotik_interfaces` | List all interfaces |
| `get_mikrotik_interface_stats` | Get interface stats |
| `list_mikrotik_routes` | List routes |
| `list_mikrotik_dhcp_leases` | List DHCP leases |
| `list_mikrotik_firewall_rules` | List firewall rules |
| `list_mikrotik_queues` | List queues |
| `list_mikrotik_wireless_clients` | List wireless clients |
| `enable_mikrotik_interface` | Enable port |
| `disable_mikrotik_interface` | Disable port |
| `reboot_mikrotik` | Reboot router |
| `create_mikrotik_firewall_rule` | Create firewall rule |
| `add_mikrotik_ip_address` | Add IP address |