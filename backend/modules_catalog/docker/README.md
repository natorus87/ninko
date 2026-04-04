# Docker Module

Manage Docker hosts through the Docker Engine API.

## Features
- List/inspect/start/stop/restart/remove containers
- Read container logs and runtime stats
- Manage images (list/pull/remove)
- Manage volumes (list/remove)
- System info, version, and disk usage

## Connection
Configure in **Settings -> Modules -> Docker**.

Typical fields:
- `host`
- `port` (default `2375` / `2376` with TLS)
- optional TLS config

## Main Tools
- `list_containers`, `inspect_container`
- `start_container`, `stop_container`, `restart_container`, `remove_container`
- `get_container_logs`, `get_container_stats`
- `list_images`, `pull_image`, `remove_image`
- `list_volumes`, `remove_volume`
- `get_docker_info`, `get_docker_version`, `get_docker_disk_usage`

## Safety
- Destructive actions (remove) should remain protected by Safeguard confirmation.
