---
name: workflow-builder
description: Workflow erstellen, Workflow bauen, Workflow anlegen, Automatisierung erstellen, Automatisierung bauen, Workflow mit Bedingung, Workflow mit Loop, Workflow mit Schleife, Workflow mit Branching, DAG-Workflow, Workflow konfigurieren, Workflow verbessern, Workflow iterativ verbessern, Workflow testen, Workflow verfeinern, create_dag_workflow, create_linear_workflow
modules: []
---

## Workflow Builder – Vollständige Expertise

Dieses Skill gibt Ninko alle Kenntnisse, um hochwertige, persistente Workflows zu bauen, zu testen und iterativ zu verbessern.

---

## Schritt 1 – Wann Workflow, wann Pipeline, wann Agent?

Drei Werkzeuge für Automatisierung — der Unterschied ist entscheidend:

| Werkzeug | Wann nutzen | Tool |
|---|---|---|
| **Workflow** | Persistente, benannte, wiederholbare Automatisierung — auch per Scheduler planbar. Hat visuellen Editor, Run-History, Branching, Loops | `create_dag_workflow` / `create_linear_workflow` |
| **Pipeline** | Ad-hoc, einmalig, mehrere Module in Serie, keine Persistenz | `run_pipeline` |
| **Agent** | Einzelne komplexe Aufgabe mit Tool-Nutzung, interaktiv | `call_module_agent` |

**Faustregel**: Wenn der User sagt „erstelle einen Workflow" oder „baue eine Automatisierung" → immer `create_dag_workflow` oder `create_linear_workflow` aufrufen. Nie nur erklären.

---

## Schritt 2 – Interview: Intent präzise verstehen

Vor dem Bauen den Use-Case klären. Ziel: einen Workflow, der in der Praxis läuft.

**4 Pflichtfragen** (wenn nicht bereits klar):

1. **Auslöser**: Manuell, Zeitplan (Cron), Webhook oder Event?
2. **Schritte**: Was soll nacheinander passieren? (Liste der Aktionen)
3. **Branching**: Gibt es Bedingungen? Was passiert bei Fehler?
4. **Variablen**: Werden Daten zwischen Schritten übergeben?

**Faustregel**: Sind alle 4 klar → sofort Workflow bauen. Ist der Use-Case einfach-linear → `create_linear_workflow`. Gibt es Conditions, Loops oder Branching → `create_dag_workflow`.

---

## Schritt 3 – Node-Typen: Alle Bausteine

### trigger — Startpunkt
Jeder Workflow braucht genau einen Trigger. Konfiguration:
```
mode: "manual"    → Per UI oder Tool gestartet
mode: "cron"      → Zeitplan, z.B. cron: "0 8 * * *" (täglich 8 Uhr)
mode: "webhook"   → HTTP-Trigger
```

### agent — KI-Ausführungsschritt
Delegiert eine Aufgabe an den Orchestrator. Der Prompt kann Variablen enthalten:
```
agent_id: "orchestrator"    → Immer "orchestrator" verwenden
prompt: "Prüfe alle Pods auf Fehler und gib eine Liste zurück"
```
**Wichtig**: Der Output eines Agent-Nodes wird automatisch als `{previous_output}` in der nächsten Node verfügbar.

### condition — Branching
Wertet einen Ausdruck aus und wählt den True- oder False-Pfad.
```
expression: "output.contains(\"error\")"
true_label: "true"     → Edge-Label für den Ja-Pfad
false_label: "false"   → Edge-Label für den Nein-Pfad
```
Vollständige Expressions: → Schritt 4

### loop — Iteration
Führt einen Prompt für jedes Element einer Liste aus. Ergebnis in `{loop_results}`.
```
mode: "foreach"              → Iteriert über alle Items
variable: "items"            → Name der Variable mit der Items-Liste
prompt: "Verarbeite: {loop_item}"   → Template für jeden Durchlauf
max_iterations: "10"         → Sicherheits-Cap (max. 50)
```
`{loop_item}` und `{loop_index}` sind in jedem Durchlauf verfügbar.
Für `while`-Mode: `condition: "variable.status != \"done\""` hinzufügen.

### variable — Werte setzen
Setzt oder transformiert eine Variable, die in späteren Nodes verwendbar ist:
```
name: "recipient"
value: "admin@example.com"
```

### end — Abschluss
Markiert das Ende eines Pfades. Jeder Pfad muss mit einem End-Node schließen:
```
status: "succeeded"    oder    status: "failed"
```

---

## Schritt 4 – Condition-Expressions: Vollständige Syntax

| Expression | Bedeutung | Beispiel |
|---|---|---|
| `output.contains("x")` | previous_output enthält x | `output.contains("error")` |
| `output.startswith("x")` | beginnt mit x | `output.startswith("Fehler")` |
| `output.endswith("x")` | endet mit x | `output.endswith("OK")` |
| `output.matches("regex")` | Regex-Match auf previous_output | `output.matches("\\d+ Pods")` |
| `variable.NAME == "value"` | Variable hat Wert | `variable.status == "done"` |
| `variable.NAME != "value"` | Variable hat nicht Wert | `variable.count != "0"` |
| `variable.NAME > N` | Variable numerisch größer | `variable.count > 5` |
| `variable.NAME < N` | Variable numerisch kleiner | `variable.errors < 1` |
| `len(output) > N` | Länge des Outputs | `len(output) > 100` |

**Fallback**: Unbekannte Expressions → `true` (aus Sicherheit immer den True-Pfad nehmen).

---

## Schritt 5 – Variable-Interpolation

Im `prompt` jedes Agent- oder Loop-Nodes sind folgende Platzhalter verfügbar:

| Variable | Beschreibung |
|---|---|
| `{previous_output}` | Output des vorherigen Agent-Nodes |
| `{loop_item}` | Aktuelles Item im Loop (foreach) |
| `{loop_index}` | Aktueller Index im Loop (0-basiert) |
| `{loop_results}` | Gesammelte Ergebnisse aller Loop-Iterationen |
| `{VARIABLE_NAME}` | Jede mit Variable-Node gesetzte Variable |

**Beispiel**: `"Sende folgende Ergebnisse an {recipient}: {previous_output}"`

---

## Schritt 6 – Prompt-Design für Agent-Nodes

Agent-Prompts im Workflow unterscheiden sich von Chat-Prompts:
- **Kontext geben**: Der Agent hat keine Chat-History — alles Wichtige muss im Prompt stehen
- **Spezifisch**: `"Prüfe alle Pods im Namespace 'production' auf CrashLoopBackOff"` statt `"Schau nach Fehlern"`
- **Output formatieren**: `"Gib das Ergebnis als komma-separierte Liste zurück"` wenn der Output in `{loop_items}` landet
- **Kontext weitergeben**: `"Basierend auf diesem K8s-Status: {previous_output} — erstelle ein GLPI-Ticket"`

---

## Schritt 7 – Fehler-Handling-Muster

Ninko-Workflows stoppen bei Node-Fehler sofort. Robuste Workflows nutzen Conditions als Fehler-Handler:

```
Trigger → Agent (Hauptaufgabe)
              ↓
         Condition: output.contains("Fehler")
           true ↓              false ↓
         Agent (Alert)       End (succeeded)
              ↓
         End (failed)
```

**Empfehlung**: Jeden kritischen Agent-Step mit einer nachgelagerten Error-Condition absichern.

---

## Schritt 8 – Welches Tool verwenden?

### `create_linear_workflow(name, description, steps)`
Nutzen wenn:
- Einfache lineare Abfolge ohne Branching
- Schnell und ohne viele Nodes
- Beispiel: `["Prüfe Pods", "Sende Telegram-Bericht"]`

### `create_dag_workflow(name, description, nodes, edges)`
Nutzen wenn:
- Conditions, Loops, Branching oder Fehler-Handler benötigt
- Mehr als 4 Schritte
- Vollständige Kontrolle über die Struktur

**Vollständiges Beispiel für `create_dag_workflow`**:
```python
create_dag_workflow(
  name="K8s Daily Health Check",
  description="Täglich Pods prüfen und bei Fehlern Alert senden",
  nodes=[
    {"id": "start", "type": "trigger", "label": "Start", "config": {"mode": "cron", "cron": "0 8 * * *"}},
    {"id": "check", "type": "agent", "label": "Pods prüfen", "config": {"agent_id": "orchestrator", "prompt": "Prüfe alle Pods auf CrashLoopBackOff und OOMKilled"}},
    {"id": "cond",  "type": "condition", "label": "Fehler?", "config": {"expression": "output.contains(\"error\")", "true_label": "true", "false_label": "false"}},
    {"id": "alert", "type": "agent", "label": "Alert senden", "config": {"agent_id": "orchestrator", "prompt": "Sende Telegram-Alert: {previous_output}"}},
    {"id": "ok",    "type": "end", "label": "Alles OK", "config": {"status": "succeeded"}},
    {"id": "done",  "type": "end", "label": "Alert gesendet", "config": {"status": "succeeded"}}
  ],
  edges=[
    {"source_id": "start", "target_id": "check",  "label": ""},
    {"source_id": "check",  "target_id": "cond",   "label": ""},
    {"source_id": "cond",   "target_id": "alert",  "label": "true"},
    {"source_id": "cond",   "target_id": "ok",     "label": "false"},
    {"source_id": "alert",  "target_id": "done",   "label": ""}
  ]
)
```

---

## Schritt 9 – Anti-Patterns & häufige Fehler

| Anti-Pattern | Problem | Lösung |
|---|---|---|
| Workflow ohne End-Node | Execution hängt, Status bleibt "running" | Jeden Pfad mit End-Node abschließen |
| Agent-Prompt ohne Kontext | Agent antwortet generisch | `{previous_output}` im Prompt verwenden |
| Condition ohne beide Edges | Ein Pfad führt ins Nirgendwo | Immer beide: true-Edge und false-Edge setzen |
| Loop ohne max_iterations | Endlosloop möglich | Immer max_iterations setzen (Default: 10) |
| Trigger ohne Modus | Manuell nur über UI startbar | Cron-Modus setzen wenn automatisch gewünscht |
| Zu viele Agent-Nodes in Serie | Jeder wartet auf den vorherigen | Pipeline statt Workflow wenn keine Persistenz nötig |
| Variable ohne Nutzung | Variable gesetzt aber nie interpoliert | `{variable_name}` im nachfolgenden Prompt nutzen |
| Fehlende Error-Condition | Fehler stoppt gesamten Workflow | Condition nach kritischen Steps |

---

## Schritt 10 – Qualitäts-Checkliste vor `create_dag_workflow`

- [ ] **Trigger**: Exakt ein Trigger-Node, Modus (manual/cron) definiert
- [ ] **End-Nodes**: Jeder mögliche Pfad endet in einem End-Node
- [ ] **Edges vollständig**: Alle Nodes verbunden, keine isolierten Nodes
- [ ] **Condition-Edges**: Beide Pfade (true + false) mit passendem label definiert
- [ ] **Prompts konkret**: Nicht "mache etwas" — spezifische Aufgabe mit Kontext
- [ ] **Variablen-Interpolation**: `{previous_output}` wo nötig, korrekte Syntax
- [ ] **Loop max_iterations**: Gesetzt wenn Loop-Node verwendet
- [ ] **Fehler-Handler**: Kritische Steps durch Condition abgesichert

Alle Punkte erfüllt → `create_dag_workflow(...)` aufrufen.

Danach: Workflow direkt ausführen mit `execute_workflow(name_oder_id)` und Execution Trace prüfen.
