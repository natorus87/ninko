import logging
from agents.base_agent import BaseAgent
from .tools import (
    ha_get_entity_state,
    ha_get_entity_details,
    ha_find_device,
    ha_call_service,
    ha_list_entities,
)

logger = logging.getLogger("ninko.modules.homeassistant.agent")

class HomeAssistantAgent(BaseAgent):
    """
    Der LLM-Agent für das Home Assistant Modul.
    Erbt von BaseAgent und bekommt spezifische HA Tools injiziert.
    """

    def __init__(self):
        super().__init__(
            name="homeassistant",

            system_prompt=(
                "Du bist der Smart Home und IoT Spezialist von Ninko. "
                "Du steuerst und überwachst Home Assistant Umgebungen im Namen des Benutzers.\n\n"
                "GERÄTE FINDEN — Strategie:\n"
                "1. User nennt einen Gerätenamen (z.B. 'Thermostat Büro', 'Shelly Küche') → "
                "'ha_find_device' aufrufen. Liefert echte Gerätenamen + Räume + alle Entitäten.\n"
                "2. User nennt Domain oder allg. Begriff (z.B. 'alle Lichter', 'Sensoren im Wohnzimmer') → "
                "'ha_list_entities' mit domain_filter und/oder name_search.\n"
                "3. Bekannte entity_id → direkt verwenden.\n\n"
                "GERÄTE STEUERN:\n"
                "- Temperatur setzen: service_name='climate.set_temperature', "
                "service_data_json='{\"temperature\": 22}'\n"
                "- Heizungsmodus: service_name='climate.set_hvac_mode', "
                "service_data_json='{\"hvac_mode\": \"heat\"}'\n"
                "- Lichter: 'light.turn_on' / 'light.turn_off', optional "
                "service_data_json='{\"brightness_pct\": 80}'\n"
                "- Vor komplexen Climate-Aufrufen: 'ha_get_entity_details' für verfügbare Modi/Grenzen.\n\n"
                "'ha_list_entities' enthält bereits den Status — danach NICHT noch 'ha_get_entity_state' aufrufen.\n"
                "Gehe effizient vor – so wenige Tool-Aufrufe wie möglich."
            ),

            tools=[ha_find_device, ha_list_entities, ha_get_entity_state, ha_get_entity_details, ha_call_service],
        )
