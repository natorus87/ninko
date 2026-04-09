# Ninko Improvement Backlog — inspiriert durch crewAI

Analyse von [crewAI](https://github.com/crewAIInc/crewAI) auf übertragbare Konzepte.
Fokus: konkrete, implementierbare Verbesserungen für Ninko's bestehende Architektur.

---

## Übersicht

| # | Thema | Aufwand | Wert | Phase |
|---|-------|---------|------|-------|
| 1 | Memory: Composite Scoring | Klein | Hoch | Quick Win |
| 2 | Skills: `allowed_tools` Whitelist | Klein | Hoch | Quick Win |
| 3 | Tool-Usage Events & Audit Trail | Mittel | Hoch | Quick Win |
| 4 | Knowledge Base vs. Memory Trennung | Mittel | Hoch | Mittelfristig |
| 5 | `@router`/`@listen` Workflow-DSL | Groß | Mittel | Mittelfristig |
| 6 | A2A Delegation mit AgentCard | Mittel | Mittel | Mittelfristig |
| 7 | Async-Safe Context Management | Mittel | Mittel | Mittelfristig |
| 8 | Skills: Progressive Disclosure | Klein | Mittel | Quick Win |
| 9 | LLM Cost Tracking | Mittel | Mittel | Mittelfristig |
| 10 | OpenTelemetry Tracing | Groß | Niedrig | Strategisch |

---

## 1. Memory: Composite Scoring

### Problem heute

`SemanticMemory` in `core/memory.py` macht nur Top-K nach cosine distance. Ältere aber wichtige Memories konkurrieren gleichwertig mit aktuellen. Unwichtiges Rauschen verdrängt relevante Fakten.

### crewAI-Ansatz

Composite Score beim Recall:

```
score = α · semantic_similarity + β · recency_decay + γ · importance_weight
```

- **Semantic Similarity**: cosine distance (wie heute)
- **Recency Decay**: `exp(-λ · age_in_days)` — Memories älter als 30 Tage werden automatisch weniger relevant
- **Importance Weight**: beim Speichern wird ein `importance` Score (0.0–1.0) gesetzt (LLM-basiert oder manuell per Kategorie)

### Umsetzung für Ninko

**`core/memory.py` — `SemanticMemory.query()`:**

```python
def _composite_score(
    self,
    distance: float,        # ChromaDB gibt 0=gleich, 2=maximal verschieden
    stored_at: datetime,
    importance: float = 0.5,
    alpha: float = 0.5,
    beta: float = 0.3,
    gamma: float = 0.2,
    decay_lambda: float = 0.05,  # Halbwertszeit ~14 Tage
) -> float:
    semantic = 1.0 - (distance / 2.0)           # normiert auf [0, 1]
    age_days = (datetime.utcnow() - stored_at).days
    recency = math.exp(-decay_lambda * age_days)
    return alpha * semantic + beta * recency + gamma * importance
```

**Beim Speichern (`store()`):**
```python
# Metadaten mit Timestamp und Importance
collection.add(
    documents=[text],
    metadatas=[{"stored_at": datetime.utcnow().isoformat(), "importance": importance}],
    ids=[uid],
)
```

**Beim Abrufen (`query()`):**
```python
results = collection.query(query_texts=[query], n_results=n_results * 3, include=["distances", "metadatas"])
# Composite Score berechnen, re-ranken, Top-K zurückgeben
```

### Zusatz: Auto-Importance beim Speichern

Bei `_auto_memorize()` in `base_agent.py` gibt der LLM-Call bereits eine Einschätzung zurück. Dort könnte direkt ein `importance`-Score mitextrahiert werden:

```
Antworte mit JSON: {"fact": "...", "importance": 0.8}
```

---

## 2. Skills: `allowed_tools` Whitelist

### Problem heute

Skills werden injiziert ohne zu deklarieren welche Tools sie benötigen oder erlauben. Der SafeGuard prüft nur global via `_TOOL_READONLY`. Es gibt keine skill-level Permission-Granularität.

### crewAI-Ansatz

Skills deklarieren explizit welche Tools sie verwenden dürfen:

```yaml
---
name: kubernetes-diagnostics
allowed_tools: [list_pods, get_pod_logs, describe_pod, get_events]
modules: [kubernetes]
---
```

### Umsetzung für Ninko

**SKILL.md Frontmatter erweitern:**

```yaml
---
name: kubernetes-incident-response
description: Kubernetes Incident Response Playbook
modules: [kubernetes]
allowed_tools: [list_pods, get_pod_logs, describe_deployment, get_events]
---
```

**`core/skills_manager.py` — `SkillInfo` Dataclass:**

```python
@dataclass
class SkillInfo:
    name: str
    description: str
    modules: list[str]
    body: str
    allowed_tools: list[str] = field(default_factory=list)  # NEU
```

**`core/safeguard.py` — Tool-Check mit Skill-Kontext:**

Wenn ein Skill injiziert ist und ein Tool-Call kommt, prüfen ob das Tool in `allowed_tools` des aktiven Skills liegt — zusätzlich zur globalen `_TOOL_READONLY` Prüfung.

**Sicherheitsvorteil:** Ein Skill der nur lesen soll, kann nicht plötzlich `delete_pod` aufrufen — auch wenn der SafeGuard das global erlauben würde.

---

## 3. Tool-Usage Events & Audit Trail

### Problem heute

Ninko loggt Tool-Calls nur implizit über `RedisLogHandler`. Es gibt keinen strukturierten Audit-Trail: welcher Agent hat wann welches Tool mit welchen Parametern aufgerufen, wie lange hat es gedauert, was war das Ergebnis (Größe, Fehler)?

### crewAI-Ansatz

Typed Events über einen Event-Bus:

```python
class ToolUsageEvent(BaseModel):
    agent_name: str
    tool_name: str
    args: dict
    result_size: int
    duration_ms: float
    error: str | None
    timestamp: datetime
    session_id: str
```

### Umsetzung für Ninko

**`core/events.py` — neues Modul:**

```python
import asyncio
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class ToolEvent:
    agent_name: str
    tool_name: str
    args: dict
    session_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: float = 0.0
    result_size: int = 0
    error: str | None = None

# Module-level Event-Queue
_event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
_listeners: list[callable] = []

async def emit(event: ToolEvent) -> None:
    for listener in _listeners:
        try:
            await listener(event)
        except Exception:
            pass

def register_listener(fn: callable) -> None:
    _listeners.append(fn)
```

**`agents/base_agent.py` — Hook bei Tool-Execution:**

LangGraph `create_react_agent` unterstützt Callbacks. Dort einen `ToolEventHandler` registrieren der `events.emit()` aufruft — analog zum `StepTrackingHandler` im `DataAnalysisSubagent`.

**Nutzen:**

- Dashboard: "Letzte Tool-Calls" Tabelle in Settings → Logs
- Cost Tracking (Punkt 9) baut darauf auf
- Compliance: vollständiger Audit-Trail aller Aktionen

**Redis-Persistenz:**

```python
key = "ninko:audit:tool_events"
await redis.lpush(key, event.model_dump_json())
await redis.ltrim(key, 0, 9999)  # Letzte 10.000 Events
```

---

## 4. Knowledge Base vs. Memory Trennung

### Problem heute

Ninko speichert alles in ChromaDB in einer `agent_memory` Collection: User-Fakten, Erfahrungen, episodische Erinnerungen — aber auch Wissen das statisch sein sollte (Runbooks, Modul-Dokumentation, API-Referenzen). Alles veraltet gleich schnell, alles hat dasselbe Recall-Verhalten.

### crewAI-Ansatz

Explizite Trennung:

| Typ | Inhalt | Lebensdauer | Beispiel |
|-----|--------|-------------|---------|
| `Memory` | Episodisch, per-Session-Fakten | Session/Tage | "User bevorzugt kurze Antworten" |
| `Knowledge` | Strukturiert, langlebig, multi-source | Permanent | Kubernetes-Runbook, API-Docs |

`Knowledge` hat pluggable `Sources`:
- `PDFKnowledgeSource` — lädt PDFs ein
- `URLKnowledgeSource` — crawlt URLs
- `StringKnowledgeSource` — statische Texte
- Beliebige Custom Sources

### Umsetzung für Ninko

**Zwei ChromaDB Collections statt einer:**

```python
# Bestehend (bleibt)
agent_memory_collection = chroma.get_or_create_collection("agent_memory")

# Neu: statisches Wissen
knowledge_collection = chroma.get_or_create_collection("ninko_knowledge")
```

**`core/knowledge.py` — neues Modul:**

```python
class KnowledgeSource(ABC):
    @abstractmethod
    async def load(self) -> list[str]:
        """Liefert Texte die in die Knowledge Collection kommen."""
        ...

class URLKnowledgeSource(KnowledgeSource):
    def __init__(self, url: str, selector: str | None = None): ...

class FileKnowledgeSource(KnowledgeSource):
    def __init__(self, path: str): ...

class KnowledgeBase:
    async def add_source(self, source: KnowledgeSource, tags: list[str] = []) -> None: ...
    async def query(self, text: str, tags: list[str] | None = None, top_k: int = 5) -> list[str]: ...
```

**Integration in `base_agent.py`:**

Im `invoke()` zuerst Knowledge-Query, dann Memory-Query. Knowledge-Results haben höhere Prio (sie sind verifiziertes Wissen).

**Initialisierung beim Startup:**

```python
# main.py lifespan
kb = KnowledgeBase()
await kb.add_source(URLKnowledgeSource("https://kubernetes.io/docs/..."), tags=["kubernetes"])
await kb.add_source(FileKnowledgeSource("docs/runbooks/proxmox.md"), tags=["proxmox"])
```

**Vorteil für Ninko:** Module-Dokumentation, Troubleshooting-Guides und API-Referenzen können einmalig geladen werden und sind für alle Agenten verfügbar — ohne dass sie durch User-Interaktion "vergessen" werden.

---

## 5. `@router` / `@listen` Workflow-DSL

### Problem heute

Ninko's Workflow-Engine ist graph-basiert (JSON-Nodes, Canvas-UI). Das ist gut für einfache lineare Flows, aber für komplexe Bedingungslogik muss der User den visuellen Editor bedienen. Es gibt keine programmatische, lesbare Definition von Workflows.

### crewAI-Ansatz

```python
class IncidentFlow(Flow):
    severity: int = 0
    
    @start()
    async def detect(self):
        self.severity = await check_severity()
    
    @router(detect)
    def route(self) -> str:
        return "critical" if self.severity > 8 else "standard"
    
    @listen("critical")
    async def page_oncall(self): ...
    
    @listen("standard")
    async def create_ticket(self): ...
    
    @listen(page_oncall, create_ticket)
    async def notify_summary(self): ...
```

### Umsetzung für Ninko

**Option A — Neuer Flow-Typ im Workflow-Editor:**

Neben dem visuellen Graph-Editor eine "Code"-Ansicht anbieten, die Python-Klassen mit Decorators definiert. Separate Engine in `core/flow_engine.py`.

**Option B — Skills als Flows:**

`SKILL.md` um einen optionalen `flow:` Block erweitern der einen Python-ähnlichen Pseudo-Code für bedingte Logik enthält. Der Agent interpretiert ihn.

**Decorator-System:**

```python
# core/flow_engine.py
def start():
    def decorator(fn): fn._is_start = True; return fn
    return decorator

def router(listen_to):
    def decorator(fn): fn._is_router = True; fn._listens_to = listen_to; return fn
    return decorator

def listen(*sources):
    def decorator(fn): fn._listens_to = sources; return fn
    return decorator

class Flow:
    async def run(self) -> dict:
        """Führt den Flow aus — traversiert den Dependency-Graph der Methoden."""
        ...
```

**Aufwand:** Groß — eigene Flow-Execution-Engine. Mittelfristig als Alternative zur JSON-basierten Workflow-Engine sinnvoll.

---

## 6. A2A Delegation mit AgentCard

### Problem heute

`call_module_agent(module_name, task)` in `core_tools.py` ist ein reiner String-Dispatch. Der Orchestrator weiß nicht was der Ziel-Agent kann — er ruft ihn blind auf. Routing passiert nur über Keyword-Matching oder LLM-Klassifizierung.

### crewAI-Ansatz

`AgentCard` als strukturiertes Manifest:

```json
{
  "name": "kubernetes-agent",
  "capabilities": ["pod management", "log analysis", "scaling"],
  "tools": ["list_pods", "get_pod_logs", "scale_deployment"],
  "response_schema": {"type": "object", "properties": {...}},
  "max_concurrency": 3
}
```

### Umsetzung für Ninko

**`ModuleManifest` erweitern:**

```python
@dataclass
class ModuleManifest:
    # bestehende Felder...
    agent_capabilities: list[str] = field(default_factory=list)  # NEU
    # z.B. ["pod management", "log streaming", "scaling", "namespace monitoring"]
```

**`core/module_registry.py` — `get_agent_card(module_name) -> dict`:**

```python
def get_agent_card(self, module_name: str) -> dict:
    manifest = self._manifests[module_name]
    agent = self._agents[module_name]
    return {
        "name": module_name,
        "display_name": manifest.display_name,
        "capabilities": manifest.agent_capabilities,
        "tools": [t.name for t in agent.tools],
        "routing_keywords": manifest.routing_keywords[:10],
    }
```

**Orchestrator-Verbesserung:**

`_build_module_descriptions()` nutzt heute `manifest.description` + 5 Keywords. Mit AgentCard könnte der LLM-Classifier präzisere Beschreibungen bekommen:

```
kubernetes: pod management, log analysis, scaling, namespace monitoring
           Tools: list_pods, get_pod_logs, scale_deployment, ...
```

**API-Endpoint:**

`GET /api/agents/cards` — gibt alle AgentCards zurück. Nützlich für externe Integrationen und das Dashboard.

---

## 7. Async-Safe Context Management

### Problem heute

Ninko propagiert Session-IDs, User-Kontext und Spracheinstellungen über explizite Parameter (`session_id: str`, `confirmed: bool`). Bei komplexen Aufrufketten (Orchestrator → Module Agent → Tool → Sub-Tool) müssen alle Parameter durchgereicht werden.

`status_bus` nutzt bereits `contextvars.ContextVar` für `session_id`. Aber andere Kontexte (Language, Auth-Role, Trace-ID) sind noch als Parameter.

### crewAI-Ansatz

Zentrale `ExecutionContext` Klasse mit `ContextVar`-Backend:

```python
_ctx_session: ContextVar[str] = ContextVar("session_id", default="")
_ctx_language: ContextVar[str] = ContextVar("language", default="de")
_ctx_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_ctx_user_role: ContextVar[str] = ContextVar("user_role", default="")

def capture() -> dict:
    return {
        "session_id": _ctx_session.get(),
        "language": _ctx_language.get(),
        "trace_id": _ctx_trace_id.get(),
        "user_role": _ctx_user_role.get(),
    }

def apply(ctx: dict) -> list[Token]:
    tokens = [
        _ctx_session.set(ctx.get("session_id", "")),
        _ctx_language.set(ctx.get("language", "de")),
        _ctx_trace_id.set(ctx.get("trace_id", "")),
        _ctx_user_role.set(ctx.get("user_role", "")),
    ]
    return tokens
```

### Umsetzung für Ninko

**`core/context.py` — neues Modul:**

Context wird in `routes_chat.py` am Request-Eingang gesetzt. Alle nachgelagerten Calls (Agent, Tool, Status-Bus) lesen aus dem Context statt Parameter.

**Schrittweise Migration:**

1. Zuerst `trace_id` hinzufügen (für Audit Trail aus Punkt 3)
2. Dann `language` aus Parameter-Passing herausnehmen
3. Langfristig `session_id` aus `_t()` und Status-Bus-Calls herausnehmen

**Vorteil:** Wenn ein Tool einen Sub-Call macht (z.B. `DataAnalysisSubagent` ruft Module-Tools auf), muss `session_id` nicht mehr explizit weitergegeben werden.

---

## 8. Skills: Progressive Disclosure (Lazy Loading)

### Problem heute

Alle Skills werden beim Startup vollständig geladen (`SkillsManager.load()`). Bei jedem Request werden bis zu 2 Skills als `SystemMessage` injiziert — der vollständige Markdown-Body. Bei langen Skills (300+ Zeilen) ist das unnötiger Token-Verbrauch wenn der Skill nur zu 20% relevant ist.

### crewAI-Ansatz

3-stufiges Disclosure-Modell:

| Stufe | Inhalt | Wann geladen |
|-------|--------|--------------|
| METADATA | Name, Description, Tags | Immer (Startup) |
| INSTRUCTIONS | Skill-Body (Markdown) | Bei Match |
| RESOURCES | Scripts, Templates, externe Refs | Bei explizitem Request |

### Umsetzung für Ninko

**SKILL.md Struktur erweitern:**

```markdown
---
name: kubernetes-incident-response
description: Kubernetes Incident Response Playbook
modules: [kubernetes]
allowed_tools: [list_pods, get_pod_logs]
---

## Kurzübersicht
<!-- METADATA-Level: immer verfügbar, max 2 Sätze -->
Best-Practice-Patterns für Kubernetes Incident Response.

## Vorgehen
<!-- INSTRUCTIONS-Level: nur bei Match injiziert -->
1. Pod-Status prüfen
...

## Ressourcen
<!-- RESOURCES-Level: nur bei explizitem "zeige details" -->
- Runbook: https://...
- Script: ./scripts/k8s-recover.sh
```

**`core/skills_manager.py` — `SkillInfo` mit Level:**

```python
@dataclass
class SkillInfo:
    name: str
    description: str  # METADATA
    modules: list[str]
    allowed_tools: list[str]
    body_short: str   # INSTRUCTIONS (bis ## Ressourcen)
    body_full: str    # RESOURCES (kompletter Body)
```

**Match-Logik bleibt gleich** — nur was injiziert wird ändert sich: standardmäßig `body_short`, bei explizitem "erkläre mir genauer" → `body_full`.

---

## 9. LLM Cost Tracking

### Problem heute

Ninko hat keine Übersicht über Token-Verbrauch pro Agent, pro Modul oder pro Session. Bei OpenRouter/Groq kostet jeder Call Geld — aber niemand sieht wie viel.

### crewAI-Ansatz

Token-Counting pro LLM-Call:

```python
class UsageMetrics(BaseModel):
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    successful_requests: int
    estimated_cost_usd: float  # basierend auf Provider-Preisliste
```

### Umsetzung für Ninko

**`core/llm_factory.py` — Token-Counting Wrapper:**

OpenAI-compatible APIs geben `usage.prompt_tokens` und `usage.completion_tokens` zurück. Diese aus der LLM-Response extrahieren und akkumulieren:

```python
class TokenTracker:
    _totals: dict[str, UsageMetrics] = {}  # per agent_name

    def record(self, agent_name: str, response) -> None:
        usage = getattr(response, "usage_metadata", None)
        if usage:
            self._totals.setdefault(agent_name, UsageMetrics()).add(usage)

    def get_summary(self) -> dict:
        return {k: v.model_dump() for k, v in self._totals.items()}
```

**Redis-Persistenz:** `ninko:metrics:tokens:{date}` — tagesweise akkumuliert.

**Dashboard:** Neues Panel in Settings → "Token-Verbrauch" mit Tabelle pro Agent und Gesamtkosten-Schätzung.

**API:** `GET /api/metrics/tokens` — gibt aktuelle Auswertung zurück.

**Preisliste:** Konfigurierbar per Provider in `llm_providers` Settings (`cost_per_1k_input`, `cost_per_1k_output`).

---

## 10. OpenTelemetry Tracing

### Problem heute

Bei Fehlern in Ninko (z.B. Tier-4 Pipeline schlägt fehl) muss man Logs manuell durchsuchen um zu verstehen: welcher Agent hat was aufgerufen, wo hat es gehängt, wie lange hat jeder Schritt gedauert?

### crewAI-Ansatz

OpenTelemetry als First-Class-Citizen:

- Jeder Agent-Aufruf ist ein `Span`
- Tool-Calls sind Child-Spans
- Trace-ID wird über Async-Boundaries propagiert
- Export zu Jaeger, Tempo, Datadog, etc.

### Umsetzung für Ninko

**`core/telemetry.py`:**

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

tracer = trace.get_tracer("ninko")

@contextmanager
def agent_span(agent_name: str, session_id: str):
    with tracer.start_as_current_span(f"agent.{agent_name}") as span:
        span.set_attribute("session_id", session_id)
        yield span

@contextmanager
def tool_span(tool_name: str, agent_name: str):
    with tracer.start_as_current_span(f"tool.{tool_name}") as span:
        span.set_attribute("agent", agent_name)
        yield span
```

**Integration in `base_agent.py`:**

```python
async def invoke(self, message: str, ...) -> tuple[str, bool]:
    with agent_span(self.name, session_id):
        # bestehende Logik
        ...
```

**Aufwand:** Groß — erfordert OTEL Collector Deployment. Sinnvoll erst ab stabiler Produktion und wenn mehrere Tenants/Clusters.

---

## Priorisierte Roadmap

### Phase 1 — Quick Wins (je 1–3 Tage)

1. **Skills `allowed_tools`** — SKILL.md Frontmatter + SafeGuard-Integration
2. **Skills Lazy Loading** — `body_short` vs. `body_full` Trennung im Parser
3. **Memory Composite Scoring** — `_composite_score()` in `SemanticMemory.query()`

### Phase 2 — Mittelfristig (je 1–2 Wochen)

4. **Tool-Usage Events** — `core/events.py` + Callback in `base_agent.py` + Dashboard-Panel
5. **AgentCard / ModuleManifest Erweiterung** — `agent_capabilities` + `/api/agents/cards`
6. **LLM Cost Tracking** — Token-Wrapper + Redis-Persistenz + Dashboard
7. **Knowledge Base** — `core/knowledge.py` + zweite ChromaDB Collection

### Phase 3 — Strategisch (je 2–4 Wochen)

8. **Async Context Management** — `core/context.py` + schrittweise Migration
9. **Flow DSL** — `core/flow_engine.py` + Decorator-System
10. **OpenTelemetry** — erst wenn Produktionslast skaliert

---

## Entscheidungs-Notizen

**Was crewAI besser macht als Ninko:**
- Formale Metadaten-Strukturen (alles deklariert, nichts implizit)
- Fine-grained Observability (Events, Telemetry)
- Saubere Trennung von Memory/Knowledge

**Was Ninko besser macht als crewAI:**
- Konkrete IT-Ops-Domäne (Module für echte Infrastruktur)
- SafeGuard-System (crewAI hat kein Äquivalent)
- Hot-Loading von Modulen/Skills ohne Restart
- Produktionsreifes Multi-Tenant-Design (Redis, Vault, ChromaDB)

**Nicht übernehmen:**
- crewAI's Crew-Konzept (N Agents arbeiten gleichzeitig an einer Aufgabe) — Ninko hat klare Hierarchie (Orchestrator → Modul), parallele Crews würden das durcheinanderbringen
- crewAI's Task-Objekte — Ninko's implizite Task-Delegation über LLM-Reasoning ist flexibler
