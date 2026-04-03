# Ubiquiti Module

Ubiquiti UniFi – Switches, Routers, Access Points Management via UniFi Controller API.

## Features

- List all devices (APs, switches, routers)
- List clients (wired and wireless)
- Get device details
- List wireless networks (SSIDs)
- List switch ports
- Get network traffic stats
- List firewall rules
- Restart devices
- Enable/disable WLANs
- Kick clients

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `UNIFI_HOST` | UniFi Controller hostname/IP |
| `UNIFI_USER` | Username |
| `UNIFI_PASSWORD` | Password (stored in Vault) |

### Connection Manager

Create a connection via the Ninko dashboard with:
- **Host**: UniFi Controller URL
- **User**: Username
- **Password**: Password

## Routing Keywords

- `ubiquiti`, `unifi`, `unifi switch`, `unifi router`, `unifi ap`, `unifi access point`, `edgerouter`, `edgeswitch`, `airmax`

## API Endpoints

- `GET /api/ubiquiti/health` – Health check
- `GET /api/ubiquiti/status` – Device status

## Tools

| Tool | Description |
|------|-------------|
| `list_ubiquiti_devices` | List all devices |
| `list_ubiquiti_clients` | List all clients |
| `get_ubiquiti_device` | Get device details |
| `list_ubiquiti_wlans` | List WLANs |
| `list_ubiquiti_switch_ports` | List switch ports |
| `get_ubiquiti_network_stats` | Get network stats |
| `list_ubiquiti_firewall_rules` | List firewall rules |
| `restart_ubiquiti_device` | Restart device |
| `enable_ubiquiti_wlan` | Enable WLAN |
| `disable_ubiquiti_wlan` | Disable WLAN |
| `kick_ubiquiti_client` | Kick client |