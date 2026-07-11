# Changelog

All notable changes to this module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.7] - 2026-07-11

### Security
- `/pair <code>` no longer allows unauthorized users to approve pairing codes
  (self-approval defeated the entire pairing flow). In-Telegram approval now
  requires an already authorized user; dashboard approval is unchanged.
- Unauthorized group messages are now ignored when no `allowed_chat_ids`
  allowlist is configured. Previously any group member could issue commands as
  soon as the bot was in the group.

### Fixed
- Tool-level safeguard confirmation (`confirm_tool_yes`) no longer crashes with
  a `NameError` when the conversation was compacted during resume.
- Network errors from httpx (ConnectError, ConnectTimeout, etc.) no longer kill
  the polling loop permanently — they inherit from neither `OSError` nor
  `asyncio.TimeoutError` and previously escaped every error handler (new shared
  `_RECOVERABLE_ERRORS` tuple, also used by send/photo/voice paths, health
  check, and status route).
- `/clear` no longer suppresses history persistence of the next message: the
  cleared-session flag is only set while a request is actually in flight.

### Changed
- All Telegram API calls share one persistent `httpx.AsyncClient` (created
  lazily, closed on `stop()`) instead of opening a new TLS connection per call
  — noticeable during streaming previews and typing indicators.
- Connection config is fetched once per update instead of up to three times.
- `/pairing/pending` uses Redis `SCAN` instead of blocking `KEYS`.
- Marketplace catalog version aligned with the module version (was stale at
  1.2.4).

## [1.2.6] - 2026-07-05

### Added
- Telegram command menu now includes `/help`, `/status`, and `/pair` in addition to
  `/start`, `/clear`, `/reset`, and `/chatid`.
- `/help` shows available commands and practical example prompts.
- `/status` shows bot/session status, chat/user IDs, authorization mode, streaming, and
  voice-reply state.

### Fixed
- Telegram streaming previews are enabled again when `streaming=true` is configured.
  Preview edits now filter agent planning/retry meta text before it can be displayed.
- Streaming route results now propagate `route_meta`, fixing compaction metadata handling
  for streamed Telegram replies.

## [1.2.5] - 2026-07-05

### Fixed
- Telegram text replies are final-only: live token/status preview is ignored even when the
  connection still has `streaming=true`, so users no longer receive intermediate reasoning
  or retry-plan updates.
- Final Telegram responses strip leaked agent planning/retry meta text such as repeated
  "I will call..." steps and "consecutive tool errors" diagnostics before formatting.

## [1.1.1] - 2026-04-06

### Added
- Initial release of Telegram Bot module
- Passive access to Ninko via Telegram Messenger
- Background polling loop (no webhook required)
- Persistent chat memory tied to Telegram user ID (Redis)
- Native commands: /start, /clear, /reset for chat history management
- Bot token authentication via Vault
- Support for voice message transcription
- Dashboard integration with SVG icon

## [1.1.3] - 2026-04-13

### Fixed
- `/chatid` command now works even when allowlist or pairing restrictions are active

## [1.2.0] - 2026-05-08

### Changed
- Telegram-Agent ist nun ein **transparenter Transport-Kanal**, kein
  inhaltlicher Agent mehr. Frühere Antworten wie „Ich bin nur ein
  Telegram-Bot, frag den Haupt-Agenten" entfallen.
- System-Prompt komplett überarbeitet (DE/EN), inkl. Source-Detection
  (`[Telegram Chat-ID:` Präfix → keinen Doppel-Send auslösen).

### Added
- Neues Tool `delegate_to_orchestrator(question)` — leitet beliebige
  Inhaltsfragen an den Haupt-Orchestrator weiter (`READONLY` im
  `tool_registry`).
- Source-aware Suppression in `bot.py`: nur reine Send-Confirmation-
  Antworten werden unterdrückt, delegierte Inhalte werden normal
  zugestellt.

### Removed
- Generische `routing_keywords` (`telegram`, `messenger`, `benachrichtige`)
  entfernt, die das Tier-2-Routing in Status- und Inhaltsfragen
  fehlleiteten.

## [1.2.2] - 2026-05-18

### Fixed
- Telegram-Streaming startet die Preview jetzt vor dem Orchestrator-Lauf und
  aktualisiert sie live über Token-Callbacks und Status-Bus-Events.
- Markdown-Tabellen werden für Telegram-HTML bereinigt, damit Inline-Markdown
  nicht in `<pre>`-Tabellen sichtbar bleibt.
- Testnachrichten nutzen denselben Telegram-HTML-Formatter wie der Bot.

## [1.2.3] - 2026-05-18

### Fixed
- Telegram-Live-Preview entfernt Markdown-Marker vor dem finalen HTML-Edit,
  damit Proxmox- und andere Markdown-Antworten während Streaming nicht roh
  angezeigt werden.
- Tabellen-Erkennung akzeptiert auch eingerückte Markdown-Tabellen.
- Marketplace-Katalogversion auf die aktuelle Telegram-Modulversion angehoben.

## [1.2.4] - 2026-05-23

### Fixed
- Inline-Button-Bestätigungen konsumieren ausstehende SafeGuard-Aktionen jetzt
  atomar und erzeugen bei Mehrfachklicks keine falschen „Keine ausstehende
  Aktion“-Antworten mehr.
- Telegram bestätigt Tool-Level-SafeGuard-Unterbrechungen nun mit einem zweiten
  Button-Dialog, statt nach der ersten Bestätigung in einen generischen
  Ausführungsfehler zu laufen.
- Textbasierte Bestätigungen (`ja`) werden beim Re-Routing wieder als
  bestätigte Ausführung weitergegeben.

## Module Information

- **Name**: telegram
- **Description**: Ermöglicht das Chatten mit dem Ninko Orchestrator über Telegram
- **Author**: Ninko Team
