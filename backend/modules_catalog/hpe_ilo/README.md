# HPE iLO Module

HPE Integrated Lights-Out (iLO4/iLO5) Server Management via REST API.

## Features

- iLO firmware version, license, and manager info
- Server model, serial number, power state, health
- Thermal sensors and fan speeds
- Power supply status
- Network configuration (IP, MAC)
- Event log
- Power on/off control
- iLO reset
- Boot button press (BIOS/EFI)

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ILO_HOST` | iLO hostname or IP | - |
| `ILO_USER` | iLO username | `Administrator` |
| `ILO_PASSWORD` | iLO password (stored in Vault) | - |

### Connection Manager

Create a connection via the Ninko dashboard with:
- **URL**: `https://<ilo-host>` or just `<ilo-host>`
- **User**: iLO username
- **Password**: iLO password

## Routing Keywords

- `ilo`, `hpe`, `hpe ilo`, `integrated lights out`
- `server-management`, `bmc`, `ipmi`

## API Endpoints

- `GET /api/hpe_ilo/health` – Health check
- `GET /api/hpe_ilo/status` – iLO + server status

## Tools

| Tool | Description |
|------|-------------|
| `get_ilo_info` | Read iLO firmware version, license |
| `get_server_info` | Read server model, serial, power, health |
| `get_server_thermal` | Read thermal sensors |
| `get_server_power` | Read power supplies |
| `get_ilo_nics` | Read network config |
| `get_ilo_eventlog` | Read event log |
| `server_power_on` | Power on server |
| `server_power_off` | Power off server |
| `server_reset_ilo` | Reset iLO |
| `server_press_boot_button` | Press boot button |