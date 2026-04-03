# Jira Module

Atlassian Jira Issue Tracking – Issues, Projekte, Sprints, Boards und Workflows.

## Features

- List and search issues
- Get issue details
- Create and update issues
- Manage sprints and boards
- Workflow transitions

## Configuration

Create a connection via the Ninko dashboard with:
- **URL**: Jira Cloud URL
- **User**: Email address
- **API Token**: Jira API token (stored in Vault)

## Routing Keywords

- `jira`, `ticket`, `issue`, `atlassian`, `sprint`, `backlog`

## Tools

| Tool | Description |
|------|-------------|
| `get_jira_projects` | List projects |
| `get_jira_issues` | List issues |
| `get_jira_issue` | Get issue details |
| `create_jira_issue` | Create issue |
| `update_jira_issue` | Update issue |
| `search_jira_issues` | Search issues |
| `get_jira_sprints` | Get sprints |
| `get_jira_boards` | Get boards |