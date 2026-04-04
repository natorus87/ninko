# Linux Server Module

Remote Linux administration via SSH.

## Features
- Execute shell commands
- Service operations and journal access
- Filesystem and network diagnostics
- APT update/upgrade/install workflows
- Read files and list directories

## Connection
Configure in **Settings -> Modules -> Linux Server**.

Typical fields:
- `host`
- `port` (default `22`)
- `username`
- `LINUX_SERVER_PASSWORD` or `LINUX_SERVER_SSH_KEY`

## Main Tools
- `run_command`
- `get_system_info`, `get_disk_usage`, `get_top_processes`
- `list_services`, `service_action`, `get_journal`
- `apt_update`, `apt_upgrade`, `apt_install`
- `read_file`, `list_directory`
- `get_network_info`, `check_port`, `list_users`, `check_last_logins`

## Safety
- `reboot_server` and package changes are state-changing operations and should stay guarded.
