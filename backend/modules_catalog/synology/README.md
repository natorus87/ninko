# Ninko Module: Synology NAS (💾)

This module provides comprehensive management of Synology NAS devices via the DSM Web API.

---

## Features

- **System Information**: Model, serial, DSM version, uptime
- **Storage Management**: Disk status, RAID configuration, volumes
- **Package Management**: List installed packages and their status
- **Service Management**: View and restart services (Active Directory, DNS, DHCP, etc.)
- **Task Scheduling**: View scheduled backup and maintenance tasks

---

## Configuration

### Connection Settings

| Field | Description |
|-------|-------------|
| DSM URL | URL to your Synology DSM (e.g., `https://192.168.1.100:5001`) |
| Username | DSM admin username |
| Password | DSM admin password |
| API Key | Optional: Synology API Key for enhanced security |

### Environment Variables (Fallback)

```bash
SYNOLOGY_URL=https://192.168.1.100:5001
SYNOLOGY_USERNAME=admin
SYNOLOGY_PASSWORD=your_password
SYNOLOGY_API_KEY=optional_api_key
```

---

## Tools

| Tool | Description | Type |
|------|-------------|------|
| `get_synology_system_info` | Retrieve system model, version, uptime | Read |
| `get_synology_storage` | List disks, RAID, volumes | Read |
| `get_synology_packages` | List installed packages | Read |
| `get_synology_services` | List running services | Read |
| `restart_synology_service` | Restart a specific service | Write |
| `get_synology_tasks` | List scheduled tasks | Read |
| `check_synology_updates` | Check for DSM updates | Read |
| `install_synology_update` | Install DSM update (requires confirm=True) | Write |
| `install_synology_package` | Install a package (requires confirm=True) | Write |
| `uninstall_synology_package` | Uninstall a package (requires confirm=True) | Write |
| `get_synology_network_info` | Query network configuration | Read |
| `get_synology_users` | List user accounts | Read |
| `get_synology_groups` | List user groups | Read |
| `create_synology_user` | Create a new user | Write |
| `delete_synology_user` | Delete a user (requires confirm=True) | Write |
| `change_synology_user_password` | Change user password | Write |
| `create_synology_group` | Create a new group | Write |
| `add_user_to_group` | Add user to group | Write |
| `remove_user_from_group` | Remove user from group | Write |
| `shutdown_synologyNAS` | Shutdown the NAS (requires confirm=True) | Write |
| `reboot_synologyNAS` | Reboot the NAS (requires confirm=True) | Write |

---

## Usage Examples

```
User: Zeig mir den Status meiner Synology
→ Calls get_synology_system_info

User: Welche Pakete sind installiert?
→ Calls get_synology_packages

User: Ist der DHCP-Server gestartet?
→ Calls get_synology_services

User: Starte den DNS-Server neu
→ Calls restart_synology_service with service_name="dnsserver"
```

---

## Installation

This module is available in the Ninko Marketplace. Install via:
**Settings → Marketplace → Synology NAS → Installieren**

After installation, create a connection in:
**Settings → Module → Synology → Zahnrad → Neue Verbindung**

---

## API Reference

- DSM 7.x Web API: `http://your-nas:5001/webapi/entry.cgi`
- Authentication: Session-based via `SYNO.API.Auth`
- Required APIs: `SYNO.Core.System`, `SYNO.Core.Storage`, `SYNO.PackageManager`, `SYNO.TaskScheduler`
