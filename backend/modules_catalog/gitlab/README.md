# GitLab Module

GitLab CI/CD – Repositories, Pipelines, Jobs, Merge Requests and Releases.

## Features

- Get server status and version
- List/create/manage projects
- Create, trigger, cancel, retry pipelines
- List and monitor pipeline jobs
- View job logs/traces
- List/create/accept merge requests
- List branches and commits
- List/create tags and releases
- Manage CI/CD variables
- Create and trigger pipeline schedules

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `GITLAB_URL` | GitLab URL (e.g., `https://gitlab.com`) |
| `GITLAB_TOKEN` | GitLab API Token |

### Connection Manager

Create a connection via the Ninko dashboard with:
- **URL**: GitLab instance URL
- **Token**: GitLab API Token (requires `api` scope)

## Routing Keywords

`gitlab`, `ci`, `cd`, `pipeline`, `merge request`, `repository`, `commit`