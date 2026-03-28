# Changelog

All notable changes to Ninko are documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.5.10] – 2026-03-28

### Changed

- **Sidebar navigation redesign** (`frontend/index.html`, `frontend/app.js`, `frontend/style.css`) — Streamlined sidebar layout:
  - **"New Chat" nav button** — The top "Chat" tab is now labelled "New Chat" (i18n: `chat.newChatBtn`) and clicking it always opens a fresh conversation instead of just switching to the chat view.
  - **Removed "History" section header** — The "Verlauf" label and the pencil icon button have been removed; the chat history list now fills the sidebar directly without a header bar.
  - **Status indicator moved to header** — The connection status dot (`status-dot`) is now displayed in the top-right corner of the primary sidebar header. The status text label and the sidebar footer have been removed entirely.
  - **Settings in main nav** — The "Settings" entry replaces "Logs" in the bottom navigation (gear icon, i18n key `nav.settings`). All 10 language files updated.
  - **Logs moved into Settings** — Logs are now accessible via **Settings → Logs** in the settings sidebar. The logs panel renders full-height inside the settings layout (CSS `:has()` override). Log polling starts/stops correctly when switching into or away from the logs settings sub-panel (`switchSettingsTab` + `switchTab` updated in `app.js`).
- **Automatisierung and Modules two-column layout** (`frontend/index.html`, `frontend/app.js`, `frontend/style.css`) — Both navigation entries now open a settings-style two-column layout instead of slide-in secondary sidebar panels:
  - Clicking "Automatisierung" shows a left sidebar with Tasks / Agents / Workflows sub-items and loads the selected panel into the right content area.
  - Clicking "Modules" shows a left sidebar with all enabled module tabs (dynamically built by `loadModules()`) and loads the selected module panel into the right content area.
  - Existing `#tab-tasks`, `#tab-agents`, `#tab-workflows`, and module tab panels are physically moved via `appendChild` into `#auto-content` / `#modules-content` — preserving all existing event listeners without duplicating HTML.
  - Old slide-in sidebar panels (`sidebar-panel-automatisierung`, `sidebar-panel-secondary`) and their back-button logic removed entirely.
  - `switchTab()` now delegates `tasks`/`agents`/`workflows` calls through `switchAutoTab()`; `switchModuleTab()` manages module panel activation. Workflow run-refresh timer cleaned up on both sub-tab and main-tab switches.
  - CSS: `.auto-content` flex container with `min-height: 0` ensures Workflow canvas retains correct full-height behaviour.

---

## [0.5.9] – 2026-03-28

### Added

- **Module Pre-Selection Button** (`frontend/index.html`, `frontend/app.js`, `frontend/style.css`, `backend/schemas/chat.py`, `backend/agents/orchestrator.py`, `backend/api/routes_chat.py`) — Pill button next to the "New Chat" title in the chat toolbar:
  - Dropdown lists all enabled modules; "Auto" option resets to standard orchestrator routing
  - When a module is pre-selected, the button is highlighted in blue and all messages in the session are routed directly to that module (bypasses the full Tier 1–4 analysis)
  - Backend: `ChatRequest.force_module: str | None` — new optional field; `orchestrator.route(force_module=...)` checks for direct module routing before `_classify_tier()`
  - Safeguard still fires before `force_module` routing takes effect
  - i18n: `chat.modulePickerTitle` + `chat.moduleAuto` in all 10 language files (DE/EN/FR/ES/IT/PT/NL/PL/ZH/JA)

### Fixed

- **Safeguard false-positive on read-only tool calls** (`backend/core/safeguard.py`) — `_TOOL_READONLY` frozenset was incomplete and contained stale tool names from older module versions. Every status query (e.g. `get_fritz_system_info`, `ha_list_entities`, `read_emails`) was blocked by the safeguard LLM classifier. Comprehensive overhaul: all 6 missing modules added (Docker, Linux Server, OPNsense, Tasmota, Qdrant, Codelab), all wrong names corrected across all existing modules (Proxmox, Home Assistant, IONOS, Email, GLPI, WordPress, Kubernetes, Pi-hole). Rule documented in `_template/tools.py`: `get_*`, `list_*`, `search_*`, `inspect_*`, `check_*` → read-only → must be in `_TOOL_READONLY`.
- **Duplicate user message on safeguard confirmation** (`frontend/app.js`) — When the user confirmed a safeguard warning and `sendMessage()` was called a second time, `addChatMessage('user', text)` was called again, inserting a second user bubble. Fixed by reading `_confirmedPending` before the DOM update and skipping `addChatMessage` for confirmation re-sends.
- **Module picker button too small** (`frontend/style.css`, `frontend/index.html`) — Button padding increased from `0.2rem/0.5rem` to `0.32rem/0.75rem`, font size from `0.78rem` to `0.84rem`, icons from 13 px to 15 px.

---

## [0.5.8] – 2026-03-28

### Security

- **Tool-level safeguard** (`backend/core/safeguard.py`, `backend/agents/base_agent.py`, `backend/agents/orchestrator.py`, `backend/api/routes_chat.py`, `backend/main.py`) — The safeguard now also intercepts LLM tool calls, not just user messages:
  - All agents (module agents, orchestrator, dynamic agents) run with `interrupt_before=["tools"]` + LangGraph `MemorySaver` when safeguard is enabled
  - Before each tool execution, `check_tool_call(tool_name, tool_args)` classifies the call using the same SAFE / STATE_CHANGING / DESTRUCTIVE pipeline as user messages
  - Read-only tools (`_TOOL_READONLY` frozenset) are always allowed instantly without an LLM classifier call — no latency overhead for safe operations
  - For `call_module_agent`: the delegated `message` argument is classified (not the tool name), catching dangerous actions delegated through the orchestrator
  - For `execute_cli_command`: the `command` string is classified directly
  - If a tool requires confirmation: execution pauses, the agent state is held in `_paused_sg_agents` (module-level dict), a Redis key `ninko:safeguard_tool_pending:{session_id}` (TTL 300s) is written, and a `__TOOL_SAFEGUARD__` sentinel is returned
  - The chat route detects the sentinel and returns `confirmation_required=True` with tool details
  - On the next request with `confirmed=true`, the route checks for a pending tool key first and resumes the paused agent via `orchestrator.resume_tool_execution(session_id)`
  - Multiple consecutive dangerous tool calls each trigger their own confirmation round
  - Pipeline sub-steps (Tier 4) remain unprotected at tool level — consistent with the existing design (safeguard guards the initial user message for pipelines)

### New Modules

- **OPNsense module** (`backend/modules/opnsense/`) — Firewall management and monitoring via OPNsense REST API:
  - `get_opnsense_system_status` — system info, uptime, version
  - `get_opnsense_interfaces` — all interface configurations and states
  - `get_opnsense_gateways` — gateway status and latency
  - `get_opnsense_firewall_rules` — firewall rules, optionally filtered by interface
  - `get_opnsense_nat_rules` — NAT / port-forward rules
  - `get_opnsense_services` — running service states (unbound, haproxy, etc.)
  - `get_opnsense_dhcp_leases` — DHCP lease table with IP/MAC/hostname
  - `restart_opnsense_service` — restart a named OPNsense service
  - `get_opnsense_logs` — recent system log lines
  - Authentication: API key + API secret via Vault; HTTPS with optional cert verification skip
  - Routing keywords: `opnsense`, `firewall`, `nat`, `portforward`, `wan`, `lan`, `dhcp`, `vpn`, `ipsec`, `wireguard`, `pf`, …

- **Tasmota module** (`backend/modules/tasmota/`) — Control and monitoring of Tasmota-flashed IoT devices (ESP8266/ESP32) via HTTP REST API:
  - `get_tasmota_status` — full device status (firmware, uptime, IP, signal)
  - `get_tasmota_power` — current power state of all relays
  - `set_tasmota_power(state, relay)` — switch relay on/off/toggle
  - `get_tasmota_sensors` — temperature, humidity, energy/power readings
  - `get_tasmota_wifi_info` — Wi-Fi SSID, RSSI, channel, IP
  - `send_tasmota_command(command)` — send arbitrary Tasmota console command
  - Authentication: plain HTTP (optional username/password configurable)
  - Routing keywords: `tasmota`, `esp8266`, `esp32`, `sonoff`, `shelly`, `steckdose`, `relais`, `stromverbrauch`, `sensor`, …

---

## [0.5.7] – 2026-03-27

### UI/UX

- **Settings as tab instead of modal** (`frontend/index.html`, `frontend/app.js`, `frontend/style.css`) — The settings menu no longer opens in a separate modal window but renders directly in the main content area, just like Chat, Logs, and all other tabs. The gear button now calls `switchTab('settings')`; `toggleSettings()` is kept as a backwards-compatible alias.

- **Chat layout: centered, no avatars** (`frontend/app.js`, `frontend/style.css`) — Redesigned chat layout inspired by modern chat interfaces:
  - User and AI avatars/icons removed entirely (no fox icon, no user SVG)
  - AI responses rendered as plain flowing text with no bubble background or border
  - User messages displayed as compact bubbles (max 70% width), right-aligned within the centered column
  - All messages laid out in a centered column (max 760px) — no more left-aligned sidebar-style layout
  - Typing indicator also removed avatar and box styling

---

## [0.5.6] – 2026-03-26

### Features

- **Kubernetes write operations** (`backend/modules/kubernetes/`) — Module extended with full create/apply/delete/inspect capabilities:
  - `apply_manifest(yaml_content, namespace)` — create or update any resource from a YAML string via server-side apply; supports multi-document YAML (`---`)
  - `delete_resource(kind, name, namespace, api_version)` — delete any resource by kind/name using the dynamic client
  - `get_resource_yaml(kind, name, namespace, api_version)` — retrieve the live YAML of any resource (managed fields stripped)
  - `create_namespace(name, labels)` — create a new namespace
  - `list_deployments(namespace)` — list deployments with replica counts and image info
  - Agent system prompt updated: instructs the agent to use `apply_manifest` for creation requests and to act directly on test/dev resources without asking

### Improvements

- **Safeguard: multilingual keyword pre-filter** (`backend/core/safeguard.py`) — Pre-filter extended from DE/EN to all 10 supported languages. 41/41 test cases pass without LLM call:
  - FR: `supprim/efface/enlève` (destructive), `crée/déploi/modifie/mets à jour` (state-changing), `montre/affiche` (safe)
  - ES: `elimin/borrar/destruy` (destructive), `crea/despleg/actualiz/reinici` (state-changing), `muestra/lista` (safe)
  - IT: `cancell/rimuovi/svuota` (destructive), `crea/aggior/modifica/riavvia` (state-changing), `mostra/elenca` (safe)
  - PT: `apagar/destrói/limpar` (destructive), `cria/atualiz/reinici` (state-changing), `mostra/lista` (safe)
  - NL: `verwijder/verniet/wis` (destructive), `aanmaken/maak/implementeer` (state-changing), `toon/lijst` (safe)
  - PL: `usuń/skasuj/zniszcz` (destructive), `utwórz/wdróż/zaktualizuj` (state-changing), `pokaż/wylistuj` (safe)
  - ZH: `删除/清除/移除/销毁` (destructive), `创建/部署/更新/配置` (state-changing), `显示/列出/查看` (safe)
  - JA: `削除/消去/削除して` (destructive), `作成/デプロイ/設定/変更` (state-changing), `表示/一覧/確認` (safe)
- **Safeguard: full English rewrite** — All comments, docstrings, and log messages translated to English. Import order fixed (previously `_keyword_prefilter` referenced `SafeguardResult` before it was defined).
- **Safeguard: hardened parser** — `_parse()` strips `<think>` blocks, markdown fences, and extracts JSON from prose. Enforces category/violation consistency: `DESTRUCTIVE`/`STATE_CHANGING` always set `violation=1`, `SAFE` always `violation=0`.
- **Safeguard: `del` false-positive removed** — `"del"` removed from destructive terms; it is a common preposition in ES/IT/FR ("del pod" = "of the pod").
- **Safeguard: pre-filter threshold raised** — Short-message fast-path raised from 120 to 200 chars.

### Bug Fixes

- **K8s Redis migration** — All `kumio:*` Redis keys copied to `ninko:*` after project rename. Affected: all module connections (11), agents, souls, settings (5), workflows.
- **K8s env vars** — Live cluster still had `KUMIO_MODULE_*` environment variables; patched to `NINKO_MODULE_*` via `kubectl patch`. FritzBox and all other modules are now visible again.

### Infra

- Docker build + DEV deploy (docker-compose) ✅
- Push `natorus87/ninko-backend:latest` + `natorus87/kumio-backend:latest` ✅
- K8s rollout `kumio-backend` in namespace `kumio` ✅

---

## [0.5.5] – 2026-03-26

### Features

- **Safeguard toggle in Agent editor** (`frontend/index.html`, `frontend/app.js`) — The Agent editor now has a Safeguard toggle in the "General" section below the "Active" toggle. `openAgentEditor()` loads the per-agent state via `GET /api/safeguard/agents/{id}` and sets the checkbox accordingly. `saveAgent()` persists the value after saving via `POST /api/safeguard/agents/{id}/enable|disable`. i18n key `agent.safeguardLabel` added for all 10 languages.

### Infra

- Docker build + DEV deploy (docker-compose) ✅
- Push `natorus87/ninko-backend:latest` + `natorus87/kumio-backend:latest` ✅
- K8s rollout `kumio-backend` in namespace `kumio` ✅

---

## [0.5.6-r1] – 2026-03-27

### Repo

- **K8s manifest split** — `k8s/` cleaned of personal data (private IP, internal hostname, model names, SearXNG secret); all replaced with neutral placeholders. New `k8s-conbro/` folder holds the personal live-cluster configuration and is excluded via `.gitignore`. The public `k8s/` folder remains the canonical template for new deployments.

---

## [0.5.4] – 2026-03-26

### Features

- **Safeguard middleware** (`backend/core/safeguard.py`) — LLM-based classifier that checks every user input before the 4-tier routing. Categories: `SAFE`, `DESTRUCTIVE`, `STATE_CHANGING`. Fail-safe: on timeout or parse error, confirmation is always required. Timeout 8s, temp=0.0, max_tokens=150.
- **AgentConfigStore** (`backend/core/agent_config_store.py`) — Redis-backed per-agent settings (hash key `ninko:agent_configs`). Stores `safeguard_enabled` per agent ID, extensible for future settings.
- **Safeguard API** (`backend/api/routes_safeguard.py`) — Global toggle (`GET/POST /api/safeguard/status|enable|disable`) and per-agent toggle (`GET/POST /api/safeguard/agents/{id}/...`). Global state persisted in Redis (`ninko:settings:safeguard`) and restored on startup.
- **Safeguard in chat endpoint** (`backend/api/routes_chat.py`) — Safeguard check before `orchestrator.route()`. If `requires_confirmation` and `confirmed=false` in the request: immediate return with `confirmation_required=true` and `safeguard` dict. `status_bus.done()` is always called even on early return.
- **Safeguard for Telegram bot** (`backend/modules/telegram/bot.py`) — Pending-confirmation flow: on destructive action the message is stored in Redis (`ninko:safeguard_pending:{session_id}`, TTL 300s) and the user is prompted to confirm. Replying with "ja/yes/bestätigen/ok/confirm" executes the stored action; any other reply starts a fresh normal flow.
- **Safeguard for Teams bot** (`backend/modules/teams/bot.py`) — Identical pending-confirmation logic as Telegram, using Teams Markdown instead of Telegram HTML.

### Changes

- **`ChatRequest`** (`backend/schemas/chat.py`) — New field `confirmed: bool = False` for explicit confirmation of destructive actions.
- **`ChatResponse`** (`backend/schemas/chat.py`) — New fields `confirmation_required: bool = False` and `safeguard: dict | None = None` for frontend evaluation.
- **`llm_factory.py`** (`backend/core/llm_factory.py`) — New function `get_safeguard_openai_client()` returns `(AsyncOpenAI, model_name)` for the active LLM provider.
- **`main.py`** — Safeguard init in lifespan (after SkillsManager, before DynamicAgentPool), Redis state restore, `safeguard_router` registered.

### Infra

- Docker build + DEV deploy (docker-compose) ✅
- Push `natorus87/ninko-backend:latest` + `natorus87/kumio-backend:latest` ✅
- K8s rollout `kumio-backend` in namespace `kumio` ✅

---

## [0.5.3] – 2026-03-26

### Features

- **Workflow run dashboard: live canvas** (`frontend/`) — The run dashboard now shows the same node canvas as the editor, but read-only with live status overlays:
  - `pending` — dimmed nodes (40% opacity)
  - `running` — amber pulsing glow + blinking status pip (●)
  - `succeeded` — green border + green pip
  - `failed` — red border, red background tint + red pip
  - `skipped` — greyed out + grayscale filter
  - Duration (ms) displayed below the node label
- **Workflow run dashboard: inline inspector** — Clicking a node opens a right panel with status badge, duration, error box and full agent output (monospace).
- **Workflow run dashboard: compact run history** — Bar at the bottom; clicking a previous run overlays the canvas with its step data.
- **Workflow run dashboard: progress indicator in toolbar** — Progress bar and step counter (`X / Y steps`) in the toolbar, next to the back button and status badge.

### Infra

- **K8s namespace still `kumio`** — Deployment runs in namespace `kumio` as `kumio-backend`, using image `natorus87/kumio-backend:latest`. Image is pushed under both names (`natorus87/ninko-backend:latest` + `natorus87/kumio-backend:latest`) until namespace migration is complete.

---

## [0.5.2] – 2026-03-25

### Bug Fixes

- **Workflow editor: `saveWorkflow` emoji regression** (`app.js`) — `finally` block set `'💾 Speichern'` instead of the original `'Speichern'` — button label was wrong after every save.
- **Workflow editor: inspector title frozen** (`app.js`) — `_wfUpdateNode()` called `_wfRenderCanvas()` (canvas correct) but did not update `#wf-inspector-title` (a separate DOM element outside the canvas). Label changes in the inspector were not reflected in the title. Fix: explicit `innerHTML` update of the title after `_wfRenderCanvas()`.
- **Workflow editor: description always empty** (`app.js`) — `saveWorkflow()` had `description: ''` hardcoded. When loading an existing workflow, `wf.description` was never transferred to the form. Both fixed: field `#wf-desc-input` is populated on load and read on save.

### Features

- **Workflow palette buttons: type colors and icons** (`index.html`, `style.css`) — Each node type (Trigger, Agent, Condition, Loop, Variable, End) now has a matching emoji icon and a colored left border (`wf-palette-trigger/agent/...`) matching the canvas node colors. Tooltips (`title` attributes) with short descriptions added.
- **Workflow connection mode: visual feedback** (`app.js`, `style.css`) — Source node pulses amber while connecting (`.wf-node-connecting`) instead of just a cursor change. Class is removed on completion or cancellation of the connection (in `_wfStartConnection` and `_wfSelectNode`).
- **Workflow cards: delete button** (`app.js`) — Delete button now has `title="Delete"` and an explicit text label, consistent with other card types (Agents, Scheduler tasks).
- **Workflow editor: description field** (`index.html`) — New input field `#wf-desc-input` directly below the workflow name. Populated when opening an existing workflow and read on save.
- **Workflow canvas hint: more precise text** (`index.html`) — Now concretely describes the two steps: palette selection and port connection.

---

## [0.5.1] – 2026-03-25

### Bug Fixes

- **`_MEMORIZE_STOP_WORDS` as local variable** (`base_agent.py`) — The set was recreated on every `_auto_memorize()` call. Now defined as a module-level constant next to `_MEMORIZE_EXCLUDED_AGENTS`.
- **`_strip_thinking()` recompiled regex on every call** (`base_agent.py`) — `import re` inside the function body + uncompiled pattern. Now `_RE_THINK = re.compile(...)` as a module constant, `import re` at the top of the file.
- **UTF-8 decode without `errors='replace'`** (`core_tools.py`) — `stdout.decode('utf-8')` crashes on non-UTF-8 output (e.g. `cat` on binary files). Now `decode('utf-8', errors='replace')` for both stdout and stderr.
- **Tier-2 error format incompatible with `_err_prefixes`** (`orchestrator.py`) — Module agent errors in `route()` started with `"Das Modul ... hat einen Fehler"` instead of `"Fehler:"`. `run_pipeline` would not have aborted the pipeline. Now `"Fehler: ..."` / `"Error: ..."`.
- **`asyncio.get_event_loop()` deprecated** (`base_agent.py`) — Replaced with `asyncio.get_running_loop()`.
- **`type("", (), {"display_name": module})()` hack** (`core_tools.py`) — Replaced with a simple `manifests[module].display_name if module in manifests else module`.
- **`orchestrator.route()` return value unpacking in scheduler** (`scheduler_agent.py`) — `route()` returns `tuple[str, str | None, bool]` (3 values) but the scheduler unpacked only 2 → `ValueError`. Now correctly `response_text, module_used, _ = await self.orchestrator.route(...)`.

### Features

- **Scheduler: custom agent as task type** — Scheduled tasks can now invoke a dynamic agent from `DynamicAgentPool` (in addition to prompt and workflow).
  - `agent_id` field in `ScheduledTaskCreate`, `ScheduledTaskUpdate`, `ScheduledTaskInfo` (`schemas/scheduler.py`)
  - `DynamicAgentPool.get_agent_by_id(agent_id)` — new method in `core/agent_pool.py`
  - `_execute_task()` in `scheduler_agent.py`: new `elif agent_id:` branch
  - Frontend: radio button "Call custom agent" + `#sched-agent-row` with agent dropdown + optional prompt field
  - Task card shows agent badge (purple, `.task-badge-agent` in `style.css`) analogous to the workflow badge
- **Scheduler: workflow dropdown bug fixed** — `loadScheduledTasks()` returned early when `tasks.length === 0`, before the workflow and agent dropdowns were populated. Now all three API calls run in parallel via `Promise.all` and dropdowns are always populated before the early-return check.

---

## [0.5.0] – 2026-03-24

First public release. Ninko is a modular, AI-powered IT operations platform built on FastAPI (Python 3.12) with an immutable core and auto-discovering modules.

### Core Architecture

- **Modular auto-discovery system** – `ModuleRegistry` scans `backend/modules/` and `backend/plugins/` at startup, registers agents, routers, and keywords. No module names hardcoded in core.
- **4-tier orchestrator routing** (`orchestrator.py`):
  - Tier 1 – Direct answer (simple queries, < 120 chars, no action verbs)
  - Tier 2 – Module agent delegation via two-stage keyword + LLM routing
  - Tier 3 – Dynamic agent (pool lookup or LLM-generated agent spec)
  - Tier 4 – Deterministic pipeline routing for multi-module tasks
- **LLM-based module routing** – `_detect_module()` (async, two-stage): keyword fast-path + LLM classification at Score=0 or ambiguity. MD5 cache (TTL 60s), 8s timeout, full fallback.
- **Dynamic Agent Pool** – `DynamicAgentPool` with Redis persistence, Jaccard scoring (threshold 18%), 4 base tools for Tier-3 agents.
- **Workflow Engine** – Async DAG with Trigger, Agent, Condition, Loop, Variable, End nodes. State stored in Redis.
- **LLM Factory** – Multi-provider: `ollama`, `lmstudio`, `openai_compatible`. Auto `/v1` append, context window auto-detection, `MAX_OUTPUT_TOKENS=16384`.

### AI Capabilities

- **Soul System** – Persistent agent identities (Soul MDs). Built-in: `backend/souls/`. Dynamic: Redis `ninko:souls`. Injected before RAG/Skills/language in `final_system_prompt`.
- **Skills System** – SKILL.md format with YAML frontmatter. Hot-reload via `install_skill` tool. Max 2 skills/request injected (threshold 12%). GUI: `GET/POST/PUT/DELETE /api/skills/`.
- **Long-term memory** – ChromaDB-backed `SemanticMemory`. Tools: `remember_fact`, `recall_memory`, `forget_fact` (preview flow), `confirm_forget`. Auto-memorize with cooldown (60s) and agent exclusions.
- **Context compaction** – LLM summary when context window budget exceeded (25% of model window). Compaction summary preserved as SystemMessage. Frontend notification `⟳`.
- **JIT tool injection** – With > 6 tools: max 8 context-relevant tools per request, keyword match against name + docstring (min 2 chars).

### LM Studio / Thinking Model Compatibility

- **`_NormalizingChatOpenAI`** – Normalizes list content to string (Jinja `is sequence` bug).
- **`_LMStudioChatOpenAI`** – Additionally: `_inject_tools_into_system()` (tool defs as text), `_convert_tool_messages_to_text()` (XML `<tool_call>`/`<tool_response>` format for Qwen3.5).
- **`_strip_thinking()`** – Removes `<think>...</think>` blocks from thinking model responses.
- All direct LLM calls via `[HumanMessage(content=...)]` for strict Jinja template compatibility.

### Internationalization (i18n)

- `_t(de, en)` + `_get_language()` in `base_agent.py`, importable in `orchestrator.py`.
- `_LANG_INSTRUCTIONS` for 10 languages – automatically appended to system prompts.
- Auto-memorize stop words: 9 languages (`NICHTS|NOTHING|RIEN|NADA|NULLA|NIETS|NIC|何もない|没有`).
- Frontend: Vanilla JS `I18n` class with `[data-i18n]` attributes, 10 language JSON files.

### Modules (15 active)

| Module | Description |
|---|---|
| `kubernetes` | Cluster management, pods, deployments, services, logs |
| `proxmox` | VMs, containers, backups, snapshots, nodes |
| `glpi` | Helpdesk tickets, assets, ITSM |
| `ionos` | DNS zones and record management via IONOS Hosting API |
| `fritzbox` | Network status, external IP, Wi-Fi, connected devices |
| `homeassistant` | Smart home: lights, heating, sensors, automations |
| `pihole` | Pi-hole v6 blocking, statistics, query log, custom DNS |
| `web_search` | SearXNG-based web search (Bing, Mojeek, Qwant) |
| `telegram` | Telegram bot with voice transcription and TTS replies |
| `email` | SMTP sending and IMAP retrieval |
| `wordpress` | Posts, media, pages via WordPress REST API |
| `codelab` | Code execution and debugging |
| `docker` | Container management |
| `linux_server` | Server administration via SSH/CLI |
| `image_gen` | AI image generation |

### TTS / STT

- **Piper TTS** – Local in backend pod, lazy-load. `POST /api/tts/synthesize`. Voice catalog, `_clean_for_tts()` for markdown/emoji stripping.
- **Whisper STT** – `faster-whisper` in backend. `POST /api/transcription/`. Supports `base`/`small` models.
- **Telegram voice** – Automatic voice replies when user sends a voice message.

### Chat UI

- **AI bubble**: `max-width: 90%` (user: 70%) – more space for long responses.
- **Tables**: `display: block; overflow-x: auto` – horizontal scrolling instead of clipping.
- **Textarea**: scrollbar hidden (`scrollbar-width: none`), auto-resize via JS.
- **Step log**: live status display with CSS spinner (active) and ✓ checkmark (done) via SSE.
- **Theme**: light/dark with FOUC prevention (inline `<script>` in `<head>`).
- **Compaction notification**: `⟳ Conversation history compacted` bubble on context reset.

### Infrastructure & Deployment

- **Dev**: `docker-compose.yml` – backend, Redis, ChromaDB, SearXNG, vault fallback (SQLite).
- **Prod**: Kubernetes/MicroK8s, namespace `ninko`, image `natorus87/ninko-backend:latest`, Traefik IngressRoute.
- **Plugin system**: ZIP-installable plugins with hot-load at runtime. Name validation against path traversal.
- **Secrets**: HashiCorp Vault with SQLite fallback (`VAULT_FALLBACK=sqlite`).
- **ChromaDB**: pinned to `0.4.24`, `numpy<2.0.0`.

### Bug Fixes

- Orchestrator retry loop: error messages now start with `"Fehler: ..."` – no more "Please try again."
- Compact matching threshold `>= 7` (was `>= 4`) – prevents German compound word misrouting.
- Telegram context prefix routing: `_strip_bot_context()` strips `[Telegram Chat-ID: ...]` before routing detection.
- LangGraph `recursion_limit=10000` + 1800s timeout as real safety net.
- `invoke()` returns `tuple[str, bool]` – all callers must unpack.
- Compaction summary preserved as `role=="system"` in history loop as `SystemMessage`.
- `crypto.randomUUID()` fallback via `Math.random()` for non-secure HTTP contexts.

---

## Version History

| Version | Date | Description |
|---|---|---|
| 0.5.0 | 2026-03-24 | First public release (beta) |
