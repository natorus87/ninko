# Ninko Backend

FastAPI-based Python 3.12 backend for the Ninko IT-Operations AI platform.

## Operational Sync (Apr 2026)

- Kubernetes runtime namespace is `ninko` (post-migration baseline).
- Auth flow:
  - first-login password change is enforced,
  - `POST /api/auth/change-password` refreshes session cookie immediately.
- Connection storage:
  - canonical key: `ninko:connections:<tenant>:<module>`
  - legacy key fallback + auto-migration is enabled for `ninko:connections:<module>`.
- Image generation:
  - writable image output directory fallback is implemented to avoid permission failures.
- Plugin frontend loading: `GET /api/modules/{name}/frontend/{tab.html|tab.js}` checks `backend/modules/` first, then `backend/plugins/` as fallback — all Marketplace-installed modules are served transparently.

## Overview

Ninko is a modular, AI-powered IT-Operations platform with an immutable core and auto-discovering modules. The AI Orchestrator routes user requests to specialized module agents using keyword-based detection.

## Architecture

### Entry Point
- **main.py** — FastAPI application with lifespan management, startup initialization, and route registration

### Core Systems (`core/`)
| File | Description |
|------|-------------|
| `module_registry.py` | Scans `modules/` and `plugins/`, imports manifests, registers agents/routers |
| `llm_factory.py` | LLM client factory (ollama, lmstudio, openai_compatible backends) |
| `agent_pool.py` | DynamicAgentPool singleton — runtime-created agents, persisted to Redis |
| `skills_manager.py` | Loads SKILL.md files from `backend/skills/` and `data/skills/`, injects into agent context |
| `soul_manager.py` | Soul MD management — persistent agent identities, built-ins + dynamic |
| `memory.py` | ChromaDB-backed semantic memory for RAG context injection |
| `connections.py` | Multi-connection CRUD manager (Redis + Vault) |
| `vault.py` | HashiCorp Vault client with SQLite fallback |
| `redis_client.py` | Shared async Redis client |
| `workflow_engine.py` | Async DAG execution engine (Trigger, Agent, Condition, Loop, Variable, End nodes) |
| `log_handler.py` | Custom RedisLogHandler — intercepts Python logs to Redis list |
| `theme_manager.py` | Theme loader/store for built-in + custom themes, active theme persistence |

### Agents (`agents/`)
| File | Description |
|------|-------------|
| `base_agent.py` | Abstract base using LangGraph `create_react_agent`, handles context trimming, RAG, Skills, Soul injection |
| `orchestrator.py` | LLM-native Function Calling routing; dispatches to direct answer, module agent, dynamic agent, or typed pipeline |
| `core_tools.py` | Core tools: `create_custom_agent`, `install_skill`, `create_linear_workflow`, etc. |
| `monitor_agent.py` | Background health check loop |
| `scheduler_agent.py` | Cron-based scheduled task runner |

### API Routes (`api/`)
- `routes_chat.py` — Chat endpoint with SSE streaming
- `routes_modules.py` — Module discovery and frontend asset serving
- `routes_agents.py` — Dynamic agent CRUD
- `routes_skills.py` — Skill management
- `routes_workflows.py` — Workflow CRUD and execution
- `routes_scheduler.py` — Scheduled task management
- `routes_settings.py` — LLM provider, language, TTS, module config
- `routes_connections.py` — Connection profile management
- `routes_memory.py` — Semantic memory (RAG) operations
- `routes_tts.py` — Text-to-Speech synthesis (Piper)
- `routes_transcription.py` — Speech-to-Text (faster-whisper)
- `routes_image_gen.py` — Image generation
- `routes_themes.py` — Theme management (presets, custom themes, repos, activation)
- `routes_logs.py` — Log viewing
- `routes_safeguard.py` — Safeguard middleware control

### Modules (`modules/` + `modules_catalog/`)
Each module is a self-contained package with:
- `manifest.py` — ModuleManifest (name, display_name, routing_keywords, api_prefix, dashboard_tab, health_check)
- `agent.py` — BaseAgent subclass instance
- `tools.py` — LangChain @tool functions
- `routes.py` — FastAPI router (optional)
- `schemas.py` — Pydantic models (optional)
- `frontend/tab.html`, `frontend/tab.js` — Dashboard UI

**Core Modules (`backend/modules/`)**
web_search, image_gen, codelab

**Catalog Modules (`backend/modules_catalog/`)**
checkmk, cisco, confluence, docker, email, fritzbox, glpi, homeassistant, hpe_ilo, ionos, jira, kubernetes, linux_server, microsoft_entra, microsoft_intune, mikrotik, netgear, nextcloud, opnsense, openproject, pihole, proxmox, qdrant, redmine, slack, synology, tasmota, teams, telegram, ubiquiti, wordpress

`lenovo_xclarity` is present in source but currently not listed in the official marketplace catalog.

### Schemas (`schemas/`)
Pydantic models for API request/response validation.

## Key Concepts

### Routing (orchestrator.py)

Primary mechanism: **LLM-native Function Calling** on tool definitions auto-generated from each module's manifest. The orchestrator exposes four tool families to the model — the chosen tool determines the execution path:

1. **Direct answer** — model responds without calling any module tool
2. **`call_module_agent`** — single-module delegation (Kubernetes, Proxmox, …)
3. **Dynamic agent** — spec generated and registered at runtime when no static module fits
4. **`run_pipeline` / `run_parallel_pipeline`** — typed multi-step workflow with per-step retry and Redis checkpoints

The legacy keyword `core/router.py` was removed in 2026-05. A small `KeywordRouter` shim in `orchestrator.py` provides keyword-based fast-path detection (`routing_keywords`) used as a tie-breaker in ambiguous cases; routing is otherwise LLM-native Function Calling. The historical tier-routing system (`RoutingConfig`, `ROUTING_PRESETS`, `configure_routing`/`get_routing_info` tools, `classify_tier`) was removed in 2026-06 as part of PLAN.md item 1.2.

### Skills System
- SKILL.md format with YAML frontmatter (name, description, modules)
- Injected as SystemMessage (max 2 skills per request, 12% keyword threshold)
- Hot-reloadable from `data/skills/` persistent volume

### Soul System
- Soul MDs define persistent agent identity
- Built-in souls in `backend/souls/` (protected)
- Dynamic agent souls persisted to Redis (`ninko:souls`)
- Auto-generated module souls at startup

### Connection Management
- Two systems: legacy `ninko:settings:modules` (Redis) and ConnectionManager (`ninko:connections:{module_id}`)
- Secrets stored in Vault or SQLite fallback

### Theme Management
- Built-in themes in `backend/themes/`
- Custom themes in `data/themes/`
- Active theme key: `ninko:settings:theme_active`
- API-driven theme activation and GitHub repo installation

## Dependencies

- **FastAPI** — Web framework
- **LangChain / LangGraph** — Agent framework
- **ChromaDB** — Vector database (pinned to 0.4.24, numpy<2.0)
- **Redis** — State persistence
- **faster-whisper** — Speech-to-text
- **Piper** — Text-to-speech (optional)

## Configuration

Environment variables (see `core/config.py`):
- `NINKO_MODULE_<NAME>` — Enable/disable modules
- `LLM_BACKEND`, `LLM_URL`, `LLM_MODEL`, `LLM_API_KEY` — LLM provider
- `REDIS_HOST`, `REDIS_PORT` — Redis connection
- `VAULT_ADDR`, `VAULT_TOKEN` — Vault secrets
- `WHISPER_MODEL_SIZE`, `WHISPER_LANGUAGE` — STT config
- `TTS_ENABLED`, `PIPER_BINARY`, `VOICES_DIR` — TTS config

## Development

```bash
# Local run
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Tests
python test_services.py
python test_monitor.py
python test_pihole.py
```

## File Structure

```
backend/
├── main.py                 # FastAPI entry point
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container definition
├── agents/                 # Agent implementations
│   ├── base_agent.py
│   ├── orchestrator.py
│   ├── core_tools.py
│   ├── monitor_agent.py
│   └── scheduler_agent.py
├── api/                    # REST API routes
│   ├── routes_chat.py
│   ├── routes_modules.py
│   ├── routes_agents.py
│   └── ... (14 route files)
├── core/                   # Core services
│   ├── module_registry.py
│   ├── llm_factory.py
│   ├── agent_pool.py
│   ├── skills_manager.py
│   ├── soul_manager.py
│   ├── memory.py
│   ├── connections.py
│   ├── workflow_engine.py
│   └── ... (10 more files)
├── modules/                # Core modules (baked into image)
│   ├── web_search/
│   ├── image_gen/
│   └── codelab/
├── modules_catalog/        # Marketplace module source catalog
│   ├── kubernetes/
│   ├── redmine/
│   ├── mikrotik/
│   └── ... (many modules)
├── schemas/                # Pydantic models
│   ├── chat.py
│   ├── settings.py
│   └── ... (8 more files)
├── skills/                 # Built-in skills (SKILL.md)
├── souls/                  # Built-in souls (MD files)
└── test_*.py               # Test scripts
```
