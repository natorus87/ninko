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

### Issue Management

| Tool | Description |
|------|-------------|
| `get_redmine_projects` | List projects |
| `get_redmine_issues` | List issues |
| `get_redmine_issue` | Get issue details |
| `create_redmine_issue` | Create issue |
| `update_redmine_issue` | Update issue |
| `get_redmine_issue_statuses` | List issue statuses |
| `get_redmine_priorities` | List issue priorities |
| `search_redmine_issues` | Search issues by text |
| `get_redmine_issue_counts` | Count issues by status |

### Time Tracking

| Tool | Description |
|------|-------------|
| `get_redmine_time_entries` | Time entries |
| `get_redmine_user_hours_report` | Hours report for user (paginated) |
| `log_redmine_time` | Log time |
| `get_redmine_time_entry_activities` | List time entry activities |

### User & Group Administration

| Tool | Description |
|------|-------------|
| `get_redmine_users` | List all users |
| `get_redmine_user_details` | Get user details with groups/memberships |
| `create_redmine_user` | Create new user (with optional admin flag) |
| `update_redmine_user` | Update user info, email, admin status |
| `delete_redmine_user` | Permanently delete user |
| `lock_redmine_user` | Deactivate/lock user (status=3) |
| `unlock_redmine_user` | Reactivate/unlock user (status=1) |
| `reset_redmine_user_password` | Reset user password |
| `get_redmine_groups` | List all groups |
| `create_redmine_group` | Create new group |
| `delete_redmine_group` | Delete group |
| `add_redmine_user_to_group` | Add user to group |
| `remove_redmine_user_from_group` | Remove user from group |

### HRM (AlphaNodes Plugin)

| Tool | Description |
|------|-------------|
| `call_redmine_hrm_api` | Read/write AlphaNodes HRM API endpoints |
| `get_redmine_hrm_attendances` | GET `/hrm/attendances.json` with filters |
| `create_redmine_hrm_attendance` | POST `/hrm/attendances.json` |
| `update_redmine_hrm_attendance` | PUT `/hrm/attendances/{id}.json` |
| `delete_redmine_hrm_attendance` | DELETE `/hrm/attendances/{id}.json` |
| `get_redmine_hrm_attendance` | GET `/hrm/attendances/{id}.json` |
| `get_redmine_hrm_user_capacity` | GET `/hrm/users/{user_id}/capacity.json` |
| `get_redmine_hrm_holidays` | GET `/hrm/holidays.json` |
| `get_redmine_hrm_attendance_types` | GET `/hrm/attendance_types.json` |
| `get_redmine_hrm_user_report` | Comprehensive HRM monthly report |
| `create_redmine_hrm_vacation` | Create vacation entry |
| `create_redmine_hrm_sick_leave` | Create sick leave entry |

### Reporting (AlphaNodes Plugin)

| Tool | Description |
|------|-------------|
| `call_redmine_reporting_api` | Read/write AlphaNodes Reporting API endpoints |
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
