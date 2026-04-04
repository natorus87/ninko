# Home Assistant Module

Control and query Home Assistant entities through the REST API.

## Features
- Read entity states
- Call HA services for specific entities
- List and search entities
- Inspect device/entity details

## Connection
Configure in **Settings -> Modules -> Home Assistant**.

Required:
- `url` (e.g. `https://ha.local:8123`)
- `HOMEASSISTANT_API_TOKEN`

## Main Tools
- `ha_get_entity_state`
- `ha_call_service`
- `ha_list_entities`
- `ha_find_device`
- `ha_get_entity_details`

## Notes
- Use least-privilege HA tokens.
- Prefer explicit entity IDs (`light.kitchen`, `switch.server_rack`) for reliable actions.
