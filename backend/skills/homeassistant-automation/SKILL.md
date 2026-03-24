---
name: homeassistant-automation
description: Home Assistant Automationen, Szenen, Entitäten, Skripte, Zustände abfragen, Lichter Geräte steuern, Trigger Bedingungen
modules: [homeassistant]
---

## Arbeitsweise mit Home Assistant

### Entitäten-Konzept
- Jedes Gerät hat eine `entity_id` im Format `domain.name` (z.B. `light.wohnzimmer`, `switch.tv`)
- Domains: `light`, `switch`, `sensor`, `binary_sensor`, `climate`, `cover`, `media_player`
- Zustände: `on`/`off`, Zahlen (Temperatur, Helligkeit), Texte

### Status abfragen
```
get_entity_state(entity_id)      → aktueller Zustand + Attribute
list_entities(domain)            → alle Entitäten einer Domain
```

### Steuern
```
control_entity(entity_id, action, ...)
  action: "turn_on" | "turn_off" | "toggle"
  Licht-Parameter: brightness (0-255), color_temp, rgb_color
```

### Szenen & Skripte
- Szenen aktivieren: `control_entity("scene.NAME", "turn_on")`
- Skripte ausführen: `control_entity("script.NAME", "turn_on")`

### Automationen abfragen
- `list_entities("automation")` → alle Automationen mit Status
- Automation aktivieren/deaktivieren: `control_entity("automation.NAME", "turn_on/off")`

### Häufige Muster
| Anfrage | Vorgehen |
|---|---|
| "Mach alle Lichter aus" | `list_entities("light")` → jedes `turn_off` |
| "Wie warm ist es im Büro?" | `get_entity_state("sensor.buero_temperatur")` |
| "Aktiviere Szene Abend" | `control_entity("scene.abend", "turn_on")` |
| "Alle Geräte im Schlafzimmer" | `list_entities()` → nach "schlafzimmer" filtern |

### Fehler-Handling
- `entity_id not found` → `list_entities()` aufrufen und ähnliche Namen vorschlagen
- `state unavailable` → Gerät offline oder nicht erreichbar
- Bei Unsicherheit über entity_id immer erst `list_entities()` aufrufen
