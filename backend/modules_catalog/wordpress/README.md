# WordPress Module

Operate WordPress instances via WP REST API.

## Features
- Site info and update visibility
- Plugin lifecycle (search/install/activate/deactivate/update/delete)
- Page and post CRUD
- Categories, tags, users, media, and settings

## Connection
Configure in **Settings -> Modules -> WordPress**.

Typical fields:
- `base_url` (WordPress URL)
- `username`
- `WORDPRESS_APP_PASSWORD`

## Main Tool Areas
- Site: `get_site_info`, `get_updates_info`
- Plugins: `list_plugins`, `search_plugins`, `install_plugin`, `activate_plugin`, `deactivate_plugin`, `update_plugin`, `delete_plugin`
- Pages/Posts: `list_*`, `get_*`, `create_*`, `update_*`, `delete_*`
- Taxonomy: `list_categories`, `create_category`, `list_tags`, `create_tag`
- Users/Settings/Media: `list_users`, `get_current_user`, `get_site_settings`, `update_site_settings`, `list_media`

## Safety
- Deletion operations and forced content actions should require explicit confirmation.
