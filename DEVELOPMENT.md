# Kumio – Technical Development Memory

This document serves as a persistent "memory" and technical guide for the Kumio project. It captures the architecture, design decisions, implementation patterns, and development history.

## 🚀 Project Vision
Kumio is a modular, AI-powered IT-Operations platform. Its core philosophy is an **immutable core** with **auto-discovering modules**. The AI Orchestrator uses a dynamic tool-discovery mechanism based on module manifests, allowing for infinite extensibility without modifying core code.

---

## 🛠 Tech Stack

### Backend
- **Framework**: FastAPI (Python 3.12)
- **AI/LLM**: LM Studio (OpenAI-compatible) or Ollama / LangChain
- **Vektordatenbank**: ChromaDB 0.4.24 (Semantic Memory)
- **Cache/Queue**: Redis (Working Memory & PubSub)
- **Secrets**: HashiCorp Vault (with SQLite Fallback)
- **Task Scheduling**: APScheduler (Core-integrated)

### Frontend
- **Framework**: Vanilla JS / HTML5 / CSS3
- **Design**: "Fox Armor" (Light Mode) & "Glowing Circuit" (Dark Mode) aesthetic, Glassmorphism
- **Communication**: REST API + Dynamic Tab Loading

---

## 🏗 Architecture Deep Dive

### 1. Module Discovery Pattern
Every module lives in `backend/modules/<module_name>/`.
The `ModuleRegistry` (core) discovers them by looking for `__init__.py` files.
Each module **must** export:
- `module_manifest`: Metadata, routing keywords, and health-check logic.
- `agent`: A `BaseAgent` subclass with task-specific tools.
- `router`: (Optional) FastAPI router for dashboard endpoints.

### 2. Configuration & Settings System
Kumio uses a dual-source configuration system:
1. **Redis (`kumio:settings:modules`)**: Stores the primary configuration (enabled state, connection parameters) gathered from the UI.
2. **Environment Variables**: Primary fallback and source for container-level configuration.
3. **Vault**: Secure storage for keys ending in `_PASSWORD`, `_TOKEN`, `_KEY`, or `_SECRET`.

**Gotcha**: Environment variables set via `_apply_module_connection` only persist for the current process lifetime. Therefore, modules should always use the `_get_<module>_config` pattern to read from Redis first, then Fallback to Env/Vault.

**Settings Save Merge Strategy**: When saving module settings, new connection values are **merged over** existing ones. Empty fields (e.g., a blank password input) do NOT overwrite previously saved values. This prevents password fields from being cleared every time the user clicks "Speichern" without re-entering the secret.

### 3. LLM Backend Configuration (Multi-Provider)
Kumio supports multiple LLM providers (Ollama, LM Studio, etc.) with a configurable default.

**Persistence Pattern**: Settings are stored in Redis under `kumio:settings:llm_providers` (a list of provider objects).
- **Startup**: `main.py`'s `lifespan` prioritizes the multi-provider list. It finds the provider with `is_default=True` and calls `_apply_default_provider()`.
- **Runtime**: Changing the default or updating a provider's settings trigger an immediate environment variable update (`_reconfigure_llm()`) so the `llm_factory` picks up the change without restart.

The `llm_factory.py` automatically adds `/v1` to the LM Studio base URL if it's missing.

### 4. AI Orchestration
The `OrchestratorAgent` does not have hardcoded module names. It uses the `routing_keywords` from manifests to decide which module agent to delegate a task to.

---

## 📦 Module Implementation Guide

To add a new module (e.g., `myservice`):
1. Create `backend/modules/myservice/`.
2. `schemas.py`: Define Pydantic models.
3. `tools.py`: Implement `@tool` functions.
4. `manifest.py`: Define `ModuleManifest`.
5. `agent.py`: Implement `MyServiceAgent(BaseAgent)`.
6. `routes.py`: Define API endpoints.
7. `frontend/`: Add `tab.html` and `tab.js`.
8. `__init__.py`: Export the manifest, agent, and router.

### Frontend Tab Rules
- **`tab.js` must NOT use ES module syntax** (`export`, `import`). The frontend dynamically appends `<script>` tags without `type="module"`, so ES module syntax causes a `SyntaxError: Unexpected token 'export'` that silently breaks the entire page.
- Use a **self-invoking IIFE** pattern instead: `(async function initMyTab() { ... })();`
- Use emoji-only icons (no FontAwesome classes) in `tab.html` and `manifest.py`, since FontAwesome is not loaded globally.

---

## 💻 Local Development Setup

### 1. Requirements
- Docker & Docker Compose
- Node.js (for frontend reference, though served by FastAPI)
- Python 3.12+ (for local linting/testing)

### 2. Running the Stack
```bash
docker compose up -d
```
The stack includes:
- `backend`: FastAPI app
- `redis`: Shared memory
- `vault`: Secrets management
- `chromadb`: Vector DB
- `ollama`: LLM backend (optional if using LM Studio)

### 3. Build & Deploy Cycle
After modified core backend or module files (including any changes to `frontend/` files):
```bash
docker compose build backend
docker compose up -d backend
```

> [!CAUTION]
> **CRITICAL RULE FOR AI AGENT**: You MUST rebuild the backend container (`docker compose up -d --build backend`) after **every single task** that modifies Python or frontend files. A simple `docker restart` is not enough, as frontend and backend files are baked into the image.

---

## 📝 Recent Development History

### Phase 19: Extended Automation & Centralized Logging (Feb 2026)
- **Task**: Integrated a new layer for structured automation (Workflows) and centralized oversight (Logs, Agents).
- **Agenten (Aufgaben)**: Generic agent definitions with system prompts and module-tool selection. This allows users to create specialized AI personas without touching Python code.
- **Workflow Engine**: Implementation of an asynchronous DAG execution engine.
    - **Node Types**: Trigger (Manual/Cron/Webhook), Agent (calls a specific AI task), Condition (Logic gate), Loop, Variable (Setter/Getter), and End.
    - **Persistence**: Workflows and their Run-States are stored in Redis.
- **Centralized Logging**: 
    - Implemented a custom `RedisLogHandler` that intercepts all Python logs.
    - Logs are stored in a capped Redis list (`kumio:logs`) for high-performance real-time access.
    - Frontend provides a unified Log Viewer with advanced filtering and search.
- **LLM Multi-Provider System**: Refactored the single-provider logic into a dynamic list of providers, allowing users to switch between different Models/Servers on the fly.

### Phase 12: IONOS DNS Module (Feb 2026)
- **Task**: Implemented IONOS Hosting DNS management (zone listing, record CRUD) via IONOS Hosting API.
- **API Base URL**: `https://api.hosting.ionos.com/dns/v1` (NOT `api.ionos.com` which is the Cloud API)
- **Auth**: `X-API-Key: prefix.secret` header. The key must be in the format `prefix.secret` (two parts separated by a dot) exactly as shown in the IONOS developer portal.
- **Records Endpoint Quirk**: `GET /zones/{id}/records` returns `401 Unauthorized` for standard API keys. The correct endpoint is `GET /zones/{id}` which returns a zone object with a `records` array embedded. Fixed in `tools.py:get_ionos_records`.
- **Tools registered**: `get_ionos_zones`, `get_ionos_records`, `add_ionos_record`, `update_ionos_record`, `delete_ionos_record`.
- **Frontend**: `tab.js` uses IIFE pattern (no ES module export). Icons use 🌐 emoji.

### Phase 12a: LLM Configuration Persistence Fix (Feb 2026)
- **Issue**: After each container restart, the backend defaulted to Ollama even if LM Studio was configured in the UI.
- **Root Cause**: `_reconfigure_llm()` only ran when users explicitly saved LLM settings, not on startup.
- **Fix**: Added a startup step in `main.py` (`lifespan`) that reads `kumio:settings:llm` from Redis and calls `_reconfigure_llm()` before any agents are initialized.
- **Additional Fix**: `llm_factory.py` now reads `LMSTUDIO_MODEL` from settings instead of hardcoding `"local-model"`. Added auto-appending of `/v1` suffix to the LM Studio URL.

### Phase 11a: Kubernetes Dashboard UI & Networking Fixes (Feb 2026)
- **Problem 1 (Routing):** K8s Ingress (Traefik) entfernte gelegentlich den Trailing-Slash bei Backend-Aufrufen (z.B. `/api/modules/`). Da FastAPI standardmäßig strikt den Pfad inklusive Slash verlangt, resultierte dies in statischen 404 Fehlern und unvollständigen JavaScript-Erfassungen.
  - **Lösung:** Alle dynamisch vom Frontend aufgerufenen FastAPI-Endpoints (`routes_modules.py` etc.) auf leere Endungen (`@router.get("")`) erweitert.
- **Problem 2 (Secure Context/UUID):** Der JavaScript-Aufruf `crypto.randomUUID()` zur Generierung der Chat-Session-ID wurde bei Aufruf des Dashboards über lokale HTTP-Netzwerkadressen (`http://kumio.conbro.local`) von modernen Browsern (Firefox/Chrome/Safari) als `undefined` blockiert. Dies brachte die UI komplett zum Absturz (ewiger "Verbinde..."-Websocket Zustand).
  - **Lösung:** Fallback auf `Math.random()`-basierte UUID-Generierung in ungesicherten Kontexten in `app.js` (`generateUUID`) integriert und IngressRoute auf `websecure` (HTTPS) erweitert.
- **Problem 3 (Frontend Architektur):** Das Binden von Sidebar-Klick-Events an die primären Navigationspunkte (Tasks, Agenten, Chat) erfolgte erst im `try...catch` Block des Modul-Ladevorgangs. Scheiterte dieser, war das gesamte Dashboard tot.
  - **Lösung:** Unabhängiges, unkonditionales Initialisieren der Core-UI-Eventlistener in `app.js`.

### Phase 11: Pi-hole Module Integration (Feb 2026)
- **Task**: Integrated Pi-hole v6 management (Blocking, Statistics, Query Log).
- **Technical Challenge**: Pi-hole v6 uses a session-based REST API with rate limiting.
- **Solution**: Implemented a robust `_authenticate` helper with:
    - Token caching (5 min TTL).
    - Session cleanup on `api_seats_exceeded` (429).
    - Retry logic with exponential backoff.
- **UI Integration**: Added a dedicated Pi-hole dashboard tab and configuration panel in Settings.
- **Local DNS Tools**: Added `get_custom_dns_records`, `add_custom_dns_record`, `remove_custom_dns_record`.

### Phase 10: Scheduler & Settings Bugfixes
- Fixed a bug where module connection parameters were not appearing in the settings UI.
- Hardcoded field mappings added to `frontend/app.js` and `backend/api/routes_settings.py`.
- Integrated a core scheduler for background tasks.

### Phase 13: Connection Profile Deletion and Duplication Fixes (Feb 2026)
- **Task**: Debugging and resolving connection duplication and deletion failures in the Settings UI.
- **Race Condition in UI**: Users clicking the "Save" button rapidly triggered parallel API requests, causing the backend to create duplicate connection profiles. Fixed by immediately disabling the button (`disabled = true`) upon interaction and re-enabling it in the `finally` block of the `saveConnection` Promise in `app.js`.
- **Silent 422 Errors on Creation**: Connection profiles failed to save entirely when selecting the "Lab" environment because `lab` was missing from the Pydantic `EnvironmentLabel` literal in `schemas/connection.py`. This resulted in broken profiles that couldn't be deleted because they never properly initialized in Redis/Vault. Fixed by adding `"lab"` to the schema.
- **Troubleshooting Scripting**: Verified Vault deletion behavior using an isolated Python backend script (`test_connection_bug.py`). Confirmed that `ConnectionManager.delete_connection()` was gracefully handling missing secrets, pointing the root cause toward the validation schema.

### Phase 14: Telegram Bot Integration & Connection Refactoring (Feb 2026)
- **Task**: Implementing a Telegram Bot to interact with Kumio from outside the local network.
- **Architecture**: The bot runs in a background task (`asyncio.create_task` inside `main.py` lifespan) using `httpx` long-polling on the `getUpdates` endpoint. It intercepts messages and proxies them to the `OrchestratorAgent`.
- **Connection Refactoring**: The `TELEGRAM_BOT_TOKEN` was originally loaded from standard HashiCorp Vault environment secrets, but this broke the modular architecture where *multiple* bots could exist. Refactored the bot to use the `ConnectionManager.get_default_connection("telegram")` instead. The token is now entered in the global dashboard Settings gear icon under the Telegram tab.
- **Chat History (Memory) Bug**: Telegram chat histories are tied to the Telegram User ID in Redis (`kumio:chat:telegram_<userid>`). Unlike the web GUI where refreshing the page assigns a new `session_id`, the Telegram session is persistent. If the agent hallucinated or got stuck in a connection error loop, it read its own error messages as truth and refused to try again.
- **Fix**: Added `/start`, `/clear`, `/reset` command hooks directly into `backend/modules/telegram/bot.py` to allow users to trigger an immediate `redis.clear_chat_history(session_id)`.

### Phase 15: FritzBox Routing Fix & Orchestrator Dynamic Matching (Feb 2026)
- **Issue**: The Orchestrator failed to route queries like "Wie ist meine externe ipadresse?" to the `fritzbox` module because it relied strictly on word boundaries (`\bip\b`). Since "ipadresse" merged the characters, the fallback LLM answered instead of calling the tool.
- **Fix**: Refactored `_detect_module()` in `backend/agents/orchestrator.py` to apply a two-step scanning process. 
  1. Strict `\b` word boundary search for short acronyms like `ip`, `vm`, `dns` to avoid false positives.
  2. Dynamic subspace matching for longer words (>= 4 characters). The orchestrator now strips all whitespace and punctuation (`[\W_]+`) from both the user prompt and the target keyword ("FRITZ!Box" -> "fritzbox"). This allows the algorithm to detect "fritzbox" even if the user types it with irregular punctuation.

### Phase 16: Rebranding & Design Overhaul (Feb 2026)
- **Task**: Global rename from earlier project name to **Kumio** and complete visual redesign.
- **Backend Rebranding**:
    - Logger root renamed to `kumio`.
    - Module environment variable prefix changed to `KUMIO_`.
    - Redis key prefix changed to `kumio:`.
    - Vault path prefix changed to `kumio/`.
- **UI Design ("Fox Armor")**:
    - **Light Mode**: High-contrast blue/white palette (#1A237E, #00B0FF).
    - **Dark Mode**: High-tech "Glowing" look with neon-cyan (#00D2FF) and purple (#9747FF) highlights.
    - **Logo Integration**: Replaced standard icons and illustrations with custom branding (`logo_dashboard.png`, `logo_icon.png`).
- **Gotcha**: The rename of environment variable prefixes requires a hard restart of the Docker stack and potentially manual updates to local `.env` files.

### Phase 17: Modular Sidebar & UX Refactoring (Feb 2026)
- **Task**: Refactored the main sidebar to support a modular "Modules" sub-menu.
- **Architectural Change**: Sidebar links are now dynamically grouped. Core links (Chat, Dashboard, Settings) remain top-level, while all discovered modules with a `dashboard_tab` are rendered inside a collapsible "Module" section.
- **Visual Fixes**: Improved the separator line in the chat sidebar to span the full width of the container.

### Phase 18: Kubernetes Deployment & Version Standardization (Feb 2026)
- **Task**: Deployed the full Kumio stack to MicroK8s (excluding `ollama`).
- **ChromaDB Alignment**: Identified that `chromadb/chroma:latest` uses a newer API version than standard LangChain/Chroma clients in Python 3.12. Standardized both server and client to **version 0.4.24**.
- **NumPy 2.0 Conflict**: Fixed `AttributeError: np.float_ was removed` by pinning `numpy<2.0.0` in `requirements.txt`.
- **Dockerfile Enhancement**: Added `build-essential` and `python3-dev` to the backend Dockerfile to allow compilation of `chroma-hnswlib` during the build process.
- **K8s Configuration**:
    - Service Type: `ClusterIP` (requires Ingress or NodePort for external access).
    - Resource Limits: Configured for stable operation on MicroK8s nodes.
    - Namespace: `kumio`.

---

## ⚠️ Lessons Learned & Troubleshooting

### Connection Validation (422 Unprocessable Entity)
- **Issue**: Profile seems to "save" in the UI but disappears on reload, or clicking "Delete" does nothing.
- **Cause**: The frontend sends an Environment string (e.g. `lab`) not allowed by the backend's strict `Literal` typing. FastAPI drops it with a 422 error, but the legacy frontend didn't display validation errors clearly.
- **Fix**: Always ensure frontend HTML select option values strictly map to the Backend Pydantic `Literal` typings.

### IONOS Records API – 401 on /zones/{id}/records
- **Cause**: The `/records` sub-endpoint requires elevated API key permissions which are not grantable via the UI.
- **Fix**: Use `GET /zones/{id}` instead. Records are embedded in the response as `zone.records[]`.

### IONOS API Key Format & Encoding Errors
- Must be `prefix.secret` (two parts separated by `.`).
- Create at [developer.hosting.ionos.de](https://developer.hosting.ionos.de).
- There are no per-endpoint permission settings – the key either has full DNS access or none.
- **Issue**: `'ascii' codec can't encode character '\u2014'` when sending `X-API-Key` headers.
- **Cause**: Sometimes copied API keys contain typographic characters like em-dashes (`—`) instead of standard hyphens (`-`). HTTPX expects strict ASCII for header values and will crash if the value contains unicode quotes/dashes.
- **Fix**: Sanitize the API key string in Python using `.replace("—", "-").strip()` before passing it into the HTTP headers.

### Missing Module Connection Data (Frontend to Backend)
- **Issue**: Module views drop connection or fail to load data, often using a "default" parameter that points to a misconfigured or missing connection.
- **Cause**: Frontend UI (`tab.js`) queries the backend via REST (e.g., `/api/pihole/summary`), but fails to append `?connection_id=...` parameters. The FastAPI endpoint was also missing the `connection_id: str = ""` parameter, preventing it from forwarding the context to the underlying `@tool` actions.
- **Fix**: Ensure all relevant FastAPI dashboard `/routes` accept a `connection_id: str = ""` query parameter and propagate it down to the tool (`module_tool.ainvoke({"connection_id": connection_id})`). Update the frontend script to append `?connection_id=` to all API fetch requests.

### Settings Password Fields Get Cleared on Save
- **Cause**: Browser sends empty string for password fields. Backend was overwriting Redis with `{ "IONOS_API_KEY": "" }`.
- **Fix**: `routes_settings.py:update_module_settings` now merges new values over existing ones. Only non-empty values overwrite stored values.

### LLM Backend Resets to Ollama After Restart
- **Cause**: `_reconfigure_llm()` only ran on settings save, not on startup.
- **Fix**: Added startup call in `main.py` `lifespan` to restore LLM settings from Redis before agents initialize.

### Frontend tab.js: Unexpected token 'export'
- **Cause**: Using ES module `export` syntax in a `<script>` tag loaded without `type="module"`.
- **Fix**: Replace `export async function initTab()` with an IIFE: `(async function init() { ... })();`

### Pi-hole v6 Auth (429 Too Many Requests)
- **Cause**: Repeated failed auth attempts or too many open sessions.
- **Fix**: Check `webserver.api.max_sessions` in Pi-hole config. In Kumio, ensure sessions are reused and old ones are deleted if possible.

### SVG Rendering in Workflow Canvas
- **Issue**: SVG edges (Bezier curves) appeared offset or remained invisible despite valid path data.
- **Coordinate Space**: `getBoundingClientRect()` includes page scroll and offsets that don't match the SVG overlay's origin.
- **Fix**: Always use `offsetLeft` and `offsetTop` relative to the shared container (`wf-canvas-container`).
- **Styling Isolation**: SVG elements sometimes fail to inherit CSS variables from the `:root` if injected via JS classes.
- **Best Practice**: Apply `stroke` and `fill` colors as explicit attributes in JS for visible SVG elements, especially for dynamic arrow markers.

### Persistence-Pattern (Settings)
- **Issue**: OS environment variables are not persistent after container restart if set via API.
- **Fix**: Always read from Redis `kumio:settings:modules` (and now `llm_providers`) as the source of truth for UI-configured values.

### ChromaDB: 410 Gone / Connection Refused in K8s
- **Issue**: Backend cannot connect to ChromaDB or receives `410 Gone`.
- **Cause**: Version mismatch between server (`latest`) and client library.
- **Fix**: Pin both to `0.4.24`. Also ensured `IS_PERSISTENT=TRUE` and mount path is correct (`/chroma/chroma` for 0.4.24).
- **NuPy Fix**: Pin `numpy<2.0.0` to avoid breaks in the ChromaDB initialization logic.

### K8s Frontend Access
- **Note**: The backend serves the frontend at port 8000. By default, it is a `ClusterIP`. To access it externally, change `k8s/backend/service.yaml` to `Type: NodePort` or configure a Traefik `IngressRoute`.

### Phase 23: Chat UI Avatar-Vereinheitlichung (März 2026)
- **Task**: Inkonsistente AI-Avatare in der Chat-UI ersetzt (drei verschiedene Icons je nach Message-Status) und die Typing-Bubble verkleinert.
- **Problem**: `addChatMessage()` nutzte ein SVG-Brain-Icon, `showTyping()` nutzte das 🧠-Emoji – beide mit lila hinterlegtem ``-Element, das dem Kumio-Logo-Stil nicht entsprach.
- **Fix (`app.js`)**: Beide Stellen (`avatarAi`-Variable und `showTyping()`) auf `<img src="/static/images/chat_logo.png" class="chat-avatar-img">` umgestellt.
- **Fix (`style.css`)**:
    - `.chat-message.ai .chat-avatar`: Hintergrund von `var(--accent-purple)` auf `transparent` geändert.
    - `.chat-avatar-img`: Neue Klasse, definiert `width/height: 32px`, `object-fit: contain`.
    - `#typing-indicator .chat-bubble`: `padding: 0.5rem 0.875rem`, `width: fit-content` – Bubble ist jetzt kompakt statt voll-breit.
- **Asset-Ablage**: `images/chat_logo.png` → `frontend/images/chat_logo.png` (ins Docker-Image gebacken, via FastAPI StaticFiles als `/static/images/chat_logo.png` erreichbar).

### Phase 22: ChromaDB Langzeitgedächtnis (März 2026)
- **Task**: Dem Core-Agent ein persistentes, sessionunabhängiges Langzeitgedächtnis über ChromaDB-Embeddings gegeben.
- **Auto-Memorize** (`base_agent.py`): Nach jeder Antwort läuft `_auto_memorize()` als **non-blocking** `asyncio.create_task`. Ein LLM-Call prüft, ob das Gespräch dauerhaft relevante Fakten enthält. Falls ja → `memory.store(category="agent_memory")`. Falls nein → der LLM antwortet `NICHTS` → kein Speichern. Kein Performance-Impact auf die Antwortzeit.
- **Neue Core-Tools** (registriert im `orchestrator.py`):
    - `remember_fact(fact)` – Explizites Speichern per User-Anweisung (`source="explicit_tool"`).
    - `recall_memory(query)` – Semantische Suche über `agent_memory` (top-5). Gibt dem Agent on-demand Zugriff auf sein Gedächtnis.
    - `forget_fact(fact)` – **Zweistufiger sicherer Lösch-Flow (Schritt 1)**: Sucht semantisch ähnliche Einträge und zeigt sie dem User als **Vorschau** an (kein Löschen). Gibt IDs und Inhalt zurück.
    - `confirm_forget(doc_ids)` – **Schritt 2**: Löscht die explizit bestätigten Einträge per ID. Wird erst nach User-Bestätigung aufgerufen.
- **Neue Methoden in `SemanticMemory`** (`core/memory.py`):
    - `delete(doc_id)` – Löscht direkt per ChromaDB-ID.
    - `delete_by_content(query, category, threshold)` – Sucht semantisch und löscht alle Treffer unterhalb des Distanz-Schwellenwerts.
- **Gotcha**: `asyncio.create_task` muss innerhalb eines laufenden Event-Loops aufgerufen werden (in FastAPI kein Problem). Exceptions in `_auto_memorize` werden bewusst als `DEBUG` geloggt und verschluckt, damit der Haupt-Request nie blockiert wird.

### Phase 21: UI Animations & Advanced CSS Branding (März 2026)
- **Task**: Integrierte `logo_dashboard_new.png` und erstellte eine pure-CSS glowing/pulsing Eye-Animation über das Cyber-Cat-Logo.
- **Responsive Positioning**: Prozentbasierte Koordinaten (`left`, `top`) relativ zum `.logo-wrapper` (560px max-width) statt Pixel-Werte.
- **Eye-Alignment-Korrektur**: Die Augen wurden nachträglich weiter auseinandergerückt und tiefer gesetzt:
    - `.eye-left`: `left: 44.5%` → `42.5%`, `top: 58%` → `59.5%`
    - `.eye-right`: `left: 55.8%` → `57.8%`, `top: 58%` → `59.5%`
- **CSS Animation Gotcha (`transform` property)**:
  - **Issue**: Die leuchtenden Augen benötigen `translate(-50%, -50%)` und `rotate(-15deg)`. Ein `@keyframes blink` mit `transform: scaleY()` überschreibt das `transform` komplett → Augen springen aus Position.
  - **Fix**: Unabhängige CSS-Properties `translate: -50% -50%;` und `rotate: -15deg;` verwenden. Diese werden von `@keyframes` nicht überschrieben.
- **Kubernetes UX**: Always rebuild the backend container (`docker compose up -d --build backend`) after tweaking CSS since static files are baked into the Python image.

### Phase 20: Multilingual Support (i18n) & Traefik Ingress (Feb 2026)
- **Task**: The entire UI and AI agent responses needed to be dynamically localized without page reloads.
- **Frontend Approach**: Created a lightweight Vanilla JS `I18n` class (`app.js`) overriding `[data-i18n]` text contents dynamically from JSON dictionaries (`de.json`, `en.json`, etc.).
- **Backend Approach**:
  - `routes_settings.py`: API endpoints to persist the language in standard Redis `kumio:settings:language` configuration and inject it as the `LANGUAGE` environment variable.
  - `BaseAgent.py`: Automatically injects `os.getenv("LANGUAGE", "de")` into the agent's core system prompt to enforce translated reasoning and responses.
- **Kubernetes Access**:
  - Replaced the simple ClusterIP instruction with a formal `traefik.containo.us/v1alpha1` `IngressRoute` configuration in `k8s/backend/ingressroute.yaml`.
  - Maps `kumio.conbro.local` directly to the `kumio-backend` ClusterIP on port 8000.

### ConnectionManager-Secrets nach PVC-Reset verloren
- **Issue**: Modul-Tools melden "Keine Standard-Verbindung konfiguriert" oder "API-Token fehlt", obwohl der User Verbindungen angelegt hat.
- **Ursache**: Connection-Metadaten (in Redis, eigene PVC) und Secrets (in SQLite `secrets.db`, auf `backend-data` PVC) sind entkoppelt. Wenn die `backend-data` PVC neu erstellt oder beim Erstellen der Connection noch nicht gemountet war, fehlen die Secrets – Redis hat aber noch die Metadaten mit `vault_keys`.
- **Fix**: Verbindung im UI neu anlegen (Einstellungen → Modul → Zahnrad → Verbindung bearbeiten, Secrets neu eingeben). Alternativ: Env-Var-Fallback (`IONOS_API_KEY`, `FRITZBOX_PASSWORD`, `HOMEASSISTANT_API_TOKEN`) in `k8s/backend/deployment.yaml` einkommentieren und als K8s-Secret hinterlegen.

### LangGraph Recursion-Limit (GRAPH_RECURSION_LIMIT)
- **Issue**: Agent antwortet mit langer LangGraph-Fehlermeldung über "Recursion limit of 25 reached".
- **Ursache 1**: Routing-Keyword zu generisch (z.B. `"aktuell"`) leitet zu viele Anfragen an einen Tool-intensiven Agenten.
- **Ursache 2**: LLM ruft ein Tool (z.B. `perform_web_search`) mehrfach auf, weil der System-Prompt keine Einschränkung vorgibt.
- **Fix**: Recursion-Limit auf 50 erhöht (`base_agent.py`). `GraphRecursionError` wird abgefangen. Routing-Keywords spezifisch halten (Phrasen statt Einzelworte). Im Agent-Prompt explizit schreiben: "Rufe das Tool genau EINMAL auf."

### Agent Langzeitgedächtnis – Cosine-Distanz Threshold
- **Issue**: `delete_by_content()` löscht alle Einträge, deren `cosine_distance <= threshold`. Bei zu kleinem Threshold (z.B. 0.1) werden kaum Einträge gelöscht (zu strikt). Bei zu großem (z.B. 0.5) werden thematisch verwandte, aber verschiedene Fakten versehentlich mitgelöscht.
- **Default**: `threshold=0.25` ist ein guter Ausgangswert für kurze Fakten-Sätze.
- **Auto-Memorize Qualität**: Die Qualität des automatischen Gedächtnisses hängt stark vom LLM-Modell ab. Kleinere Modelle (< 7B Parameter) tendieren dazu, `NICHTS` zu häufig oder zu selten zu antworten. Ggf. den Extraktions-Prompt anpassen.

### Phase 25: WebSearch K8s-Aktivierung & Modul-Env-Var-Fallbacks (März 2026)

#### WebSearch auf Kubernetes
- **Problem**: `KUMIO_MODULE_WEB_SEARCH` und `SEARXNG_URL` fehlten in `k8s/backend/deployment.yaml`. SearXNG-Manifeste (`k8s/searxng/`) waren vorhanden, aber das Backend kannte die URL nicht.
- **Fix**: `KUMIO_MODULE_WEB_SEARCH=true` und `SEARXNG_URL=http://searxng:8080` ergänzt. SearXNG k8s-Service heißt `searxng` (Port 8080), entspricht exakt der URL.

#### Env-Var-Fallback für IONOS, FritzBox, HomeAssistant
- **Problem**: Module nutzen `ConnectionManager.get_default_connection()` → wenn kein UI-Connection existiert (z.B. nach PVC-Reset), schlugen alle Tools mit `ValueError` fehl.
- **Ursache**: Die SQLite-Vault-Secrets (auf `backend-data` PVC) und die Redis-Connection-Metadaten sind entkoppelt. Wird die PVC neu erstellt oder war sie beim Erstellen der Connection noch nicht gemountet, sind die Secrets verloren – auch wenn Redis die Verbindungs-Metadaten noch hat.
- **Fix**: Alle drei Module greifen jetzt zuerst auf `ConnectionManager`, dann auf Env-Vars als Fallback zurück:
  - IONOS: `IONOS_API_KEY`
  - FritzBox: `FRITZBOX_HOST`, `FRITZBOX_USER`, `FRITZBOX_PASSWORD`
  - HomeAssistant: `HOMEASSISTANT_URL`, `HOMEASSISTANT_API_TOKEN`
- Kommentierte Beispiel-Blöcke in `k8s/backend/deployment.yaml` ergänzt (zeigen, wie man sie via `kumio-secrets` K8s-Secret einbindet).
- **Fehlermeldungen verbessert**: Statt missverständlichem "Bitte IONOS_API_KEY in den Modul-Einstellungen setzen" gibt es jetzt eine klare Anleitung mit beiden Konfigurationspfaden.

### Phase 26: LangGraph Recursion-Limit Fix & WebSearch-Routing-Verfeinerung (März 2026)

#### Problem
Der WebSearch-Agent lief in eine Endlosschleife: Das Routing-Keyword `"aktuell"` in `web_search/manifest.py` matchte jede Frage, die "aktuell" enthält (z.B. "wie hoch ist der aktuelle Bitcoin-Preis"). Der `WebSearchAgent` rief dann `perform_web_search` mehrfach auf (verschiedene Suchvarianten) bis LangGraphs Standard-Recursion-Limit von 25 erreicht war.

#### Fixes
1. **`recursion_limit` auf 50 erhöht** in `base_agent.py:ainvoke(config={"recursion_limit": 50})`.
   - Jeder Agent hat seinen eigenen separaten LangGraph-Graphen – Limits addieren sich nicht wenn der Orchestrator an ein Modul weiterleitet.
   - 50 Steps ≈ 16–25 Tool-Calls, ausreichend für alle realistischen Multi-Step-Tasks.
2. **`GraphRecursionError` sauber abgefangen** in `base_agent.py` – erkennt die Exception an `"GRAPH_RECURSION_LIMIT"` im Fehlertext, gibt eine benutzerfreundliche deutsche Meldung zurück.
3. **Routing-Keyword `"aktuell"` entfernt** aus `web_search/manifest.py` – zu generisch. Ersetzt durch spezifische Phrasen: `"aktueller preis"`, `"aktuelle kurse"`, `"aktuelle news"`, `"was kostet"`, `"wie teuer"`.
4. **WebSearch-Agent-Prompt angepasst**: Explizite Instruktion, `perform_web_search` genau EINMAL aufzurufen und danach direkt zu antworten.

### Phase 27: Soul System – Persistente Agenten-Identitäten (März 2026)
- **Task**: Jeder Agent erhält eine unveränderliche „Seele" (Soul MD), die seine Rolle, Fähigkeiten und Verhaltensregeln definiert.
- **`SoulManager`** (`core/soul_manager.py`): Singleton, geladen beim Start nach ModuleRegistry, vor SkillsManager. Lädt built-in Souls aus `backend/souls/` und dynamische Souls aus Redis (`kumio:souls`).
- **Injection**: In `base_agent.invoke()` wird die Soul MD an den Anfang von `final_system_prompt` gesetzt (vor RAG, Skills, Sprachanweisung).
- **Auto-Generierung**: Modul-Souls werden beim Start generiert wenn keine existieren. Dynamische Agenten-Souls werden bei `DynamicAgentPool.register()` aus dem System-Prompt extrahiert.
- **Kumio-Seele**: `backend/souls/kumio.md` – wird in den Orchestrator injiziert (`name="orchestrator"`).

### Phase 28: Skills-System & GUI (März 2026)
- **Task**: Prozedurales Domänenwissen (how-to, step-by-step) in SKILL.md-Dateien persistieren und automatisch in passende Agenten-Kontexte injizieren.
- **`SkillsManager`** (`core/skills_manager.py`): Lädt aus `backend/skills/` (built-in) und `data/skills/` (hot-reload). Injiziert max. 2 Skills per Request als SystemMessage (threshold 12%).
- **`install_skill` Tool**: Der Orchestrator kann Skills direkt aus dem Chat installieren – schreibt SKILL.md nach `data/skills/` und ruft `SkillsManager.reload()` auf.
- **Skills GUI**: `GET/POST/PUT/DELETE /api/skills/` via `routes_skills.py`. Frontend: Skills-Panel, Editor-Panel, Sektion im Agent-Sidebar.
- **Built-in Skills**: `kubernetes-incident-response`, `pihole-session-management`, `ionos-dns-quirks`, `proxmox-troubleshooting`.

### Phase 29: LM Studio Jinja-Template-Kompatibilität (März 2026)
- **Problem**: LM Studio's eingebettetes Jinja2 kennt den `is sequence`-Test nicht → drei verschiedene HTTP-400-Fehler.
- **Fix 1** (`_NormalizingChatOpenAI`): Normalisiert Listen-Content zu String (gilt für `openai_compatible` + `lmstudio`).
- **Fix 2** (`_inject_tools_into_system`): Injiziert Tool-Definitionen als Markdown-Text in die SystemMessage, da Template-Tool-Injektion still fehlschlägt und das Modell `example_function_name` aufruft.
- **Fix 3** (`_convert_tool_messages_to_text`): Konvertiert `AIMessage(tool_calls=[...])` → `<tool_call>`-Format und `ToolMessage` → `<tool_response>` HumanMessage. Qwen3.5 ist auf dieses XML-Format trainiert.
- **Thinking-Modell-Support**: `_strip_thinking()` in `base_agent.py` entfernt `<think>...</think>`-Blöcke. Alle direkten LLM-Calls via `[HumanMessage(content=...)]` für Thinking-Modell-Kompatibilität.

### Phase 30: LLM-basiertes Modul-Routing (März 2026)
- **Motivation**: Keyword-Matching ist spröde bei deutschen Komposita, semantisch ähnlichen Anfragen und neuen Modulen ohne passende Keywords.
- **Zweistufige `_detect_module()`** (jetzt async):
  1. **Keyword-Schnellpfad**: Genau 1 Modul → sofort Tier 2, kein LLM-Call.
  2. **LLM-Klassifikation** (bei Score=0 oder Ambiguität ≥2 Module): `asyncio.wait_for(timeout=8s)`, System+User-Prompt via `_t(de, en)`.
- **`_build_module_descriptions()`**: Dynamisch aus `manifest.description` + ersten 5 Keywords gebaut – kein Hardcoding.
- **Cache**: MD5-Hash der Nachricht → TTL 60s, Auto-Purge bei >500 Einträgen.
- **Ambiguität-Auflösung**: LLM entscheidet ob echtes Compound (→ Tier 4) oder nur ambige Keywords (→ Tier 2).
- **`_classify_tier()` ebenfalls async** – `route()` awaitet den Call.

### Phase 31: Chat-UI Verbesserungen (März 2026)
- **AI-Bubble breiter**: `.chat-message.ai .chat-bubble-group { max-width: 90% }` (User bleibt bei 70%).
- **Tabellen scrollbar**: `.chat-bubble table { display: block; overflow-x: auto; width: max-content }` – breite Tabellen scrollen horizontal, kein Clipping mehr.
- **Textarea-Scrollbar ausgeblendet**: `scrollbar-width: none` + `::-webkit-scrollbar { display: none }` auf `.chat-input` – native Scrollbar nicht mehr sichtbar, Scrollen funktioniert weiterhin.

---

## 📅 Maintenance
- Update `ModuleManifest` version on breaking changes.
- Ensure `routing_keywords` remain unique enough to avoid orchestrator confusion.
- Document new tools in `tools.py` docstrings (Agent uses them for reasoning!).
- When adding secret fields (e.g., `_KEY`, `_PASSWORD`, `_TOKEN`, `_SECRET`), register them in `routes_settings.py:_get_secret_keys()` and add the module name to `_get_env_connection()`.



