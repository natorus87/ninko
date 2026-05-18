# Changelog

All notable changes to this module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

## Module Information

- **Name**: telegram
- **Description**: Ermöglicht das Chatten mit dem Ninko Orchestrator über Telegram
- **Author**: Ninko Team
