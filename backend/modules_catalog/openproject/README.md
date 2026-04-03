# OpenProject Module

OpenProject Enterprise – Project Management, Tasks, Time Tracking via OpenProject API.

## Features

- List and search projects
- List work packages (tasks, bugs)
- Create and update work packages
- List and manage users
- Log time entries
- View project details

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENPROJECT_HOST` | OpenProject URL |
| `OPENPROJECT_API_KEY` | API Key (stored in Vault) |

### Connection Manager

Create a connection via the Ninko dashboard with:
- **URL**: OpenProject URL
- **API Key**: Your API key

## Routing Keywords

- `openproject`, `open project`, `projektmanagement`, `project management`, `task management`, `ticket`

## API Endpoints

- `GET /api/openproject/health` – Health check
- `GET /api/openproject/status` – Projects/tasks/users counts

## Tools

| Tool | Description |
|------|-------------|
| `list_openproject_projects` | List all projects |
| `get_openproject_project` | Get project details |
| `list_openproject_work_packages` | List work packages |
| `get_openproject_work_package` | Get task details |
| `list_openproject_users` | List users |
| `list_openproject_time_entries` | List time entries |
| `create_openproject_work_package` | Create task |
| `update_openproject_work_package` | Update task |
| `log_openproject_time` | Log time |