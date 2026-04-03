# Lenovo XClarity Module

Lenovo XClarity Administrator – ThinkSystem/ThinkBlade Server Management via REST API.

## Features

- List managed servers
- Get server details
- List chassis enclosures
- List storage systems
- View server health and alerts
- List events
- View firmware versions
- Power on/off/restart servers
- Identify servers (blink LED)

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `XCLARITY_HOST` | XClarity Administrator hostname/IP |
| `XCLARITY_USER` | Username (default: admin) |
| `XCLARITY_PASSWORD` | Password (stored in Vault) |

### Connection Manager

Create a connection via the Ninko dashboard with:
- **URL**: `https://<xclarity-host>`
- **User**: admin username
- **Password**: admin password

## Routing Keywords

- `xclarity`, `lenovo`, `lenovo xclarity`, `think system`, `thinkblade`, `lenovo server`, `lenovo bmc`

## API Endpoints

- `GET /api/lenovo_xclarity/health` – Health check
- `GET /api/lenovo_xclarity/status` – Server/chassis/storage counts

## Tools

| Tool | Description |
|------|-------------|
| `list_xclarity_servers` | List all servers |
| `get_xclarity_server_details` | Get server details |
| `list_xclarity_chassis` | List chassis |
| `list_xclarity_storage` | List storage |
| `get_xclarity_server_health` | Check health |
| `list_xclarity_events` | List events |
| `get_xclarity_firmware` | Get firmware versions |
| `power_on_xclarity_server` | Power on |
| `power_off_xclarity_server` | Power off |
| `restart_xclarity_server` | Restart |
| `identify_xclarity_server` | Blink LED |