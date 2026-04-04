# Zabbix Module

Zabbix Enterprise Monitoring – Hosts, Items, Triggers, Graphs and Alerts.

## Features

- Get server status and version
- List/create/delete hosts
- List monitoring items and triggers
- View current problems and alerts
- List graphs and templates
- Get historical data
- Create and delete hosts

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ZABBIX_URL` | Zabbix API URL (e.g., `http://zabbix.local/zabbix/api_jsonrpc.php`) |
| `ZABBIX_USER` | Zabbix username |
| `ZABBIX_PASSWORD` | Zabbix password |

### Connection Manager

Create a connection via the Ninko dashboard with:
- **URL**: Zabbix API URL
- **User**: Zabbix username
- **Password**: Zabbix password

## Routing Keywords

`zabbix`, `monitoring`, `host`, `item`, `trigger`, `alert`, `graph`