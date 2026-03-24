import asyncio
import json
import logging
import os
from typing import Dict, Any, Optional
import httpx
from langchain_core.tools import tool

from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("kumio.modules.homeassistant.tools")

async def _get_api_client(connection_id: str = "") -> Dict[str, Any]:
    """
    Lädt Konfiguration und Secrets aus dem ConnectionManager oder Env-Vars für Home Assistant.
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
        # Fallback: Env-Var (für k8s / docker-compose ohne UI-Konfiguration)
        base_url = os.getenv("HOMEASSISTANT_URL", "http://homeassistant.local:8123").rstrip("/")
        api_token = os.getenv("HOMEASSISTANT_API_TOKEN", "")

    if not api_token:
        raise ValueError(
            "Home Assistant API Token fehlt. "
            "Bitte eine Verbindung in den Einstellungen anlegen oder HOMEASSISTANT_API_TOKEN setzen."
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
    Liest den aktuellen Status einer Entität aus Home Assistant (z.B. light.living_room, sensor.temperature).
    Nutze dieses Tool, um zu überprüfen, ob ein Licht an/aus ist, wie warm es ist oder um irgendwelche Sensorwerte aus dem Smart Home abzufragen.
    
    Args:
        entity_id: Die vollständige Home Assistant Entitäts-ID (z.B. 'light.wohnzimmer', 'switch.steckdose_tv')
        connection_id: Die ID der zu nutzenden Verbindung (optional)
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
            
            return f"Die Entität '{friendly_name}' ({entity_id}) hat aktuell den Status '{state}'."
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Entität '{entity_id}' wurde nicht gefunden."
        logger.error(f"HTTP Fehler bei ha_get_entity_state: {e}")
        return f"Fehler bei der Kommunikation mit Home Assistant: {e}"
    except Exception as e:
        logger.error(f"Fehler in ha_get_entity_state: {e}")
        return f"Ein unerwarteter Fehler ist aufgetreten: {e}"

@tool
async def ha_call_service(service_name: str, entity_id: str, service_data_json: str = "", connection_id: str = "") -> str:
    """
    Ruft einen Service in Home Assistant auf, um ein Gerät zu steuern.
    Unterstützt beliebige Zusatzparameter über service_data_json (als JSON-String).

    Beispiele:
    - Licht einschalten: service_name='light.turn_on', entity_id='light.wohnzimmer'
    - Licht mit Helligkeit: service_name='light.turn_on', entity_id='light.wohnzimmer', service_data_json='{"brightness_pct": 80}'
    - Heizung auf 22°C: service_name='climate.set_temperature', entity_id='climate.office', service_data_json='{"temperature": 22}'
    - Heizungsmodus: service_name='climate.set_hvac_mode', entity_id='climate.office', service_data_json='{"hvac_mode": "heat"}'
    - Schalter: service_name='switch.turn_off', entity_id='switch.steckdose'

    Args:
        service_name: Der auszuführende Service im Format 'domain.service' (z.B. 'light.turn_on', 'climate.set_temperature')
        entity_id: Die vollständige Entitäts-ID (z.B. 'light.wohnzimmer', 'climate.office'). 'all' für alle Entitäten.
        service_data_json: Optionale Zusatzparameter als JSON-String (z.B. '{"temperature": 22}' oder '{"brightness_pct": 80}')
        connection_id: Die ID der zu nutzenden Verbindung (optional)
    """
    try:
        if "." not in service_name:
            return "Fehler: service_name muss das Format 'domain.service' haben (z.B. 'light.turn_on')."

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
                    return f"Fehler: service_data_json muss ein JSON-Objekt sein (z.B. {{\"temperature\": 22}})."
            except json.JSONDecodeError as e:
                return f"Fehler: service_data_json ist kein gültiges JSON: {e}"

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=client_config["headers"], json=payload, timeout=10.0)
            response.raise_for_status()

            extra_info = f" mit Parametern {service_data_json}" if service_data_json else ""
            return f"Der Service '{service_name}' wurde erfolgreich für '{entity_id}'{extra_info} aufgerufen."
    except httpx.HTTPError as e:
        logger.error(f"HTTP Fehler bei ha_call_service: {e}")
        return f"Fehler bei der Kommunikation mit Home Assistant API: {e}"
    except Exception as e:
        logger.error(f"Fehler in ha_call_service: {e}")
        return f"Ein unerwarteter Fehler ist aufgetreten: {e}"

@tool
async def ha_list_entities(domain_filter: str = "", name_search: str = "", connection_id: str = "") -> str:
    """
    Listet Entitäten in Home Assistant auf. Unterstützt Suche nach Domain und/oder Namen.
    Nützlich, um unbekannte Entitäts-IDs zu finden, bevor ein Service aufgerufen wird.

    Beispiele:
    - Alle Heizungen: domain_filter='climate'
    - Alle Lichter im Wohnzimmer: domain_filter='light', name_search='wohnzimmer'
    - Suche nach "büro": name_search='büro'
    - Alle Entitäten: (beide Parameter leer lassen)

    Args:
        domain_filter: Optionaler Filter für eine Domäne (z.B. 'light', 'switch', 'climate', 'sensor', 'binary_sensor'). Leer = alle Domains.
        name_search: Optionale Volltextsuche im Anzeigenamen oder in der Entitäts-ID (Groß-/Kleinschreibung egal). Leer = kein Name-Filter.
        connection_id: Die ID der zu nutzenden Verbindung (optional)
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

                # Für Climate-Entitäten: Solltemperatur anzeigen
                extra = ""
                if e_id.startswith("climate."):
                    current_temp = attrs.get("current_temperature")
                    target_temp = attrs.get("temperature")
                    hvac_mode = attrs.get("hvac_mode", state)
                    if current_temp is not None or target_temp is not None:
                        extra = f" | Ist: {current_temp}°C, Soll: {target_temp}°C, Modus: {hvac_mode}"

                entities.append(f"- {friendly_name} ({e_id}): {state}{extra}")

            if not entities:
                msg = "Keine Entitäten gefunden"
                if domain_filter:
                    msg += f" für Domain '{domain_filter}'"
                if name_search:
                    msg += f" mit Namen '{name_search}'"
                return msg + "."

            header = f"Gefundene Entitäten ({len(entities)}):"
            if len(entities) > 60:
                header = f"Es wurden {len(entities)} Entitäten gefunden. Hier die ersten 60 — nutze name_search oder domain_filter um einzugrenzen:"
                return header + "\n" + "\n".join(entities[:60])

            return header + "\n" + "\n".join(entities)
    except Exception as e:
        logger.error(f"Fehler in ha_list_entities: {e}")
        return f"Fehler beim Auflisten der Entitäten: {e}"


@tool
async def ha_find_device(search: str, connection_id: str = "") -> str:
    """
    Sucht in der Home Assistant Geräte-Registry nach einem Gerät anhand seines Namens
    und gibt alle zugehörigen Entitäten zurück.

    Im Gegensatz zu 'ha_list_entities' durchsucht dieses Tool die echten Gerätenamen
    (z.B. "Thermostat Büro", "Shelly Plug Küche"), nicht nur entity_ids oder friendly_names.
    Außerdem werden Räume/Bereiche (Areas) angezeigt.

    Nutze dieses Tool, wenn der User ein Gerät beim Namen nennt und du die entity_id nicht kennst.

    Args:
        search: Suchbegriff (Teilstring, Groß-/Kleinschreibung egal), z.B. 'büro', 'thermostat', 'shelly'
        connection_id: Die ID der zu nutzenden Verbindung (optional)
    """
    try:
        client_config = await _get_api_client(connection_id)
        base_url = client_config["base_url"]
        headers = client_config["headers"]
        search_lower = search.lower()

        async with httpx.AsyncClient() as client:
            # Geräte-Registry laden
            dev_resp = await client.get(
                f"{base_url}/api/config/device_registry/list",
                headers=headers, timeout=10.0
            )
            dev_resp.raise_for_status()
            devices: list = dev_resp.json()

            # Entitäts-Registry laden (enthält device_id Zuordnung)
            ent_resp = await client.get(
                f"{base_url}/api/config/entity_registry/list",
                headers=headers, timeout=10.0
            )
            ent_resp.raise_for_status()
            entity_registry: list = ent_resp.json()

            # Bereich-Registry laden (optional — ignorieren wenn nicht verfügbar)
            areas: Dict[str, str] = {}
            try:
                area_resp = await client.get(
                    f"{base_url}/api/config/area_registry/list",
                    headers=headers, timeout=10.0
                )
                if area_resp.status_code == 200:
                    for a in area_resp.json():
                        areas[a.get("area_id", "")] = a.get("name", "")
            except Exception:
                pass

            # Aktuellen Status aller Entitäten laden (für state-Anzeige)
            states_resp = await client.get(f"{base_url}/api/states", headers=headers, timeout=15.0)
            states_resp.raise_for_status()
            states_by_id: Dict[str, Any] = {s["entity_id"]: s for s in states_resp.json()}

        # Geräte nach Suchbegriff filtern
        def _device_name(dev: Dict) -> str:
            return (dev.get("name_by_user") or dev.get("name") or "").strip()

        matching_devices = [
            d for d in devices
            if search_lower in _device_name(d).lower()
            or search_lower in (d.get("model") or "").lower()
            or search_lower in (d.get("manufacturer") or "").lower()
        ]

        if not matching_devices:
            return f"Kein Gerät mit dem Begriff '{search}' gefunden. Tipp: Versuche 'ha_list_entities' mit name_search='{search}'."

        # Entitäten je Gerät gruppieren
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
                info_parts.append(f"Raum: {area_name}")
            header = f"Gerät: {name}"
            if info_parts:
                header += f" ({', '.join(info_parts)})"
            lines.append(header)

            dev_entities = entities_by_device.get(dev_id, [])
            if dev_entities:
                for ent in dev_entities:
                    e_id = ent.get("entity_id", "")
                    disabled = ent.get("disabled_by")
                    if disabled:
                        continue  # deaktivierte Entitäten überspringen
                    state_obj = states_by_id.get(e_id, {})
                    state = state_obj.get("state", "unbekannt")
                    attrs = state_obj.get("attributes", {})
                    fname = attrs.get("friendly_name", e_id)
                    extra = ""
                    if e_id.startswith("climate."):
                        cur = attrs.get("current_temperature")
                        tgt = attrs.get("temperature")
                        if cur is not None or tgt is not None:
                            extra = f" | Ist: {cur}°C, Soll: {tgt}°C"
                    lines.append(f"  → {fname} ({e_id}): {state}{extra}")
            else:
                lines.append("  (keine Entitäten gefunden)")

            lines.append("")

        return "\n".join(lines).rstrip()

    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            return "Fehler: Home Assistant API Token fehlt oder hat keine Berechtigung für die Geräte-Registry."
        if e.response.status_code == 404:
            return (
                "Die Geräte-Registry API ist nicht verfügbar (HA < 2023.x oder kein Zugriff). "
                "Nutze stattdessen 'ha_list_entities' mit name_search."
            )
        return f"Fehler bei der Kommunikation mit Home Assistant: {e}"
    except Exception as e:
        logger.error(f"Fehler in ha_find_device: {e}")
        return f"Ein unerwarteter Fehler ist aufgetreten: {e}"


@tool
async def ha_get_entity_details(entity_id: str, connection_id: str = "") -> str:
    """
    Liefert den vollständigen Status und ALLE Attribute einer einzelnen Entität.
    Besonders nützlich für Climate-Geräte (Heizungen, Klimaanlagen), um alle verfügbaren
    Modi, Min-/Max-Temperaturen und den aktuellen Zustand zu sehen.

    Nutze dieses Tool bevor du 'ha_call_service' für eine Heizung/Klimaanlage aufrufst,
    um die richtigen Parameter (hvac_modes, min_temp, max_temp) zu kennen.

    Args:
        entity_id: Die vollständige Entitäts-ID (z.B. 'climate.office', 'light.wohnzimmer')
        connection_id: Die ID der zu nutzenden Verbindung (optional)
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

        lines = [f"Entität: {friendly_name} ({entity_id})", f"Status: {state}", "Attribute:"]
        for key, value in attrs.items():
            if key == "friendly_name":
                continue
            lines.append(f"  {key}: {value}")

        return "\n".join(lines)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Entität '{entity_id}' wurde nicht gefunden."
        return f"Fehler bei der Kommunikation mit Home Assistant: {e}"
    except Exception as e:
        logger.error(f"Fehler in ha_get_entity_details: {e}")
        return f"Ein unerwarteter Fehler ist aufgetreten: {e}"
