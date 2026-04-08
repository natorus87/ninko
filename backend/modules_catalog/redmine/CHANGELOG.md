# Changelog

All notable changes to this module will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-04-08

### Added
- User Administration Tools (13 new tools):
  - `create_redmine_user` - Create new users with admin flag
  - `get_redmine_user_details` - Get user details with groups/memberships
  - `update_redmine_user` - Update user info, email, admin status
  - `delete_redmine_user` - Permanently delete users
  - `lock_redmine_user` / `unlock_redmine_user` - Deactivate/activate users
  - `reset_redmine_user_password` - Password reset functionality
  - `add_redmine_user_to_group` / `remove_redmine_user_from_group` - Group membership
  - `get_redmine_groups` / `create_redmine_group` / `delete_redmine_group` - Group management
- Full CRUD operations for user and group administration
- Status management (active/locked) for user lifecycle
- Multi-language support for all new tools (DE, EN, FR, ES, IT, NL, PL, PT, JA, ZH)

### Changed
- Updated module version from 1.0.9 to 1.1.0
- Extended agent system prompt with user administration capabilities
- Updated README.md with comprehensive tool documentation

## [1.0.0] - 2026-04-06

### Added
- Initial release of Redmine module
- Redmine project management integration
- Ticket management
- Project management
- User management
- Time entry tracking
- Workflow management
- HRM (Human Resource Management) support
- Resource planning
- Attendance tracking
- Leave management
- Reporting capabilities
- Dashboard integration with emoji icon

## Module Information

- **Name**: redmine
- **Description**: Redmine Projektmanagement – Tickets, Projekte, Benutzer, Time Entries und Workflows
- **Author**: Ninko Team
