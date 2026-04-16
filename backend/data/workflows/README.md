# Workflow Templates

Vordefinierte Workflow-Templates für Ninko.

## Verfügbare Templates

| Template | Datei | Beschreibung |
|----------|-------|--------------|
| Einfache Sequenz | `template-simple-sequential.json` | Linearer Flow: Trigger → Agent → Ende |
| Bedingte Verzweigung | `template-conditional-branching.json` | Condition-Node mit zwei Pfaden |
| Parallele Verarbeitung | `template-parallel-processing.json` | Parallel-Node für gleichzeitige Aufgaben |
| Subflow Orchestration | `template-subflow-orchestration.json` | Subflow-Node für modulare Workflow-Komposition |
| Script Automation | `template-script-automation.json` | Script-Node für Python-Code-Ausführung |

## Verwendung

Templates können über die API importiert werden:

```bash
# Einfache Sequenz
curl -X POST http://localhost:8000/api/workflows/ \
  -H "Content-Type: application/json" \
  -d @backend/data/workflows/template-simple-sequential.json

# Subflow Orchestration
curl -X POST http://localhost:8000/api/workflows/ \
  -H "Content-Type: application/json" \
  -d @backend/data/workflows/template-subflow-orchestration.json

# Script Automation
curl -X POST http://localhost:8000/api/workflows/ \
  -H "Content-Type: application/json" \
  -d @backend/data/workflows/template-script-automation.json
```

## Template-Struktur

```json
{
  "id": "template-id",
  "name": "Anzeigename",
  "description": "Beschreibung",
  "nodes": [...],
  "edges": [...],
  "variables": [...]
}
```

## Node-Typen Referenz

- `trigger` - Workflow-Start (manual/cron/webhook)
- `agent` - KI-Agent ausführen
- `condition` - Bedingte Verzweigung
- `loop` - Schleife (foreach/while)
- `parallel` - Parallele Ausführung
- `subflow` - Anderen Workflow aufrufen
- `script` - Python-Script ausführen
- `variable` - Variable setzen
- `end` - Workflow-Ende

## Node-Typen im Detail

### Script

Führt ein gespeichertes Python-Script aus.

```json
{
  "type": "script",
  "label": "Daten verarbeiten",
  "config": {
    "script_id": "mein-script-id",
    "input_var": "raw_data",
    "timeout": "30"
  }
}
```

**Config-Optionen:**
- `script_id` (erforderlich): ID des Scripts aus dem Scripting-Modul
- `input_var` (optional): Variablenname, dessen Wert als `{script_input}` im Script verfügbar ist
- `timeout` (optional): Timeout in Sekunden (1-300, Default: 30)

**Output-Variablen:**
- `{script_output}`: stdout des Scripts
- `{script_error}`: stderr des Scripts (falls vorhanden)
- `{script_exit_code}`: Exit-Code (0 = Erfolg)
- `{previous_output}`: Alias für `{script_output}`

**Beispiel-Script:**
```python
import sys

# Input aus Variable (falls gesetzt)
input_data = sys.stdin.read()
if input_data:
    numbers = [int(x.strip()) for x in input_data.split(",")]
    result = sum(numbers)
    print(f"Summe: {result}")
else:
    print("Keine Input-Daten")
```
