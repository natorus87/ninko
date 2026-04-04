# Microsoft Teams Module

Connect Ninko to Microsoft Teams for chat-based operations.

## Features
- Send messages from Ninko to Teams
- Receive Teams messages and route them to orchestrator
- Optional voice attachment processing/transcription flow

## Connection
Configure in **Settings -> Modules -> Teams**.

Typical fields:
- `MICROSOFT_APP_ID`
- `MICROSOFT_APP_PASSWORD`
- Bot endpoint/webhook config according to deployment

## Main Tools
- `send_teams_message`

## Notes
- Ensure the bot endpoint is reachable from Microsoft cloud endpoints.
- Validate tenant/app permissions before production rollout.
