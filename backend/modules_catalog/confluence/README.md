# Confluence Module

Atlassian Confluence Wiki – Spaces, Pages, Blog Posts, Labels und Suche.

## Features

- List and search spaces
- Get page content and metadata
- Create and update pages
- Blog posts
- Labels and attachments

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `CONFLUENCE_URL` | Confluence Cloud URL |
| `CONFLUENCE_USER` | Email or username |
| `CONFLUENCE_API_KEY` | API token (stored in Vault) |

## Routing Keywords

- `confluence`, `wiki`, `dokumentation`, `atlassian`

## Tools

| Tool | Description |
|------|-------------|
| `get_confluence_spaces` | List spaces |
| `get_confluence_space` | Get space details |
| `get_confluence_page` | Get page content |
| `search_confluence` | Search pages |
| `create_confluence_page` | Create page |
| `update_confluence_page` | Update page |
