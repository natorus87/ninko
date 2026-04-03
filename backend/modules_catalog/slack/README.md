# Slack Module

Slack Team Communication – Channels, Messages, Users, and Notifications via Slack API.

## Features

- List channels (public and private)
- List users
- Read channel message history
- Search messages
- Send messages to channels
- Send direct messages
- Upload files
- Create channels
- Invite users to channels

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `SLACK_BOT_TOKEN` | Slack Bot User OAuth Token (starts with `xoxb-`) |

### Connection Manager

Create a connection via the Ninko dashboard with:
- **Token**: Bot User OAuth Token

## RequiredScopes

The Slack app needs these scopes:
- `channels:read`
- `channels:write`
- `chat:write`
- `users:read`
- `files:write`
- `groups:read`
- `search:read`

## Routing Keywords

- `slack`, `slack channel`, `slack nachricht`, `slack bot`, `slack webhook`, `slack notification`

## API Endpoints

- `GET /api/slack/health` – Health check
- `GET /api/slack/status` – Workspace status

## Tools

| Tool | Description |
|------|-------------|
| `list_slack_channels` | List all channels |
| `list_slack_users` | List all users |
| `get_slack_channel_history` | Get channel messages |
| `search_slack_messages` | Search messages |
| `send_slack_message` | Send message to channel |
| `send_slack_dm` | Send direct message |
| `upload_slack_file` | Upload file |
| `create_slack_channel` | Create channel |
| `invite_user_to_channel` | Invite user |