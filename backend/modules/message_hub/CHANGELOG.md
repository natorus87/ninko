# Changelog

All notable changes to this module will be documented in this file.

## [1.0.1] - 2026-05-18

### Fixed
- Telegram replies from the Message Hub worker are sent as plain text instead
  of fragile Telegram Markdown, avoiding parse failures for generated tables
  and code snippets.

## [1.0.0] - 2026-05-11

### Added
- Initial Message Hub module for bidirectional channel routing.
