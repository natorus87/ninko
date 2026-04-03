# Redmine Module

Redmine Projektmanagement – Tickets, Projekte, Benutzer, Time Entries und Workflows.

## Features

- List and search issues
- Get issue details
- Create and update issues
- Time tracking
- User and group management
- Project management

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `REDMINE_URL` | Redmine instance URL |
| `REDMINE_API_KEY` | API key (stored in Vault) |

## Routing Keywords

- `redmine`, `ticket`, `issue`, `projekt`, `time tracking`

## Tools

| Tool | Description |
|------|-------------|
| `get_redmine_projects` | List projects |
| `get_redmine_issues` | List issues |
| `get_redmine_issue` | Get issue details |
| `create_redmine_issue` | Create issue |
| `update_redmine_issue` | Update issue |
| `get_redmine_users` | List users |
| `get_redmine_time_entries` | Time entries |
| `log_redmine_time` | Log time |