# GitHub Module

GitHub – Repositories, Actions, Pull Requests, Issues and Releases.

## Features

- Get user status and rate limits
- List/create/manage repositories
- Create, trigger, cancel, re-run GitHub Actions workflows
- List and monitor workflow runs and jobs
- View job logs
- List/create/merge pull requests
- List/create issues
- List branches and commits
- List tags and releases
- Manage repository variables and secrets
- Code and issue search

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `GITHUB_TOKEN` | GitHub Personal Access Token |

### Connection Manager

Create a connection via the Ninko dashboard with:
- **Token**: GitHub Personal Access Token (requires `repo` and `workflow` scopes)

## Routing Keywords

`github`, `repository`, `repo`, `actions`, `workflow`, `pull request`, `issue`