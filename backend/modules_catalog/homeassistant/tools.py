import json
import logging
import os
from typing import Dict, Any
import httpx
from langchain_core.tools import tool

from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.homeassistant.tools")

async def _get_api_client(connection_id: str = "") -> Dict[str, Any]:
    """
    Loads configuration and secrets from ConnectionManager or env vars for Home Assistant.
    """
    conn_data = await ConnectionManager.get_connection("homeassistant", connection_id)
    if not conn_data:
        conn_data = await ConnectionManager.get_default_connection("homeassistant")

    if conn_data:
        base_url = conn_data.config.get("url", conn_data.config.get("HOMEASSISTANT_URL", "http://homeassistant.local:8123"))
        if base_url.endswith("/"):
            base_url = base_url[:-1]
        vault = get_vault()
        api_token_path = conn_data.vault_keys.get("HOMEASSISTANT_API_TOKEN")
        api_token = await vault.get_secret(api_token_path) if api_token_path else ""
    else:
        # Fallback: env var (for k8s / docker-compose without UI configuration)
        base_url = os.getenv("HOMEASSISTANT_URL", "http://homeassistant.local:8123").rstrip("/")
        api_token = os.getenv("HOMEASSISTANT_API_TOKEN", "")

    if not api_token:
        raise ValueError(
            "Home Assistant API token is missing. "
            "Please create a connection in settings or set HOMEASSISTANT_API_TOKEN."
        )

    return {
        "base_url": base_url,
        "headers": {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }
    }

@tool
async def ha_get_entity_state(entity_id: str, connection_id: str = "") -> str:
    """
    Reads the current state of an entity from Home Assistant (e.g. light.living_room, sensor.temperature).
    Use this tool to check if a light is on/off, what the temperature is, or to query any sensor values from the smart home.

    Args:
        entity_id: The full Home Assistant entity ID (e.g. 'light.wohnzimmer', 'switch.steckdose_tv')
        connection_id: The ID of the connection to use (optional)
    """
    try:
        client_config = await _get_api_client(connection_id)
        url = f"{client_config['base_url']}/api/states/{entity_id}"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=client_config["headers"], timeout=10.0)
            response.raise_for_status()
            data = response.json()

            state = data.get("state")
            attributes = data.get("attributes", {})
            friendly_name = attributes.get("friendly_name", entity_id)

            return f"Entity '{friendly_name}' ({entity_id}) currently has state '{state}'."
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Entity '{entity_id}' was not found."
        logger.error("HTTP error in ha_get_entity_state: %s", e)
        return f"Error communicating with Home Assistant: {e}"
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.error("Error in ha_get_entity_state: %s", e)
        return f"An unexpected error occurred: {e}"

@tool
async def ha_call_service(service_name: str, entity_id: str, service_data_json: str = "", connection_id: str = "") -> str:
    """
    Calls a service in Home Assistant to control a device.
    Supports arbitrary additional parameters via service_data_json (as JSON string).

    Examples:
    - Turn on light: service_name='light.turn_on', entity_id='light.wohnzimmer'
    - Light with brightness: service_name='light.turn_on', entity_id='light.wohnzimmer', service_data_json='{"brightness_pct": 80}'
    - Heating to 22°C: service_name='climate.set_temperature', entity_id='climate.office', service_data_json='{"temperature": 22}'
    - Heating mode: service_name='climate.set_hvac_mode', entity_id='climate.office', service_data_json='{"hvac_mode": "heat"}'
    - Switch: service_name='switch.turn_off', entity_id='switch.steckdose'

    Args:
        service_name: The service to call in 'domain.service' format (e.g. 'light.turn_on', 'climate.set_temperature')
        entity_id: The full entity ID (e.g. 'light.wohnzimmer', 'climate.office'). 'all' for all entities.
        service_data_json: Optional additional parameters as JSON string (e.g. '{"temperature": 22}' or '{"brightness_pct": 80}')
        connection_id: The ID of the connection to use (optional)
    """
    try:
        if "." not in service_name:
            return "Error: service_name must be in 'domain.service' format (e.g. 'light.turn_on')."

        domain, service = service_name.split(".", 1)
        client_config = await _get_api_client(connection_id)
        url = f"{client_config['base_url']}/api/services/{domain}/{service}"

        payload: Dict[str, Any] = {"entity_id": entity_id} if entity_id and entity_id != 'all' else {}

        if service_data_json:
            try:
                extra = json.loads(service_data_json)
                if isinstance(extra, dict):
                    payload.update(extra)
                else:
                    return "Error: service_data_json must be a JSON object (e.g. {\"temperature\": 22})."
            except json.JSONDecodeError as e:
                return f"Error: service_data_json is not valid JSON: {e}"

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=client_config["headers"], json=payload, timeout=10.0)
            response.raise_for_status()

            extra_info = f" mit Parametern {service_data_json}" if service_data_json else ""
            return f"Service '{service_name}' was called successfully for '{entity_id}'{extra_info}."
    except httpx.HTTPError as e:
        logger.error("HTTP error in ha_call_service: %s", e)
        return f"Error communicating with Home Assistant API: {e}"
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.error("Error in ha_call_service: %s", e)
        return f"An unexpected error occurred: {e}"

@tool
async def ha_list_entities(domain_filter: str = "", name_search: str = "", connection_id: str = "") -> str:
    """
    Lists entities in Home Assistant. Supports search by domain and/or name.
    Useful for finding unknown entity IDs before calling a service.

    Examples:
    - All heaters: domain_filter='climate'
    - All lights in living room: domain_filter='light', name_search='wohnzimmer'
    - Search for "office": name_search='büro'
    - All entities: (leave both parameters empty)

    Args:
        domain_filter: Optional filter for a domain (e.g. 'light', 'switch', 'climate', 'sensor', 'binary_sensor'). Empty = all domains.
        name_search: Optional full-text search in display name or entity ID (case-insensitive). Empty = no name filter.
        connection_id: The ID of the connection to use (optional)
    """
    try:
        client_config = await _get_api_client(connection_id)
        url = f"{client_config['base_url']}/api/states"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=client_config["headers"], timeout=10.0)
            response.raise_for_status()

            data = response.json()
            entities = []
            search_lower = name_search.lower() if name_search else ""

            for item in data:
                e_id = item.get("entity_id", "")
                attrs = item.get("attributes", {})
                friendly_name = attrs.get("friendly_name", "")
                state = item.get("state", "")

                if domain_filter and not e_id.startswith(f"{domain_filter}."):
                    continue

                if search_lower and search_lower not in friendly_name.lower() and search_lower not in e_id.lower():
                    continue

                # For climate entities: show target temperature
                extra = ""
                if e_id.startswith("climate."):
                    current_temp = attrs.get("current_temperature")
                    target_temp = attrs.get("temperature")
                    hvac_mode = attrs.get("hvac_mode", state)
                    if current_temp is not None or target_temp is not None:
                        extra = f" | Current: {current_temp}°C, Target: {target_temp}°C, Mode: {hvac_mode}"

                entities.append(f"- {friendly_name} ({e_id}): {state}{extra}")

            if not entities:
                msg = "No entities found"
                if domain_filter:
                    msg += f" for domain '{domain_filter}'"
                if name_search:
                    msg += f" with name '{name_search}'"
                return msg + "."

            header = f"Found entities ({len(entities)}):"
            if len(entities) > 60:
                header = f"Found {len(entities)} entities. Showing the first 60 — use name_search or domain_filter to narrow down:"
                return header + "\n" + "\n".join(entities[:60])

            return header + "\n" + "\n".join(entities)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.error("Error in ha_list_entities: %s", e)
        return f"Error listing entities: {e}"


@tool
async def ha_find_device(search: str, connection_id: str = "") -> str:
    """
    Searches the Home Assistant device registry for a device by name
    and returns all associated entities.

    Unlike 'ha_list_entities', this tool searches real device names
    (e.g. "Thermostat Office", "Shelly Plug Kitchen"), not just entity_ids or friendly_names.
    It also shows rooms/areas.

    Use this tool when the user mentions a device by name and you don't know the entity_id.

    Args:
        search: Search term (substring, case-insensitive), e.g. 'office', 'thermostat', 'shelly'
        connection_id: The ID of the connection to use (optional)
    """
    try:
        client_config = await _get_api_client(connection_id)
        base_url = client_config["base_url"]
        headers = client_config["headers"]
        search_lower = search.lower()

        async with httpx.AsyncClient() as client:
            # Load device registry
            dev_resp = await client.get(
                f"{base_url}/api/config/device_registry/list",
                headers=headers, timeout=10.0
            )
            dev_resp.raise_for_status()
            devices: list = dev_resp.json()

            # Load entity registry (contains device_id mapping)
            ent_resp = await client.get(
                f"{base_url}/api/config/entity_registry/list",
                headers=headers, timeout=10.0
            )
            ent_resp.raise_for_status()
            entity_registry: list = ent_resp.json()

            # Load area registry (optional — ignore if unavailable)
            areas: Dict[str, str] = {}
            try:
                area_resp = await client.get(
                    f"{base_url}/api/config/area_registry/list",
                    headers=headers, timeout=10.0
                )
                if area_resp.status_code == 200:
                    for a in area_resp.json():
                        areas[a.get("area_id", "")] = a.get("name", "")
            except (RuntimeError, ValueError, TypeError, KeyError, OSError):
                pass

            # Load current state of all entities (for state display)
            states_resp = await client.get(f"{base_url}/api/states", headers=headers, timeout=15.0)
            states_resp.raise_for_status()
            states_by_id: Dict[str, Any] = {s["entity_id"]: s for s in states_resp.json()}

        # Filter devices by search term
        def _device_name(dev: Dict) -> str:
            return (dev.get("name_by_user") or dev.get("name") or "").strip()

        matching_devices = [
            d for d in devices
            if search_lower in _device_name(d).lower()
            or search_lower in (d.get("model") or "").lower()
            or search_lower in (d.get("manufacturer") or "").lower()
        ]

        if not matching_devices:
            return f"No device found for term '{search}'. Tip: Try 'ha_list_entities' with name_search='{search}'."

        # Group entities by device
        entities_by_device: Dict[str, list] = {}
        for ent in entity_registry:
            dev_id = ent.get("device_id")
            if dev_id:
                entities_by_device.setdefault(dev_id, []).append(ent)

        lines = []
        for dev in matching_devices:
            dev_id = dev.get("id", "")
            name = _device_name(dev)
            manufacturer = dev.get("manufacturer") or ""
            model = dev.get("model") or ""
            area_id = dev.get("area_id") or ""
            area_name = areas.get(area_id, area_id)

            info_parts = []
            if manufacturer:
                info_parts.append(manufacturer)
            if model:
                info_parts.append(model)
            if area_name:
                info_parts.append(f"Room: {area_name}")
            header = f"Device: {name}"
            if info_parts:
                header += f" ({', '.join(info_parts)})"
            lines.append(header)

            dev_entities = entities_by_device.get(dev_id, [])
            if dev_entities:
                for ent in dev_entities:
                    e_id = ent.get("entity_id", "")
                    disabled = ent.get("disabled_by")
                    if disabled:
                        continue  # skip disabled entities
                    state_obj = states_by_id.get(e_id, {})
                    state = state_obj.get("state", "unknown")
                    attrs = state_obj.get("attributes", {})
                    fname = attrs.get("friendly_name", e_id)
                    extra = ""
                    if e_id.startswith("climate."):
                        cur = attrs.get("current_temperature")
                        tgt = attrs.get("temperature")
                        if cur is not None or tgt is not None:
                            extra = f" | Current: {cur}°C, Target: {tgt}°C"
                    lines.append(f"  → {fname} ({e_id}): {state}{extra}")
            else:
                lines.append("  (no entities found)")

            lines.append("")

        return "\n".join(lines).rstrip()

    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            return "Error: Home Assistant API token is missing or lacks permission for the device registry."
        if e.response.status_code == 404:
            return (
                "The device registry API is not available (HA < 2023.x or no access). "
                "Use 'ha_list_entities' with name_search instead."
            )
        return f"Error communicating with Home Assistant: {e}"
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.error("Error in ha_find_device: %s", e)
        return f"An unexpected error occurred: {e}"


@tool
async def ha_get_entity_details(entity_id: str, connection_id: str = "") -> str:
    """
    Returns the full state and ALL attributes of a single entity.
    Especially useful for climate devices (heaters, air conditioners) to see all available
    modes, min/max temperatures, and the current state.

    Use this tool before calling 'ha_call_service' for a heater/air conditioner
    to know the correct parameters (hvac_modes, min_temp, max_temp).

    Args:
        entity_id: The full entity ID (e.g. 'climate.office', 'light.wohnzimmer')
        connection_id: The ID of the connection to use (optional)
    """
    try:
        client_config = await _get_api_client(connection_id)
        url = f"{client_config['base_url']}/api/states/{entity_id}"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=client_config["headers"], timeout=10.0)
            response.raise_for_status()
            data = response.json()

        state = data.get("state")
        attrs = data.get("attributes", {})
        friendly_name = attrs.get("friendly_name", entity_id)

        lines = [f"Entity: {friendly_name} ({entity_id})", f"State: {state}", "Attributes:"]
        for key, value in attrs.items():
            if key == "friendly_name":
                continue
            lines.append(f"  {key}: {value}")

        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Entity '{entity_id}' was not found."
        return f"Error communicating with Home Assistant: {e}"
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as e:
        logger.error("Error in ha_get_entity_details: %s", e)
        return f"An unexpected error occurred: {e}"
