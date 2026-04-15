# Workflow Templates

Vordefinierte Workflow-Templates für Ninko.

## Verfügbare Templates

| Template | Datei | Beschreibung |
|----------|-------|--------------|
| Einfache Sequenz | `template-simple-sequential.json` | Linearer Flow: Trigger → Agent → Ende |
| Bedingte Verzweigung | `template-conditional-branching.json` | Condition-Node mit zwei Pfaden |
| Parallele Verarbeitung | `template-parallel-processing.json` | Parallel-Node für gleichzeitige Aufgaben |

## Verwendung

Templates können über die API importiert werden:

```bash
curl -X POST http://localhost:8000/api/workflows/ \
  -H "Content-Type: application/json" \
  -d @backend/data/workflows/template-simple-sequential.json
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

## Node-Typen

- `trigger` - Workflow-Start (manual/cron/webhook)
- `agent` - KI-Agent ausführen
- `condition` - Bedingte Verzweigung
- `loop` - Schleife (foreach/while)
- `parallel` - Parallele Ausführung
- `subflow` - Anderen Workflow aufrufen
- `variable` - Variable setzen
- `end` - Workflow-Ende
