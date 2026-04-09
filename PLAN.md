# Plan: Intelligente Task-Decomposition mit Read-Only Subagents

## Core-Idee

Das 4-Tier-Routing bekommt einen neuen Schritt: **LLM-basierte Komplexitätsbewertung**. Erkennt das LLM eine datenintensive Aufgabe, delegiert der Orchestrator an einen **generischen Read-Only Subagent**. Dieser arbeitet in einem **isolierten Context**, sammelt und aggregiert Daten iterativ und gibt nur eine kompakte Zusammenfassung an den Orchestrator zurück.

**Warum?** Module wie Redmine, Jira, GLPI liefern bei `list_issues()` oft 50-200 KB JSON. Das füllt das Context-Window nach 2-3 Zyklen. Der User bekommt dann abgeschnittene oder generalisierte Antworten.

**Lösung:** Der Subagent absorbiert die großen Datenmengen in seinem eigenen Context. Der Orchestrator erhält nur ~300 Tokens statt ~15.000.

---

## Architektur

### Erweitertes Tier-Routing

```
Tier 1: Simple Questions (< 120 chars, keine Action-Verbs)
        → Direct LLM answer

Tier 2: Module erkannt (Keyword-Match)
        ↓
        LLM Complexity-Check: "Ist das datenintensiv?"
        ├─ NEIN → Tier 2: Direct Module Agent (wie bisher)
        └─ JA   → Tier 2.5: DataAnalysisSubagent (NEU)
                   → isolierter Context
                   → nur read-only Tools
                   → gibt Summary zurück

Tier 3: Dynamic Agent (kein Modul match)
Tier 4: Multi-Step Workflow Pipeline
```

### Complexity-Check (LLM-basiert)

**Wo:** Nach `_detect_module()`, vor Agent-Invocation

**Prompt:**
```markdown
Analysiere diese Aufgabe für Modul "{module}":

User-Query: {user_message}

Wird diese Aufgabe wahrscheinlich viele Datensätze zurückliefern
(> 20 Ergebnisse, komplexe Filterung, Aggregation)?

Indikatoren für JA:
- "alle/list all/show all" → viele Ergebnisse erwartet
- "gruppiert nach/group by" → Aggregation über große Menge
- "vergleiche/compare" → muss viele Daten durchgehen
- Keine explizite Limitierung ("die letzten 5")

Indikatoren für NEIN:
- "Ticket #123" → einzelne Ressource
- "erstelle/create" → Schreiboperation, keine Datenabfrage
- Explizites Limit ("zeige 3")

Antworte NUR mit JSON:
{
  "is_complex": true/false,
  "sub_tasks": ["task1", "task2"],
  "suggested_subagent_count": 1-2,
  "reasoning": "..."
}
```

**Timeout:** 2 Sekunden. Bei Timeout → `is_complex = false` (Fallback zu normalem Agent).

### Orchestrator-Integration

```python
# orchestrator.py — in route()

TIER_SUBAGENT = "2.5"  # String, nicht int

async def route(self, message, session_id="", ...):
    tier = await self._classify_tier(message)
    
    if tier == 1:
        # Direct LLM
        ...
    
    elif tier == 2:
        module, _ = await self._detect_module(message)
        
        # NEU: Complexity-Check
        complexity = await self._check_task_complexity(message, module)
        
        if complexity and complexity.get("is_complex"):
            # Tier 2.5: Subagent
            subagent = self._get_or_create_subagent(session_id, module)
            summary, did_compact = await subagent.invoke(
                task=message,
                module=module,
                sub_tasks=complexity.get("sub_tasks", []),
            )
            return summary, module, did_compact
        else:
            # Tier 2: Normal
            agent = self.registry.get_agent(module)
            response, did_compact = await agent.invoke(message)
            return response, module, did_compact
    ...
```

---

## DataAnalysisSubagent

### Konzept

```python
class DataAnalysisSubagent(BaseAgent):
    """
    Generischer Subagent für datenintensive Aufgaben.
    
    - Eigener isolierter Context (belastet Orchestrator nicht)
    - Nur read-only Tools (list_*, search_*, get_*, check_*)
    - Gibt kompakte Summary zurück, keine Rohdaten
    """
```

### Tool-Zugriff: Nur Read-Only vom erkannten Modul

**Problem:** Module-Tools sind pro Agent registriert, nicht zentral verfügbar.

**Lösung:** `ModuleRegistry` hat `get_agent(module_name)` → der Agent hat `.tools`. Filtern nach `_TOOL_READONLY` aus `safeguard.py`:

```python
def _get_readonly_tools_for_module(self, module: str) -> list:
    """Hole read-only Tools vom erkannten Modul."""
    module_agent = self.registry.get_agent(module)
    if not module_agent:
        return []
    
    from core.safeguard import _TOOL_READONLY
    return [t for t in module_agent.tools if t.name in _TOOL_READONLY]
```

Der Subagent bekommt **nur** die Tools des erkannten Moduls, nicht aller Module. Das verhindert Verwirrung und hält den Tool-Namespace klein.

### System-Prompt

```markdown
# Data Analysis Subagent

Du analysierst große Datenmengen für das Modul "{module}".

## Strategie

1. **Verstehe die Anfrage:** Welche Filter, Gruppierung, Sortierung?
2. **Iterativ abfragen:** Nutze limit-Parameter, nicht alles auf einmal
3. **Lokal aggregieren:** Zähle, gruppiere, sortiere in deinem Context
4. **Kompakt zusammenfassen:**
   - Statistiken (total, Verteilung)
   - Top-N Items (nach Relevanz/Alter/Priorität)
   - Insights (Auffälligkeiten, Trends)
   - NIEMALS vollständige Listen (max 10-20 Items)

## Wichtig
- Gib NUR die Zusammenfassung zurück, keine Rohdaten
- Max 500 Tokens Output
- Wenn > 100 Ergebnisse: aggregiere statt aufzulisten
```

### Subagent-Skalierung (Lokales LLM)

⚠️ **Constraint:** Bei einem lokalen LLM (LM Studio, Ollama) können LLM-Requests nicht parallel laufen (GPU ist Bottleneck). Mehrere Subagents parallel = Queue-Effekt = nur Overhead.

**Strategie: Sequenzielles Batching**

| Aufgabe | Subagents | Strategie |
|---------|-----------|-----------|
| 1-3 Queries | 1 | Ein Subagent, iterativ |
| 4-5 Queries | 1 | Ein Subagent, batcht alle Sub-Tasks |
| 6+ Queries (stark unterschiedlich) | 2 | Sequenziell, jeder batcht 2-3 |

Bei Cloud-APIs (OpenAI, OpenRouter): Parallelisierung möglich, aber nicht als Basis-Annahme.

---

## Step-Visualization im Dashboard

### Problemstellung

Aktuell sieht der User nur einen Spinner. Was macht der Subagent? Funktioniert es? Wo hängt es?

### Lösung: WebSocket Step-Streaming

**Backend sendet 4 Event-Typen über den bestehenden WebSocket-Kanal:**

```python
# Event-Typen
"step_start"   # Neuer Schritt beginnt
"step_update"  # Text-Update während Schritt läuft (optional)
"step_done"    # Schritt erfolgreich abgeschlossen
"step_error"   # Schritt fehlgeschlagen + Error-Details + Retry-Flag
```

**Wichtig:** Der Subagent ist ein ReAct-Agent — die Steps kommen **dynamisch** aus den Tool-Calls, nicht vordefiniert. Integration in `base_agent.py`:

```python
# In BaseAgent._run_agent() oder dem Tool-Execution-Hook:

# Vor Tool-Call:
await self._emit_step({
    "type": "step_start",
    "step_id": tool_call.id,
    "title": tool_call.name,  # z.B. "list_issues"
    "description": str(tool_call.args)[:200],  # Argumente gekürzt
    "status": "running"
})

# Nach Tool-Call:
await self._emit_step({
    "type": "step_done",
    "step_id": tool_call.id,
    "title": tool_call.name,
    "details": {
        "result_size": len(result),
        "duration_ms": elapsed_ms,
    },
    "status": "done"
})
```

So erscheint jeder Tool-Call als expandierbarer Schritt — egal welches Tool der Agent wählt.

### Frontend: Step-Tree (Claude Code Stil)

**Während Execution:**
```
●●● list_issues...                    (animated dots)
●●● Filtering results...              (animated dots)
●●● Aggregating by assignee...        (animated dots)
```

**Nach Completion:**
```
▶ ✓ list_issues                        500ms
    API: list_issues(status="Open", type="Bug")
    Results: 347 issues

▶ ✓ Filter by age                       50ms
    Input → Output: 347 → 67

▶ ✓ Group by assignee                   30ms
    Alice: 23, Bob: 18, Unassigned: 26

▶ ✓ Summary generated                  200ms
    12,500 → 125 tokens (1:100)
```

Klick auf `▶` expandiert die Details.

### Animated Step-Text

Der Schritt-Text animiert sich während er läuft:

**CSS Animated Dots:**
```css
.step-title.running::after {
  content: "";
  animation: dots 1.5s infinite;
}

@keyframes dots {
  0%, 20% { content: ""; }
  40% { content: "."; }
  60% { content: ".."; }
  80%, 100% { content: "..."; }
}
```

**Optionale Progress-Updates via WebSocket:**
```python
# Backend sendet step_update mit neuem Text
await self._emit_step({
    "type": "step_update",
    "step_id": tool_call.id,
    "title": f"list_issues ({len(partial_results)} received)"
})
```

Frontend aktualisiert den Text, die Dots-Animation läuft weiter.

### CSS-Regeln

```css
.steps-tree {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  font-size: 0.875rem;
}

.step {
  border-left: 2px solid var(--border);
  padding-left: 12px;
  margin-bottom: 4px;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 6px 0;
  user-select: none;
}

.step-status.running {
  color: var(--accent-blue);
  animation: pulse-dots 1.2s infinite;
}

.step-status.done { color: var(--success-green); }
.step-status.error { color: var(--error-red); }

@keyframes pulse-dots {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}

.step-details {
  display: none;
  padding: 8px 0 8px 12px;
  border-left: 2px solid var(--accent-blue);
  color: var(--text-muted);
}

.step-details.open { display: block; }

/* Error State */
.step.error { border-left-color: var(--error-red); }

.error-container {
  background: rgba(239, 68, 68, 0.05);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 6px;
  padding: 12px;
}

.error-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.btn-retry {
  background: var(--accent-blue);
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
  transition: background-color 0.15s, opacity 0.15s;
}

.btn-retry:disabled { opacity: 0.5; cursor: not-allowed; }
```

---

## Error Recovery & Retry

### Error-Klassifizierung

```python
class ErrorType(str, Enum):
    RETRYABLE = "retryable"   # Timeout, Connection, Rate-Limit
    PERMANENT = "permanent"    # Auth, Invalid Parameter, 404
    PARTIAL   = "partial"      # Teilresultate ok, weitermachen
```

Bei `step_error` sendet das Backend:
```python
await self._emit_step({
    "type": "step_error",
    "step_id": tool_call.id,
    "error": str(e),
    "error_type": "retryable",       # oder "permanent"
    "suggested_retry": True,          # Frontend zeigt Retry-Button
    "status": "error"
})
```

### Retry-Mechanismus

**Frontend:**
- `RETRYABLE` → Zeige Retry-Button + Skip-Button + Abort-Button
- `PERMANENT` → Zeige nur Error + Abort-Button (kein Retry)
- Exponential Backoff: 1s, 2s, 4s (max 3 Versuche)

**Backend braucht in-memory State** für den pausierten Subagent — ähnliches Pattern wie `_paused_sg_agents` in `base_agent.py` für Safeguard-Tool-Pending:

```python
# Module-level dict in data_analysis_subagent.py
_active_subagents: dict[str, DataAnalysisSubagent] = {}

def _get_or_create_subagent(session_id: str, module: str) -> DataAnalysisSubagent:
    if session_id not in _active_subagents:
        _active_subagents[session_id] = DataAnalysisSubagent(module)
    return _active_subagents[session_id]

def _cleanup_subagent(session_id: str):
    _active_subagents.pop(session_id, None)
```

**Retry-Endpoint:**

```python
@app.post("/api/subagent/retry-step")
async def retry_step(body: RetryStepRequest):
    subagent = _active_subagents.get(body.session_id)
    if not subagent:
        return {"status": "error", "error": "No active subagent"}
    
    result = await subagent.retry_step(body.step_id)
    return result
```

**Subagent muss fehlgeschlagene Steps tracken:**

```python
class DataAnalysisSubagent(BaseAgent):
    def __init__(self, module: str):
        super().__init__(name="data_analysis_subagent")
        self.module = module
        self.tools = self._get_readonly_tools_for_module(module)
        self._failed_steps: dict[str, dict] = {}  # step_id → {executor, args, ...}
    
    async def retry_step(self, step_id: str) -> dict:
        if step_id not in self._failed_steps:
            return {"status": "error", "error": "Step not found or already completed"}
        
        step = self._failed_steps[step_id]
        try:
            result = await step["tool"].ainvoke(step["args"])
            del self._failed_steps[step_id]
            # emit step_done
            return {"status": "success"}
        except Exception as e:
            is_retryable = isinstance(e, (TimeoutError, ConnectionError))
            # emit step_error
            return {"status": "error", "suggested_retry": is_retryable}
```

---

## Chat-History Verhalten

Wenn der Orchestrator an einen Subagent delegiert:

1. **Chat-History bekommt nur die Summary** (nicht die internen Steps)
2. **Steps sind transient** — sichtbar im Dashboard während der Execution, aber nicht in der gespeicherten History
3. **Grund:** Die Steps sind Debugging-Info, nicht Konversations-Kontext. Sie in die History zu packen würde das Context-Problem nur verschieben.

```python
# In orchestrator.route():
summary, did_compact = await subagent.invoke(task=message, module=module)

# Summary geht in die Chat-History (wie jede andere Agent-Antwort)
# Steps waren live via WebSocket sichtbar, werden nicht gespeichert
return summary, module, did_compact
```

---

## Fallback: Was wenn Complexity-Check falsch liegt?

**False Positive** (LLM sagt "komplex", aber es sind nur 5 Tickets):
- Subagent funktioniert trotzdem, nur minimaler Overhead (~1-2s extra LLM-Call)
- Akzeptabler Trade-off

**False Negative** (LLM sagt "nicht komplex", aber Module-Agent liefert 50 KB):
- `_truncate_output()` in `core_tools.py` greift bereits (200 Zeilen / 4000 Chars)
- Kein katastrophaler Fehler, nur suboptimale Antwort
- Langfristig: Feedback-Loop (wenn `_truncate_output()` triggert → nächstes Mal Subagent nutzen)

---

## Workflow-Beispiele

### Jira — "Alle kritischen Bugs älter als 2 Wochen"

```
User: "Zeige mir alle kritischen Bugs in Jira älter als 2 Wochen, gruppiert nach Assignee"

1. _detect_module() → "jira"
2. _check_task_complexity() → {is_complex: true, reasoning: "alle + älter als + gruppiert"}
3. DataAnalysisSubagent startet:
   - Tool: list_issues(type="Bug", priority="Critical", limit=100)
     ●●● list_issues...
     ✓ 67 Bugs (500ms)
   - Lokal: filter age > 14 days → 67 bleiben
   - Lokal: group by assignee → Alice: 23, Bob: 18, Unassigned: 26
   - Summary generieren
     ✓ Summary (200ms)
4. Orchestrator erhält: "67 kritische alte Bugs. Alice: 23, Bob: 18, Unassigned: 26."
   (~300 Tokens statt ~15.000)
```

### Redmine — "Wie viele offene Tickets für Projekt XYZ?"

```
User: "Wie viele offene Tickets haben wir für Projekt XYZ?"

1. _detect_module() → "redmine"
2. _check_task_complexity() → {is_complex: false, reasoning: "Einfache Zählung"}
3. Tier 2: Direct Redmine Agent (wie bisher)
```

### GLPI — "Überblick: Status-Verteilung + Überfällige + Assignees"

```
User: "Gib mir einen Überblick über alle Tickets: Status, Überfällige, Top Assignees"

1. _detect_module() → "glpi"
2. _check_task_complexity() → {
     is_complex: true,
     sub_tasks: ["Status-Verteilung", "Überfällige", "Assignee-Ranking"],
     suggested_subagent_count: 1
   }
3. DataAnalysisSubagent startet (1 Subagent, batcht alle 3 Sub-Tasks):
   - Tool: get_tickets(status="all", limit=100)
   - Lokal: group by status → Open: 47, In Progress: 23, Review: 8
   - Tool: get_tickets(filter="overdue")
   - Lokal: count → 5 überfällige
   - Lokal: group by assignee (aus erstem Abruf) → Alice: 28, Bob: 19
   - Summary
4. Orchestrator erhält kompakte Zusammenfassung
```

---

## Implementierungs-Phasen

### Phase 1: Core (2-3 Tage)

- [ ] `DataAnalysisSubagent` Klasse (`backend/agents/data_analysis_subagent.py`)
- [ ] `_check_task_complexity()` in Orchestrator
- [ ] `_get_readonly_tools_for_module()` — Tool-Filterung
- [ ] System-Prompt für Aggregation/Summarization
- [ ] Integration in `route()` (Tier 2.5)

### Phase 2: Step-Visualization (2-3 Tage)

- [ ] `_emit_step()` in BaseAgent (Hook bei Tool-Execution)
- [ ] WebSocket Event-Handling im Frontend (`subagent_step`)
- [ ] Step-Tree HTML + CSS (expandierbar, animated dots)
- [ ] `step_update` für Progress-Text während Execution

### Phase 3: Error Recovery (1-2 Tage)

- [ ] Error-Klassifizierung (`retryable` / `permanent` / `partial`)
- [ ] `_active_subagents` dict + `retry_step()` Methode
- [ ] `/api/subagent/retry-step` Endpoint
- [ ] Frontend: Retry/Skip/Abort Buttons + Exponential Backoff

### Phase 4: Testing & Tuning (1-2 Tage)

- [ ] Complexity-Check Prompt testen (10+ Queries, >80% Accuracy)
- [ ] Token-Zählung: messen ob Context tatsächlich gespart wird
- [ ] Integration Tests: Jira, Redmine, GLPI (je 3-5 Queries)
- [ ] Performance: Subagent-Overhead messen

---

## Entscheidungen (Finalisiert)

| # | Entscheidung | Begründung |
|---|-------------|-----------|
| 1 | **LLM-basierte Komplexitätsbewertung** (kein Keyword-Fallback) | LLM versteht Kontext, Keywords sind fragile. Timeout 2s → Fallback zu normalem Agent. |
| 2 | **Read-Only Tools** vom erkannten Modul | Subagent braucht nur Lesezugriff. Kein Safeguard nötig. |
| 3 | **Kein Safeguard-Check** für Subagent | Read-Only = sicher. Keine Bestätigung nötig. |
| 4 | **Sequenzielles Batching** (1-2 Subagents) | Lokales LLM = GPU Bottleneck. Parallelisierung nur mit Cloud-API. |
| 5 | **Steps = dynamisch aus Tool-Calls** | ReAct-Agent entscheidet selbst. Steps sind nicht vordefiniert. |
| 6 | **Summary in Chat-History**, Steps transient | Steps sind Debugging-Info, nicht Konversations-Kontext. |

---

## Datei-Struktur

```
backend/
├─ agents/
│  ├─ data_analysis_subagent.py  ← NEU
│  ├─ orchestrator.py            ← Modified (_check_task_complexity, Tier 2.5)
│  └─ base_agent.py              ← Modified (_emit_step Hook)
│
├─ api/
│  └─ routes_subagent.py         ← NEU (retry-step, abort Endpoints)
│
frontend/
├─ app.js                        ← Modified (Step-Tree Rendering, WebSocket Handler)
├─ style.css                     ← Modified (Steps CSS)
└─ i18n/*.json                   ← Modified (Step-Labels)
```

---

## Success-Kriterien

- [ ] Complexity-Check >80% Accuracy (10+ Test-Queries)
- [ ] Context-Ersparnis: Subagent-Summary <5% der Original-Datenmenge
- [ ] Performance: Subagent-Overhead <2s bei einfachen Queries
- [ ] Steps sichtbar, expandierbar, animiert im Dashboard
- [ ] Retry funktioniert für transiente Fehler (Timeout, Connection)
- [ ] Keine Regression: einfache Queries funktionieren wie bisher (Tier 2 unverändert)
