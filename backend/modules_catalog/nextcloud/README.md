# Nextcloud Module

Nextcloud File Sync and Share – Files, Folders, Shares, Users via WebDAV and OCS API.

## Features

- List and search files
- Create folders
- Upload and delete files
- Create shares (link, user, group)
- List and manage users
- View storage usage

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `NEXTCLOUD_HOST` | Nextcloud URL |
| `NEXTCLOUD_USER` | Username |
| `NEXTCLOUD_PASSWORD` | Password (stored in Vault) |

### Connection Manager

Create a connection via the Ninko dashboard with:
- **URL**: Nextcloud URL
- **User**: Username
- **Password**: Password

## Routing Keywords

- `nextcloud`, `next cloud`, `fileshare`, `file share`, `owncloud`, `cloud storage`

## API Endpoints

- `GET /api/nextcloud/health` – Health check
- `GET /api/nextcloud/status` – Users/shares/storage stats

## Tools

| Tool | Description |
|------|-------------|
| `list_nextcloud_files` | List files in folder |
| `search_nextcloud_files` | Search files |
| `list_nextcloud_users` | List users |
| `get_nextcloud_user` | Get user details |
| `list_nextcloud_shares` | List shares |
| `get_nextcloud_storage` | Get storage usage |
| `create_nextcloud_folder` | Create folder |
| `upload_nextcloud_file` | Upload file |
| `delete_nextcloud_file` | Delete file |
| `create_nextcloud_share` | Create share |
| `create_nextcloud_user` | Create user |