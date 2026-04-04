# Discord Module

Discord Server Management – Guilds, Channels, Members, and Messages via Discord API.

## Features

- Get guild (server) information
- List channels (text, voice, categories)
- List members
- Read channel message history
- Search messages
- Send messages to channels
- Create text/voice channels
- Delete channels

## Configuration

### Environment Variables

| Variable | Description |
|----------|-------------|
| `DISCORD_BOT_TOKEN` | Discord Bot Token |
| `DISCORD_GUILD_ID` | Discord Server ID |

### Connection Manager

Create a connection via the Ninko dashboard with:
- **Bot Token**: Discord Bot Token
- **Guild ID**: Server ID

## Required Scopes

Your bot needs these intents:
- `GUILD_MEMBERS` - Read members
- `GUILD_MESSAGES` - Read/send messages
- `GUILDS` - Read guild info

## Routing Keywords

`discord`, `server`, `guild`, `channel`, `textkanal`