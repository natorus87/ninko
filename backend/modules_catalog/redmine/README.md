# Redmine Module

Redmine Projektmanagement – Tickets, Projekte, Benutzer, Time Entries und Workflows.

## Features

- List and search issues
- Get issue details
- Create and update issues
- Time tracking
- User and group management
- Project management
- AlphaNodes HRM API (read/write endpoints)
- AlphaNodes Reporting API (read/write endpoints)

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `REDMINE_URL` | Redmine instance URL |
| `REDMINE_API_KEY` | API key (stored in Vault) |
| `REDMINE_HRM_API_PREFIX` | Prefix for HRM plugin API endpoints (default: `hrm`) |
| `REDMINE_REPORTING_API_PREFIX` | Prefix for Reporting plugin API endpoints (default: `reporting`) |

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
| `call_redmine_hrm_api` | Read/write AlphaNodes HRM API endpoints |
| `call_redmine_reporting_api` | Read/write AlphaNodes Reporting API endpoints |
| `get_redmine_hrm_attendances` | GET `/hrm/attendances.json` with filters |
| `create_redmine_hrm_attendance` | POST `/hrm/attendances.json` |
| `get_redmine_hrm_attendance` | GET `/hrm/attendances/{id}.json` |
| `get_redmine_hrm_user_capacity` | GET `/hrm/users/{user_id}/capacity.json` |
| `get_redmine_hrm_holidays` | GET `/hrm/holidays.json` |
| `get_redmine_reporting_budgets` | GET `/reporting/budgets.json` |
| `get_redmine_project_budgets` | GET `/projects/{project_id}/budgets.json` |
| `get_redmine_reporting_time_logs` | GET `/reporting/time_logs.json` |

## AlphaNodes Endpoints

- HRM:
  - `GET /hrm/attendances.json`
  - `POST /hrm/attendances.json`
  - `GET /hrm/attendances/{id}.json`
  - `GET /hrm/users/{user_id}/capacity.json`
  - `GET /hrm/holidays.json`
- Reporting:
  - `GET /reporting/budgets.json`
  - `GET /projects/{project_id}/budgets.json`
  - `GET /reporting/time_logs.json`

## Common Filters

- `from`, `to` (YYYY-MM-DD)
- `user_id`
- `limit`, `offset`
