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

## Module Information

- **Name**: telegram
- **Description**: Ermöglicht das Chatten mit dem Ninko Orchestrator über Telegram
- **Author**: Ninko Team
