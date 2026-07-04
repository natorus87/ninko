# Ninko — Documentation

Ninko is a modular, AI-powered IT-Operations platform built on FastAPI (Python 3.12). The core is immutable — modules register themselves at startup, and no module name is hardcoded in the core.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [The Orchestrator — Function-Calling Routing](#2-the-orchestrator--function-calling-routing)
3. [How an Agent Processes a Request](#3-how-an-agent-processes-a-request)
4. [SafeGuard Middleware](#4-safeguard-middleware)
5. [Semantic Memory](#5-semantic-memory)
6. [Skills System](#6-skills-system)
7. [Soul System](#7-soul-system)
8. [LLM Providers](#8-llm-providers)
9. [Module Connections](#9-module-connections)
10. [Chat Interface](#10-chat-interface)
11. [Custom Agents](#11-custom-agents)
12. [Workflows (DAG Automation)](#12-workflows-dag-automation)
13. [Scheduler (Scheduled Tasks)](#13-scheduler-scheduled-tasks)
14. [Module Reference](#14-module-reference)
15. [Security](#15-security)
16. [Developing a Module](#16-developing-a-module)
17. [Startup Order & Persistence](#17-startup-order--persistence)
18. [Theme System](#18-theme-system)
19. [REST API Reference](#19-rest-api-reference)
20. [Operational Migration Notes (Apr 2026)](#20-operational-migration-notes-apr-2026)

---

## 1. Architecture Overview

### Core Principles

| Principle | Description |
|---|---|
| **Immutable Core** | No module name is hardcoded in the orchestrator or routing logic |
| **Auto-Discovering Modules** | Modules register themselves at startup via `ModuleManifest` |
| **Function-Calling Routing** | The model picks the right module tool(s) per request; deterministic fast-paths handle common cases |
| **Local AI by Default** | All LLM calls remain within the local network (Ollama / LM Studio) |

### Current Runtime Baseline (Apr 2026)

- Kubernetes namespace: `ninko`
- Backend deployment: `ninko-backend`
- Ingress hosts: `kumio.conbro.local` and `ninko.conbro.local`
- Connection Redis key format: `ninko:connections:<tenant>:<module>` (`default` tenant used for single-tenant operation)

### System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Ninko Dashboard                          │
│     Chat  │  Kubernetes  │  Proxmox  │  GLPI  │  + Modules     │
└───────────────────────────┬─────────────────────────────────────┘
                            │  HTTP / WebSocket
┌───────────────────────────▼─────────────────────────────────────┐
│                    FastAPI Backend (:8000)                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  SafeGuard Middleware                    │    │
│  │  Keyword-Pre-Filter → LLM-Classifier → Confirmation     │    │
│  └──────────────────────────┬──────────────────────────────┘    │
│  ┌───────────────────────────▼──────────────────────────────┐   │
│  │                   OrchestratorAgent                       │   │
│  │  Fast-paths → Function Calling → Pipeline / ReAct        │   │
│  └──────────────────────────┬──────────────────────────────-┘   │
│  ┌───────────────────────────▼──────────────────────────────┐   │
│  │                   Module Registry                         │   │
│  │   backend/modules/   +   backend/plugins/  (Hot-Load)    │   │
│  └───┬───────────┬────────────┬─────────────┬───────────────┘   │
│      │           │            │             │                    │
│  Kubernetes  Proxmox       GLPI        + 30 Modules             │
└──────┼───────────┼────────────┼─────────────┼────────────────────┘
       │           │            │             │
┌──────▼───────────▼────────────▼─────────────▼────────────────────┐
│   LLM Factory   │  ChromaDB (Memory)  │  Redis  │  Vault/SQLite  │
│ Ollama/LMStudio │  Embeddings + RAG   │  Cache  │  Secrets       │
└───────────────────────────────────────────────────────────────────┘
```

### Request Lifecycle

```
User input
  → SafeGuard (Keyword-Pre-Filter → LLM-Classifier)
  → Orchestrator (Tier decision)
  → [Module Agent | Dynamic Agent | Pipeline]
  → BaseAgent.invoke()
    → Soul + RAG context + Skills + Language
    → ReAct loop with tools (LangGraph)
    → <think> stripping (thinking models)
  → Response to user
  → Auto-Memorize in background (asyncio.create_task)
```

### Directory Structure

```
ninko/
├── backend/
│   ├── agents/           # OrchestratorAgent, BaseAgent, MonitorAgent, SchedulerAgent
│   ├── api/              # FastAPI routes (routes_*.py)
│   ├── core/             # Core singletons: LLMFactory, ModuleRegistry, Redis, Vault, ...
│   ├── modules/          # Core modules (always in image): web_search, image_gen, codelab
│   ├── modules_catalog/  # Catalog modules (installable via Marketplace)
│   ├── plugins/          # Runtime-installed plugins (via Marketplace or ZIP)
│   ├── skills/           # Built-in SKILL.md files
│   ├── souls/            # Built-in Soul MD files
│   ├── themes/           # Built-in dashboard themes
│   └── main.py           # FastAPI app, lifespan startup
├── frontend/             # Vanilla JS single-page app (static files)
├── data/                 # Persistent volume: skills/, themes/, plugins/
├── k8s/                  # Kubernetes manifests (placeholders, committed)
├── k8s-conbro/           # Kubernetes manifests (real values, gitignored)
└── docker-compose.yml
```

---

## 2. The Orchestrator — Function-Calling Routing

The `OrchestratorAgent` is the central brain. Every user message passes through it (unless SafeGuard blocks it beforehand). Routing is **LLM-native Function Calling**, not a fixed tier ladder: a few deterministic fast-paths run first, and everything else is decided by the model choosing which module tool(s) to call.

```
force_module?  ─────────────→ Direct module / custom-agent call
       ↓ no
agent/workflow creation? ────→ Deterministic auto-create
       ↓ no
FRITZ!Box-Tasmota discovery? → Read-only fast-path
       ↓ no
infra-status (proxmox/k8s)? ─→ Module status fast-path
       ↓ no
Function Calling (primary) ──→ LLM picks module tool(s)
       ↓ FC disabled / fails
ReAct fallback ──────────────→ orchestrator.invoke() with core tools
```

### Deterministic fast-paths (no LLM routing)

Checked in `route()` before any routing LLM call:

- **`force_module`** — the request pins a module or custom-agent UUID (e.g. via the chat module picker); bypasses routing entirely and calls that agent directly.
- **Agent creation** — explicit "create an agent for …" intent → `_auto_create_custom_agent` generates and registers a custom agent.
- **Workflow creation** — explicit "create a workflow …" intent → `_auto_create_workflow`.
- **FRITZ!Box-Tasmota discovery** — "find Tasmota devices in the FritzBox" style requests are served read-only without LLM routing.
- **Infra-status** — status/health questions for `proxmox` or `kubernetes` route straight to that module.

### Function Calling (primary path)

For everything else, the orchestrator exposes one tool per registered module (schema auto-generated from each manifest — no hardcoding) plus its core tools, and lets the LLM decide:

- **No tool call** → the model answers directly from its own knowledge.
- **One module tool** → `call_module_agent` delegates to that module's agent.
- **Two or more module tools** → the calls are assembled into an ad-hoc pipeline and run by the `PipelineEngine` (typed steps, per-step retry, Redis checkpoints).

Routing decisions are cached to skip the LLM call on repeats:
- **Exact cache** — sha256 of the (context + message), 24h TTL.
- **Semantic cache** — embedding cosine ≥ 0.92 against prior routings, 7d TTL.

```
"What is a Kubernetes pod?"                       → direct LLM answer (no tool)
"Show all failing pods"                           → call_module_agent("kubernetes", …)
"Check the Kubernetes cluster and send a Telegram report"
                                                  → pipeline [kubernetes → telegram]
"Create an agent for security audits"             → auto-create custom agent
```

### Custom (dynamic) agents

Registered custom agents from the `DynamicAgentPool` are listed in the routing prompt appendix, so the model can delegate to them like any module. New agents are created on demand via `create_custom_agent` (or the explicit agent-creation fast-path) and are usable immediately.

### ReAct fallback

If Function Calling is disabled (`LLM_ENABLE_FUNCTION_CALLING=false` / `tool_choice=none`), the model produces no tool schema, or the routing LLM call fails, the orchestrator falls back to a ReAct loop (`orchestrator.invoke()`) that reasons over its core tools directly.

### Utility Module Exclusion

`_UTILITY_MODULES = {"web_search", "image_gen", "telegram", "email", "teams"}` — notification/utility modules are only added to a multi-step pipeline when explicitly named in the message. Prevents false-positive extra steps caused by history contamination.

> **Note:** Earlier releases used an explicit 4-tier router (keyword fast-path + compound pipeline planner). Those code paths (`_route_tier2_module`, `_plan_and_execute_pipeline`) were removed in 2026-07; routing is Function-Calling-only. A `KeywordRouter` shim remains in `orchestrator.py` for its unit tests but is not part of the live routing path.

### Orchestrator Tools

| Tool | Function |
|---|---|
| `execute_cli_command` | Run a shell command on the backend host |
| `create_custom_agent` | Create and register a new dynamic agent |
| `update_custom_agent` | Update an existing agent (takes effect immediately) |
| `install_skill` | Write a SKILL.md to the persistent volume and hot-reload |
| `create_linear_workflow` | Programmatically create and save a workflow |
| `execute_workflow` | Execute a saved workflow by ID |
| `remember_fact` | Store a fact in semantic memory |
| `recall_memory` | Semantic search in long-term memory |
| `forget_fact` / `confirm_forget` | Two-step memory deletion (preview → confirmation) |
| `call_module_agent` | Delegate a task to any module agent |
| `run_pipeline` | Execute a sequential JSON plan |
| `wait` | Wait dynamically (1–60 seconds) with a reason |

---

## 3. How an Agent Processes a Request

All agents — module agents, dynamic agents, and the orchestrator — share the same `BaseAgent.invoke()` foundation.

### Invoke Flow

```
BaseAgent.invoke(user_message, session_id, chat_history)
│
├─ 1. Context-Window Calibration (first call only, cached)
│     Query LLM provider for the model's context window.
│     History budget = 25% of window − MAX_OUTPUT_TOKENS.
│
├─ 2. History Trimming / Compaction
│     Token count > budget?
│     └─ LLM summarizes old messages into a compaction summary.
│        Summary is inserted as a SystemMessage at position 1.
│
├─ 3. System Prompt Assembly (exact order):
│     a. Soul MD               ← persistent agent identity
│     b. Core system_prompt    ← tools + behavioral instructions
│     c. Connection context    ← active connections for this module
│     d. Compaction summary    ← if history was compacted
│     e. RAG context           ← top-3 semantic memory hits (cosine < 0.5)
│     f. Skills injection      ← max. 2 matching SKILL.md files (threshold 12%)
│     g. Date/time injection   ← current date+time (TIMEZONE env)
│     h. Language instruction  ← "Answer in English." / "Antworte auf Deutsch."
│
├─ 4. JIT Tool Injection (when agent has > 6 tools)
│     Each tool is scored against the message.
│     Only the top-8 most relevant tools are kept.
│     A temporary agent with a reduced tool set is created.
│
├─ 5. ReAct Agent Execution (LangGraph)
│     Timeout: 1800 seconds. Recursion limit: 10,000 (effectively unlimited).
│     Real-time status events via SSE bus to the frontend.
│
├─ 6. Response Extraction
│     Strip <think>…</think> blocks (thinking models like Qwen3.5).
│     Final text extraction from AIMessage.
│     If empty → fall back to ToolMessage content or default error string.
│
└─ 7. Auto-Memorize (background asyncio task — never blocks the response)
      Cooldown: 60 seconds per agent.
      Skipped for: monitor, scheduler; responses < 80 characters.
      LLM extracts 1–2 permanent facts.
      Stored in ChromaDB under category "agent_memory".
```

### Return Value

`BaseAgent.invoke()` always returns `tuple[str, bool]` — `(response, did_compact)`.
`OrchestratorAgent.route()` returns `tuple[str, str | None, bool]` — `(response, module, did_compact)`.

**Important:** All call sites must unpack both or all three values:
```python
response, _ = await agent.invoke(...)
response, module, _ = await orchestrator.route(...)
```

---

## 4. SafeGuard Middleware

SafeGuard runs **before** the orchestrator on every user message (and optionally on every tool call). Since v0.7.2 it is fully profile-based.

### Built-in Profiles

| Profile ID | User messages | Tool calls | Injection detection | fail_open |
|---|---|---|---|---|
| `strict` | ✓ | ✓ | ✓ | No |
| `moderate` *(default)* | ✓ | ✓ | No | No |
| `user_only` | ✓ | No | No | No |
| `llm_only` | No | ✓ | No | No |
| `disabled` | No | No | No | Yes |

### Classification Categories

| Category | Meaning | Examples |
|---|---|---|
| `SAFE` | Read-only | `show pods`, `list DNS records`, `status` |
| `STATE_CHANGING` | Creates or modifies something | `create pod`, `update DNS`, `deploy` |
| `DESTRUCTIVE` | Irreversible | `delete namespace`, `rm -rf`, `DROP TABLE` |
| `PROMPT_INJECTION` | Instruction hijacking detected | `ignore previous instructions`, `you are now` |
| `UNKNOWN` | Parse error or LLM failure | — |

The `confirm_categories` field in the profile controls which categories actually require confirmation. Empty list = classify but never block.

### Three-Stage Evaluation

**Stage 1 — Profile Resolution**

Order (first match wins):

```
1. Per-chat session   → Redis ninko:safeguard:profile:chat:{session_id} (TTL 24h)
2. Per-agent          → AgentConfigStore (ninko:agent_configs hash)
3. Global profile     → Redis ninko:settings:safeguard
4. Fallback           → "moderate"
```

**Stage 2 — Keyword Pre-Filter** (messages ≤ 200 characters)

Fast in-process check without an LLM call. Detected patterns in all 10 languages:

- **Safe:** `show`, `list`, `get`, `logs`, `status`, `what`, `explain`, `zeige`, `liste`, `pokaż`, `显示`, `表示` …
- **Destructive:** `delete`, `rm -`, `drop`, `lösche`, `supprim`, `elimin`, `削除` …
- **State-Changing:** `create`, `deploy`, `scale`, `erstell`, `crée`, `crea`, `作成` …
- **Injection patterns:** `ignore previous instructions`, `you are now`, `forget your rules`, `system prompt override` …

Priority: safe → destructive → state-changing → injection. First match wins.

> **Note:** `"del"` is intentionally absent from destructive keywords — it is a common preposition in Spanish, Italian, and French (`"del pod"` = `"of the pod"`).

**Stage 3 — LLM Classifier** (when no pre-filter match)

LLM call with `max_tokens=150` and an 8s timeout. Response parsing: strip `<think>` blocks, remove markdown fences, extract the first `{…}` JSON object.

### Confirmation Flow

**Dashboard (REST):**
SafeGuard blocks → frontend receives `confirmation_required: true` → confirmation dialog with category + rationale. For `PROMPT_INJECTION` a special warning banner appears. The next click sends `confirmed: true` in the request body.

**Telegram / Teams (bot channels):**
Bots cannot send `confirmed: true` in a follow-up request. Ninko stores the pending message in Redis (`ninko:safeguard_pending:{session_id}`, TTL 300s). If the user replies within 5 minutes with a confirmation word (`ja`, `yes`, `confirm`, `ok`, `si`, `oui`, `tak`, `はい`, `确认` …), the original message is re-executed. Any other message starts a normal new flow.

### fail_open Mode

When `fail_open: true` in the profile, any LLM error (timeout, parse error) causes the request to be **passed through** instead of blocked. Prevents Ninko from becoming unusable when the LLM is down.

> **Warning:** With `fail_open: false` and an unreachable LLM, `safeguard.check()` returns `requires_confirmation=True` for every message. Workaround: `POST /api/safeguard/active` with `{"profile_id": "disabled"}` or create a profile with `fail_open: true`.

---

## 5. Semantic Memory

Ninko has a **persistent long-term memory** based on ChromaDB vector embeddings. Unlike chat history (7-day TTL in Redis), semantic memory survives container restarts and new sessions.

### Automatic Storage

After each agent response, a background task checks whether the conversation contained a permanently relevant fact (user preferences, known IPs, resolved incidents, decisions). If so, it is stored silently.

Skipped when:
- Response < 80 characters
- Agent is `monitor` or `scheduler`
- 60-second cooldown for this agent is still active

### Manual Storage

```
"Remember: Pi-hole runs on 192.168.1.10"
"Please note that I work in the infrastructure team"
"Store: Prod cluster runs on node k3s-prod-01"
```

### Retrieval

```
"What do you know about our infrastructure?"
"Do you remember what IP the Pi-hole had?"
"What was the result of the last incident?"
```

### Deletion (two-step)

**Step 1 — Preview:**
```
"Forget that Pi-hole runs on 192.168.1.10"
```
Ninko shows matching entries with content and ID. Nothing is deleted yet.

**Step 2 — Confirmation:**
```
"Yes, delete that" / "confirm" / "delete all"
```
Only after confirmation are the entries removed from ChromaDB.

### RAG Mechanism

On every `invoke()` call, the user message is embedded and compared via cosine similarity against all stored entries. Entries with distance < 0.5 are prepended to the system prompt:

```
Relevant context from memory:
- Pi-hole runs on 192.168.1.10
- Prod cluster is on node k3s-prod-01
```

### Cosine Distance Threshold

Default: `threshold=0.25` for `delete_by_content()`. Too low (< 0.1) = too strict, too high (> 0.5) = deletes related but distinct facts. The quality of auto-memorization depends heavily on model size — models < 7B respond with `NICHTS` too often.

---

## 6. Skills System

Skills are procedural knowledge files (SKILL.md) that are automatically injected into agent prompts when they match the current request.

### Skills vs. Memory vs. Soul

| Type | Content | Question |
|---|---|---|
| **Soul** | Persistent agent identity | *Who is this agent?* |
| **Skills** | Procedural domain knowledge | *How should one approach this problem?* |
| **Memory** | Episodic facts | *What has happened / is known?* |

### SKILL.md Format

```markdown
---
name: kubernetes-incident-response
description: Step-by-step guide for pod failure diagnosis in Kubernetes
modules: [kubernetes]
---

## Step 1 — Check pod status
Run `get_failing_pods()` to identify pods in a non-running state.

## Step 2 — Analyze logs
Check the last 100 lines with `get_pod_logs(pod_name, namespace)`.
...
```

The `modules` field restricts injection to specific agents. Empty array = available to all agents.

### Built-in Skills

| Skill | Module | Purpose |
|---|---|---|
| `kubernetes-incident-response` | kubernetes | CrashLoopBackOff, OOMKilled, eviction diagnosis |
| `pihole-session-management` | pihole | Session token caching, 429 handling, rate limits |
| `ionos-dns-quirks` | ionos | IONOS API quirks (zones vs. records, em-dash in keys) |
| `proxmox-troubleshooting` | proxmox | Common Proxmox error patterns |
| `fritzbox-network-diagnostics` | fritzbox | Network diagnostics, WAN troubleshooting |
| `homeassistant-automation` | homeassistant | Automation templates and patterns |
| `glpi-ticket-workflow` | glpi | Ticket creation and escalation workflow |
| `email-alert-templates` | email | Email templates for alerts and reports |
| `web-search-strategy` | web_search | Search strategies for research |
| `wordpress-publishing` | wordpress | Publishing workflow for posts |
| `agent-builder` | all | 5-question interview for agent creation |
| `workflow-builder` | all | DAG workflow planning and patterns |

### Injection Logic

On every `invoke()` call, `SkillsManager.find_matching_skills(message, agent_name)` runs:
1. Tokenize the message.
2. Per skill: check module filter, then calculate keyword overlap.
3. Return top-2 skills with overlap ≥ 12%.
4. Append as formatted Markdown to the end of the system prompt.

### Installing Custom Skills

Via chat:
```
"Teach Ninko how to restart the payment service: [describe procedure]"
```

Via API:
```http
POST /api/skills/
Content-Type: application/json

{
  "name": "payment-service-restart",
  "description": "Restart procedure for the payment service",
  "content": "## Step 1\nFirst check the pod logs...",
  "modules": ["kubernetes", "docker"]
}
```

Skills are written to `data/skills/` (persistent volume) and survive container restarts.

---

## 7. Soul System

Every agent in Ninko has a "Soul" — a Markdown file that defines its persistent identity, purpose, capabilities, and behavioral constraints. The Soul is injected at the very beginning of the system prompt, before RAG context, skills, or language instructions.

### Soul Types

**Built-in Souls** (`backend/souls/*.md`)
Baked into the Docker image. Protected from deletion. Ninko's own Soul (`ninko.md`) is injected into the orchestrator.

**Module Agent Souls**
Automatically generated at startup from the manifest description and tool names. Only created if no soul exists yet.

**Dynamic Agent Souls**
Automatically generated when a custom agent is created via `create_custom_agent` or the Agents UI. Generated from name, description, and system prompt bullet points. Stored in Redis (`ninko:souls`).

### Soul Structure

A generated Soul contains:
- **Identity** — "You are [Name], [role] for Ninko."
- **Purpose** — The agent's primary mission.
- **Capabilities** — Extracted from system prompt bullet points.
- **Behavior Guidelines** — Tone, escalation paths, tool usage conventions.
- **Constraints** — What the agent should **not** do.
- **Escalation Rules** — When to delegate back to the orchestrator.

### Soul vs. System Prompt

| | Soul | System Prompt |
|---|---|---|
| **Purpose** | Persistent identity / personality | Operational instructions and tool rules |
| **Location** | `backend/souls/` or Redis `ninko:souls` | In `BaseAgent.__init__()` or dynamic agent JSON |
| **Injection position** | Very beginning of the final system prompt | After the Soul |
| **Mutability** | Built-in: read-only; dynamic: editable | Always editable |

---

## 8. LLM Providers

Ninko supports four backend types. All providers use a unified interface (`LLMFactory`) so modules and agents never need to know which backend is active.

### Supported Backends

| Backend | Use case | API key required |
|---|---|---|
| `ollama` | Local model server (Ollama) | No |
| `lmstudio` | Local model server (LM Studio) | No |
| `openai_compatible` | Any OpenAI-compatible API (OpenRouter, Groq, Heimaker) | Yes |
| `litellm` | LiteLLM proxy (any model behind a proxy) | Yes (any value) |

### Adding a Provider

1. **Settings → LLM Providers → Add Provider**
2. Choose backend type
3. Enter base URL:
   - Ollama (Docker): `http://ollama:11434`
   - LM Studio (local): `http://192.168.1.100:1234` — `/v1` is appended automatically
   - OpenRouter: `https://openrouter.ai/api/v1`
   - LiteLLM: your own proxy URL
4. Model name exactly as expected by the provider (e.g. `qwen2.5:14b`, `llama3.2:3b`)
5. **Set as default** → active immediately without restart

### Embedding Model

The embedding model for ChromaDB (semantic memory and RAG) is configured separately under **Settings → LLM Providers → Embedding Model**. It is independent of the active LLM provider. When changing the embedding model, existing memory entries should be re-embedded.

### Thinking Models (Qwen3.5, DeepSeek-R1)

These models emit `<think>…</think>` blocks before their actual response. Ninko strips these automatically before the response reaches the user, before SafeGuard JSON parsing, and before memory storage. No configuration required.

### LM Studio — Known Limitations

LM Studio's embedded Jinja2 does not support the `is sequence` test. This causes three known errors, all fixed in `llm_factory.py`:

1. **HTTP 400 "Unknown test: sequence"** for list content → `_NormalizingChatOpenAI` normalizes lists to strings.
2. **Model generates `example_function_name`** instead of real tool names → `_inject_tools_into_system()` appends tool definitions as readable text to the SystemMessage.
3. **HTTP 400** for `AIMessage` with `tool_calls` list → `_convert_tool_messages_to_text()` converts to XML format (`<tool_call>`, `<tool_response>`).

### SSL Certificates

For self-signed certificates (e.g. internal LiteLLM proxy): set `verify_ssl: false` in the provider. **Important:** `get_safeguard_openai_client()` must use the same `verify` value, otherwise the SafeGuard classifier fails with `CERTIFICATE_VERIFY_FAILED`.

---

## 9. Module Connections

Ninko supports **multi-connection** per module: a module (e.g. Kubernetes) can manage multiple environments simultaneously (prod, staging, dev, lab).

### Creating a Connection

1. **Settings → [Module] → Connections**
2. Click **New Connection**
3. Fill in the fields:
   - **Name** — Descriptive label (e.g. "Prod Cluster Frankfurt")
   - **Environment** — `prod`, `staging`, `dev`, `lab`, or `local` (affects SafeGuard risk assessment)
   - **Non-secret fields** — URLs, usernames, options
   - **Secret fields** — Passwords, API keys, tokens (always displayed empty, stored in Vault)
4. **Set as default** — Used automatically when no other connection is requested
5. **Save**

> **Note:** Empty secret fields never overwrite saved values. Non-secret fields can be updated without re-entering passwords.

### Using a Connection in Chat

```
"Restart the nginx pod in the staging cluster"
"Show Pi-hole statistics on the 'Home Lab' connection"
"Scale the payment service to 3 replicas on the prod connection"
```

### Two Separate Configuration Systems

| System | API | Storage | Used by |
|---|---|---|---|
| Legacy module settings | `PUT /api/settings/modules/{name}` | Redis `ninko:settings:modules` | Older configuration fields |
| ConnectionManager | `POST /api/connections/{module_id}` | Redis `ninko:connections:{id}` + Vault | All current modules (tools) |

Tools always read via `ConnectionManager.get_default_connection(module_id)`. If no UI connection exists, modules fall back to env vars (e.g. `FRITZBOX_HOST`, `HOMEASSISTANT_URL`).

---

## 10. Chat Interface

### Navigation

| Area | Elements |
|---|---|
| Top navigation bar | **New Chat**, **Automation** (Tasks, Agents, Workflows) |
| Bottom navigation bar | **Modules**, **Settings** |
| History | Chat history list (directly below the top nav, no separate header bar) |

**Connection status** — Single green/red dot in the top right of the sidebar header.

### Sending Messages

Enter requests in natural language. The orchestrator handles routing automatically.

| Input | Tier | Handler |
|---|---|---|
| `"What is BGP?"` | 1 | Direct LLM answer |
| `"Show all failing pods"` | 2 | Kubernetes agent |
| `"Create a security agent"` | 3 | Dynamic agent created |
| `"Check cluster and send Telegram report"` | 4 | Pipeline |

### Module Pre-Selection (Chat Toolbar)

The module-picker pill next to the chat title (`Ninko._forcedModule`) enables direct routing:
- **Auto** — normal Function-Calling routing
- **Module name** — Directly to the module agent (bypasses all tiers)
- **Custom agent UUID** — Directly to the custom agent (from `DynamicAgentPool`)

Custom agents appear in the dropdown under "My Agents" with a 🤖 prefix.

### Voice Control

Click the microphone button → record a voice message → Whisper transcribes it (locally, no external API call) → text is sent as a chat message.

> **Note:** The microphone only works over HTTPS or `localhost`. Over plain HTTP, browsers block `navigator.mediaDevices`.

### Multilingual Support

10 languages: German, English, French, Spanish, Italian, Portuguese, Dutch, Polish, Chinese, Japanese. Language change in **Settings → Language** without page reload.

---

## 11. Custom Agents

Custom agents are specialized AI personas that can be created manually or automatically by the orchestrator.

### Creating an Agent (UI)

1. **Agents tab → New Agent**
2. Fill in the fields:
   - **Name** — Used for routing and Soul generation
   - **Description** — Listed in the orchestrator's routing prompt so the model can delegate matching requests to this agent
   - **System Prompt** — Bullet points for capabilities recommended (used by the Soul generator)
   - **LLM Provider** — Empty = global default
   - **SafeGuard Profile** — Which security profile for this agent
3. **Save** → Immediately registered in `DynamicAgentPool`, stored in Redis

### Base Tools (all Custom Agents)

Every custom agent automatically receives 4 base tools:

| Tool | Function |
|---|---|
| `execute_cli_command` | Run shell commands |
| `call_module_agent` | Invoke any module agent |
| `recall_memory` | Search semantic memory |
| `remember_fact` | Store in semantic memory |

### Agent Templates

6 built-in templates as a starting point:

| Template ID | Label | Category |
|---|---|---|
| `it_ops` | IT Operations Generalist | ops |
| `k8s_specialist` | Kubernetes Specialist | ops |
| `security_scanner` | Security Scanner | security |
| `monitor_reporter` | Monitor & Reporter | monitoring |
| `helpdesk` | Helpdesk Agent | support |
| `home_automation` | Home Automation | smart_home |

### LLM Generation

```http
POST /api/agents/generate
{"use_case": "Monitors Docker containers and sends alerts via Telegram", "allowed_modules": ["docker", "telegram"]}
```

Returns `name`, `description`, and `system_prompt` — ready to save.

---

## 12. Workflows (DAG Automation)

The workflow editor provides a visual canvas for multi-step automation pipelines as Directed Acyclic Graphs (DAGs).

### Node Types

| Node | Configuration fields | Purpose |
|---|---|---|
| **Trigger** | — | Entry point of every workflow |
| **Agent** | `agent_id`, `prompt` | Delegate a task to the orchestrator (full Function-Calling routing) |
| **Condition** | `expression`, `true_label`, `false_label` | Branch: `output.contains("error")` → true path |
| **Variable** | `name`, `value` | Set a variable, supports `{other_variable}` interpolation |
| **Loop** | `variable`, `items` | Iterate over a list |
| **End** | `status` | Terminal node |

### Variable Interpolation

Outputs flow through the workflow via `{previous_output}`. Named variables via the Variable node:

```
Variable: result = "Cluster is healthy"
Agent prompt: "Summarize this for a status report: {result}"
```

### Starting a Workflow

- **Manually:** ▶ button on the workflow card
- **Scheduled:** Assign the workflow to a scheduled task (→ Section 13)
- **Via chat:** `"Execute the daily-k8s-report workflow"` — orchestrator calls `execute_workflow`

### Run Status

| Status | Meaning |
|---|---|
| `idle` | Not yet started |
| `running` | Currently executing |
| `succeeded` | Completed successfully |
| `failed` | Aborted with an error |

Each step has its own status: `pending`, `running`, `succeeded`, `failed`, `skipped`.

---

## 13. Scheduler (Scheduled Tasks)

The scheduler runs tasks automatically on a cron schedule via background coroutines in the backend process.

### Task Types and Execution Paths

```
workflow_id present → WorkflowEngine.execute(workflow)
agent_id present    → DynamicAgentPool.get_agent_by_id(id) → agent.invoke()
prompt present      → orchestrator.route(prompt)  [default path]
```

Scheduled tasks do **not** pass through SafeGuard — they are trusted background processes.

### Cron Syntax

| Expression | Meaning |
|---|---|
| `*/5 * * * *` | Every 5 minutes |
| `0 * * * *` | Hourly |
| `0 8 * * *` | Daily at 08:00 |
| `0 8 * * 1` | Every Monday at 08:00 |
| `0 */6 * * *` | Every 6 hours |
| `0 9,17 * * 1-5` | Mon–Fri at 09:00 and 17:00 |

### Task Logs

Click the log icon on a task card → last 50 execution logs with timestamp, duration, status (ok/error), and full LLM output.

---

## 14. Module Reference

### Core Modules (always in the image)

#### Web Search (🔍)
Web search via a local SearXNG instance (aggregates Bing, Mojeek, Qwant).

**Configuration:** `SEARXNG_URL` env var. Docker Compose: set automatically. Kubernetes: enter in `deployment.yaml`.

```
"What is the current Bitcoin price?"
"Search Kubernetes 1.30 release notes"
"News about Redis 8"
```

#### Image Generation (🎨)
AI image generation via any compatible API.

**Providers:** Together AI, OpenAI DALL-E, Google Imagen, local Stable Diffusion. API key in Settings → Image Generation.

```
"Create an image of a Kubernetes cluster diagram"
```

#### CodeLab (💻)
Code execution and analysis in the browser. Supports Python, Bash, JavaScript.

### Catalog Modules (installable via Marketplace)

#### Kubernetes (☸)

| Capability | Description |
|---|---|
| Cluster health | Node status, resource usage |
| Pod management | List, logs, restart |
| Deployment scaling | `scale`, `rollout restart` |
| Write operations | `apply_manifest`, `delete_resource`, `create_namespace` |
| Event analysis | Error diagnosis, CrashLoopBackOff, OOMKilled |

```
"Show all failing pods in the production namespace"
"Restart the payment-api pod"
"Create an nginx test pod in the default namespace"
"Scale the frontend deployment to 3 replicas"
"Apply this manifest: [YAML]"
```

#### Proxmox (🖥)
VM and LXC container management via the Proxmox REST API.

```
"List all VMs on pve-01"
"Start VM 105"
"Create a snapshot of VM 200 named 'before-update'"
"Migrate VM 200 to pve-02"
```

#### GLPI Helpdesk (🎫)
Ticket and asset management via the GLPI REST API.

```
"Create an incident ticket: server unreachable"
"Status of ticket #1234?"
"Show all open tickets assigned to me"
```

#### IONOS DNS (🌐)
DNS zone and record management via the IONOS Hosting API.

**Authentication:** API key in `prefix.secret` format (two parts separated by `.`).

**Known quirk:** The IONOS API embeds records in the zone object (`GET /zones/{id}`), no separate records endpoint. Ninko handles this automatically.

```
"Which DNS zones do we have at IONOS?"
"Create an A record for dev.example.com → 10.0.0.5"
"Delete the TXT record _acme-challenge.example.com"
```

#### FritzBox (📶)
Home and office network management.

```
"What is my external IP address?"
"Enable the guest Wi-Fi network"
"Show connected devices"
"Create a port forwarding rule for port 8080"
```

#### Home Assistant (🏠)
Smart home automation.

```
"Turn on the living room lights"
"Set the heating to 21°C"
"Current temperature in the bedroom?"
"Create an automation: when motion detected → turn on light"
```

#### Pi-hole (🛡)
DNS-based ad blocking and custom DNS management (Pi-hole v6).

**Known quirk:** Pi-hole v6 uses a session-based API with rate limiting. Ninko caches the session token (5-minute TTL) and handles 429 errors with automatic retry.

```
"Block the domain tracking.example.com"
"Show today's network statistics"
"Add a local DNS record: nas.home → 192.168.1.50"
```

#### Docker (🐳)
Container management via the Docker socket API.

```
"List all running containers"
"Show logs for container nginx-proxy"
"Restart container my-app"
"Clean up Docker system (images, volumes)"
```

#### Checkmk (📊)
Monitoring platform integration.

```
"Show all critical hosts in Checkmk"
"Acknowledge the alert for web-server-01"
"Create a maintenance window for db-01"
```

#### Linux Server (🖥)
SSH-based remote server administration.

```
"Check disk usage on server web-01"
"Show last 50 lines of /var/log/syslog"
"Restart the nginx service"
```

#### WordPress (📝)
Content management via the WordPress REST API.

**Prerequisite:** WordPress must use a permalink format other than "Plain" (Settings → Permalinks). Plain permalinks disable the REST API.

```
"Create a draft with the title 'Q1 Summary'"
"List the last 5 published posts"
```

#### Telegram Bot (💬)
Full bidirectional Telegram messenger integration.

**Features:**
- Voice messages are automatically transcribed via Whisper and processed as text
- Replies can be sent as voice messages (TTS via Piper) when TTS is active
- SafeGuard uses a pending confirmation flow for bot channels
- Session ID is tied to the Telegram user ID and survives restarts

**Commands:** `/start`, `/clear`, `/reset` — delete the chat history of the current session

#### Microsoft Entra / Intune, Cisco, Confluence, Jira, OpenProject, Redmine, Slack, Teams
Additional enterprise integrations — each via REST API, connection via ConnectionManager, secrets in Vault.

#### Synology, Netgear, Mikrotik, Ubiquiti, Tasmota, OPNsense, HPE iLO, Lenovo XClarity
Network, NAS, and hardware management integrations.

---

## 15. Security

### Local AI by Default

All LLM calls remain within the network when using Ollama or LM Studio. No data goes to external services unless an OpenAI-compatible external provider is explicitly configured.

### Secrets Storage

All module credentials (API keys, passwords, tokens) are stored encrypted via HashiCorp Vault or SQLite fallback. Never in plain text on disk. Always displayed as empty in API responses.

### SafeGuard

Every user-initiated message is classified before execution (→ Section 4). State-changing, destructive, and prompt injection attempts require explicit confirmation.

### Proxmox — Additional Protection Layer

`PROXMOX_CONFIRM_DESTRUCTIVE=true` (default) requires agent-level confirmation before irreversible VM operations.

### Network Exposure

Ninko is designed for internal network operation. Do **not** expose it directly to the internet. For production use, place a reverse proxy (Traefik, Nginx) with TLS and optionally basic auth or OAuth middleware in front of it.

### Log Security

Ninko writes logs to a capped Redis list (`ninko:logs`, visible in the Logs tab). Secret API keys passing through tools are not automatically masked in logs. Do not include raw secrets in system prompts or chat messages.

---

## 16. Developing a Module

Every module follows the same self-contained structure. Adding a new module only requires creating a folder — nothing in the core changes.

### File Structure

```
backend/modules_catalog/mymodule/
├── __init__.py       ← Exports: module_manifest, agent, router
├── manifest.py       ← ModuleManifest with routing_keywords
├── agent.py          ← BaseAgent subclass
├── tools.py          ← @tool functions (LangChain)
├── schemas.py        ← Pydantic models
├── routes.py         ← FastAPI APIRouter
└── frontend/
    ├── tab.html
    └── tab.js
```

### manifest.py

```python
from backend.core.module_registry import ModuleManifest

module_manifest = ModuleManifest(
    name="mymodule",                            # Internal ID, lowercase
    display_name="My Module",                   # UI label
    description="Manages MyService instances",  # Used by LLM for routing — keep descriptive
    version="1.0.0",
    routing_keywords=[
        "myservice", "my-module", "specific-term",
        # Keep keywords unique across all modules.
        # Short keywords (< 7 chars) use only \b word-boundary matching.
        # Keywords >= 7 chars also match within compound words.
    ],
    api_prefix="/api/mymodule",
    dashboard_tab={"id": "mymodule", "label": "My Module", "icon": "🔧"},
    health_check=lambda: {"status": "ok"},
    enabled_by_default=False,  # False = requires credentials before meaningful operation
)
```

### agent.py

```python
from backend.agents.base_agent import BaseAgent
from backend.modules_catalog.mymodule.tools import my_tool, my_other_tool

class MyModuleAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="mymodule",
            system_prompt=(
                "You are the My Module specialist for Ninko.\n\n"
                "Capabilities:\n"
                "- List resources and check status\n"
                "- Create and update resources\n\n"
                "Rules:\n"
                "- Always confirm before deleting\n"
                "- Always pass connection_id to tools\n"
            ),
            tools=[my_tool, my_other_tool],
        )
```

### tools.py

```python
from langchain_core.tools import tool
from backend.core.connections import ConnectionManager

@tool
def get_my_resource(resource_id: str, connection_id: str = "") -> str:
    """
    Retrieves the status of a resource.

    Args:
        resource_id: The ID of the resource to check.
        connection_id: Optional connection profile.

    Returns:
        JSON string with status details.
    """
    # Tool docstrings matter — the agent LLM uses them for tool selection.
    conn = ConnectionManager.get_default_connection("mymodule", connection_id)
    # ... API call ...
```

**Read-only tools** (read-only, no writes) must be registered in `backend/core/safeguard.py:_TOOL_READONLY`:
- `get_*`, `list_*`, `search_*`, `inspect_*`, `check_*` → read-only → add to the frozenset
- `start_*`, `stop_*`, `restart_*`, `delete_*`, `create_*`, `set_*` → write → **do not** add

### routes.py

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/mymodule", tags=["mymodule"])

@router.get("/resources")
async def list_resources(connection_id: str = ""):
    """Dashboard API — always accept connection_id and pass it to tools."""
    ...
```

### frontend/tab.js

```javascript
// No ES module syntax (no export/import).
// All catalog modules (both core and plugin) must register via _pluginTabs.
// getTabObject() in app.js checks _pluginTabs as a fallback — this guarantees
// the dashboard init() is called regardless of how the module is loaded.
const MyModuleTab = {
    async init() {
        // Called on first tab activation by switchModuleTab().
    },
    destroy() {
        // Optional cleanup (clear polling intervals etc.)
    }
};

// REQUIRED for all catalog modules — must be the last line in tab.js.
if (typeof Ninko !== 'undefined') Ninko._pluginTabs['mymodule'] = MyModuleTab;
```

> **Why `_pluginTabs` is mandatory for catalog modules**: When a module is installed from GitHub Marketplace it lands in `backend/plugins/`. `getTabObject()` in `app.js` contains a hardcoded map of known global variable names. If the tab.js uses `const X = {}` (rather than `window.X = {}`), the variable may not be accessible via `typeof X` across script scopes in all browsers. `_pluginTabs` registration is explicit and always reliable.

### Activating a Module

```env
NINKO_MODULE_MYMODULE=true
```

Ninko discovers and loads the module automatically on the next start.

### Checklist

- [ ] `routing_keywords` are unique across all modules.
- [ ] Tool docstrings describe exactly what each tool does and returns.
- [ ] `manifest.description` is informative (used by the LLM for routing decisions).
- [ ] Increment `ModuleManifest.version` on breaking changes.
- [ ] Register secret fields in `routes_settings.py:_get_secret_keys()` and `_get_env_connection()`.
- [ ] Register read-only tools in `safeguard.py:_TOOL_READONLY`.
- [ ] `routes.py` endpoints accept `connection_id: str = ""`.
- [ ] `frontend/tab.js` does not use `export`/`import`.
- [ ] `frontend/tab.js` last line: `if (typeof Ninko !== 'undefined') Ninko._pluginTabs['mymodule'] = MyModuleTab;`

---

## 17. Startup Order & Persistence

### Startup Order (`main.py` Lifespan)

```
1.  ModuleRegistry.scan()             → Scan backend/modules/ + backend/plugins/, load manifests
2.  SoulManager.load()                → Load built-in souls from backend/souls/
3.  SoulManager.load_from_redis()     → Merge dynamic souls from Redis
4.  ModuleRegistry.auto_generate_souls() → Generate souls for modules without their own soul
5.  SkillsManager.load()              → Load backend/skills/ + /app/data/skills/
6.  SafeguardProfileStore.seed_builtins() + migrate_legacy()
7.  SafeguardMiddleware.init()        → Restore active profile ID from Redis
8.  DynamicAgentPool.load_from_redis() → Instantiate custom agents from Redis
9.  OrchestratorAgent()               → Initialize with module registry
10. SchedulerAgent.start_loop()       → Start background cron loop
11. MonitorAgent.start_loop()         → Start background health-check loop
```

### Persistence Reference

| Data | Redis key / path | Durability | Restored at |
|---|---|---|---|
| LLM provider settings | `ninko:settings:llm_providers` | Persistent | Startup |
| Embedding model | `ninko:settings:embed_model` | Persistent | Startup |
| Active SafeGuard profile ID | `ninko:settings:safeguard` | Persistent | Startup |
| SafeGuard profiles | `ninko:safeguard:profiles` (hash) | Persistent | Startup |
| Per-chat SafeGuard profile | `ninko:safeguard:profile:chat:{id}` | 24h TTL | Per request |
| Module settings | `ninko:settings:modules` | Persistent | On demand |
| Module connections | `ninko:connections:{module_id}` | Persistent | ConnectionManager |
| Connection secrets | Vault / SQLite (`ninko:secrets`) | Persistent | Per request |
| Dynamic agents | `ninko:agents` | Persistent | load_from_redis() |
| Agent souls | `ninko:souls` | Persistent | load_from_redis() |
| Per-agent SafeGuard profile | `ninko:agent_configs` (hash) | Persistent | Per request |
| Semantic memory | ChromaDB `ninko_memory` | Persistent (PVC) | Auto-connect |
| Chat history | `ninko:history:{session_id}` | 7-day TTL | Per session |
| Workflows | `ninko:workflows` | Persistent | load() |
| Workflow run logs | `ninko:workflow:runs:{id}` | Persistent | Per request |
| Scheduled tasks | `ninko:scheduler:tasks` | Persistent | Startup |
| Task execution logs | `ninko:scheduler:log:{task_id}` | 50-entry cap | Per request |
| Built-in skills | `backend/skills/` (in image) | Image-baked | load() |
| Custom skills | `/app/data/skills/` (PVC) | Persistent | load() |
| Built-in souls | `backend/souls/` (in image) | Image-baked | load() |
| Pending SafeGuard confirmation (bot) | `ninko:safeguard_pending:{session}` | 300s TTL | Per request |
| Active theme | `ninko:settings:theme_active` | Persistent | Startup |
| Branding settings | `ninko:settings:branding` | Persistent | On demand |
| Language setting | `ninko:settings:language` | Persistent | On demand |

### Infrastructure

| Service | Container | Port | Notes |
|---|---|---|---|
| Backend (FastAPI) | `ninko-backend` | 8000 | Whisper + Piper TTS included |
| Redis | `ninko-redis` | 6379 | Primary state store |
| ChromaDB | `ninko-chromadb` | 8100 → 8000 | Pinned to v0.4.24, numpy < 2.0 |
| SearXNG | `ninko-searxng` | 8080 | Only for the web search module |

> **Piper TTS** is only included in the image when built with `--build-arg INSTALL_PIPER=true`. `docker compose build backend` sets this automatically.

---

## 18. Theme System

### Data Model

`ThemeDefinition` contains:
- Metadata: `id`, `name`, `description`, `version`, `author`, `preview_url`
- Token maps: `tokens_dark`, `tokens_light` (CSS custom property overrides)

### Persistence

- Built-in themes: `backend/themes/<theme_id>/theme.json` (in image)
- Custom themes: `data/themes/<theme_id>/theme.json` (persistent volume)
- Active theme: Redis key `ninko:settings:theme_active`

### Theme in the Frontend

On startup and on light/dark toggle:
- Active tokens are applied to `document.documentElement.style`
- The mode-specific token set is used automatically (`tokens_dark` vs. `tokens_light`)

**FOUC prevention:** An inline `<script>` in `<head>` reads `localStorage('ninko_theme')` synchronously and sets `light-mode-pre` on `<html>` — before the first pixel is rendered. `body` starts with `opacity: 0` and a 180ms transition; `init()` sets `opacity: 1` after all async setup completes.

---

## 19. REST API Reference

**Base URL:** `http://localhost:8000` (Dev) · `https://ninko.your-domain.local` (Prod via Traefik)

**Interactive docs:** `http://localhost:8000/docs` (Swagger UI) · `http://localhost:8000/redoc` (ReDoc)

**General conventions:**
- All responses are JSON unless otherwise noted
- Errors: `{"detail": "Error message"}`
- Pagination: via `limit` query parameter where applicable
- Date fields: ISO-8601 format (`2026-01-15T08:30:00Z`)
- Secret fields (ending in `_KEY`, `_PASSWORD`, `_TOKEN`, `_SECRET`) are always masked in responses

---

### 19.1 Chat

#### `POST /api/chat/`

Sends a user message through the orchestrator.

**Request Body:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `message` | string | ✓ | — | User's message (1–10,000 characters) |
| `session_id` | string | — | `"default"` | Session ID for chat history |
| `language` | string | — | `"de"` | Response language |
| `confirmed` | bool | — | `false` | `true` → skip SafeGuard for this request |
| `force_module` | string \| null | — | `null` | Module name or custom agent UUID (bypasses routing) |

**Response `200 ChatResponse`:**

| Field | Type | Description |
|---|---|---|
| `response` | string | Agent's response |
| `module_used` | string \| null | Which module responded (e.g. `"kubernetes"`) |
| `session_id` | string | Echo of the session ID |
| `compacted` | bool | `true` → chat history was compacted |
| `timestamp` | datetime | Response timestamp |
| `confirmation_required` | bool | `true` → SafeGuard has blocked |
| `safeguard` | object \| null | `{category, rationale, violation}` when blocked |

**Example:**
```http
POST /api/chat/
Content-Type: application/json

{
  "message": "Show all failing pods",
  "session_id": "user-abc-123",
  "language": "en"
}
```

```json
{
  "response": "I found the following pods in an error state: ...",
  "module_used": "kubernetes",
  "session_id": "user-abc-123",
  "compacted": false,
  "timestamp": "2026-04-03T10:15:30Z",
  "confirmation_required": false,
  "safeguard": null
}
```

---

#### `GET /api/chat/stream?session_id={id}`

SSE stream for live status updates during chat processing.

**Response:** `text/event-stream`

Each event has the format:
```
data: {"type": "status", "message": "Kubernetes agent responding..."}

data: {"type": "tool", "tool": "list_pods", "status": "running"}

data: {"type": "done"}
```

---

#### `GET /api/chat/history/{session_id}`

Retrieve the chat history of a session.

**Response:**

| Field | Type | Description |
|---|---|---|
| `session_id` | string | Session ID |
| `messages` | list[ChatMessage] | Message list |
| `total` | int | Number of messages |

`ChatMessage`: `{role: "user"|"assistant"|"system", content: string, timestamp: datetime|null}`

---

#### `DELETE /api/chat/history/{session_id}`

Delete the chat history of a session (removes the Redis key).

---

#### `PUT /api/chat/history/{session_id}`

Fully replace the chat history.

**Request Body:** `{"messages": [{"role": "user", "content": "..."}]}`

---

#### `GET /api/chat/ui-history`

Retrieve all saved conversations (cross-device, stored in Redis).

---

#### `POST /api/chat/ui-history`

Save or update a conversation.

**Request Body:** `{"id": "uuid", "title": "Kubernetes Debugging", "timestamp": "...", "messages": [...]}`

---

#### `DELETE /api/chat/ui-history/{conv_id}`

Delete a saved conversation.

---

### 19.2 Agents

#### `GET /api/agents/`

List all custom agents.

**Response:** `{"agents": [AgentDefinition], "total": int}`

`AgentDefinition` fields: `id`, `name`, `description`, `system_prompt`, `llm_provider_id`, `enabled`, `created_at`, `updated_at`

---

#### `POST /api/agents/` *(201)*

Create a new custom agent.

**Request Body `AgentCreate`:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ | — | Display name (1–128 characters) |
| `description` | string | — | `""` | Short description (shown in the orchestrator's routing prompt) |
| `system_prompt` | string | — | `""` | System prompt; bullet points for capabilities recommended |
| `llm_provider_id` | string \| null | — | `null` | Provider ID; null = global default |
| `enabled` | bool | — | `true` | Is the agent active? |

**Response:** `{"id": "uuid", "status": "created"}`

---

#### `GET /api/agents/{agent_id}`

Retrieve a single agent.

**Response:** `AgentDefinition` + `soul_md: string | null` (Soul MD content if present)

---

#### `PUT /api/agents/{agent_id}`

Update an agent. Same fields as `POST`. The running agent is **immediately** re-instantiated.

---

#### `DELETE /api/agents/{agent_id}`

Delete an agent (Redis + Soul MD + `AgentConfigStore` entry).

---

#### `GET /api/agents/templates`

Retrieve built-in agent templates.

**Response:** `{"templates": [Template]}`

`Template` fields: `id`, `label`, `icon`, `category`, `description`, `tags`, `suggested_modules`, `system_prompt`

Built-in template IDs: `it_ops`, `k8s_specialist`, `security_scanner`, `monitor_reporter`, `helpdesk`, `home_automation`

---

#### `POST /api/agents/generate`

Generate an agent spec via LLM from a use case. Makes an LLM call with `max_tokens=600`.

**Request Body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `use_case` | string | ✓ | Description of the desired agent |
| `allowed_modules` | list[string] | — | Modules to include (hints for the LLM prompt) |

**Response:** `{"name": "...", "description": "...", "system_prompt": "..."}` (`<think>` blocks are removed)

---

#### `POST /api/agents/{agent_id}/duplicate` *(201)*

Duplicate an agent (new name with suffix, new UUID).

---

### 19.3 Workflows

#### `GET /api/workflows/`

List all workflows including the last run status.

**Response:** `{"workflows": [WorkflowDefinition], "total": int}`

`WorkflowDefinition` fields: `id`, `name`, `description`, `nodes`, `edges`, `variables`, `enabled`, `created_at`, `updated_at`

---

#### `POST /api/workflows/` *(201)*

Create a new workflow.

**Request Body `WorkflowCreate`:**

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | ✓ | Workflow name (1–128 characters) |
| `description` | string | — | Short description |
| `nodes` | list[WorkflowNode] | — | Node definitions |
| `edges` | list[WorkflowEdge] | — | Edges between nodes |
| `variables` | list[WorkflowVariable] | — | Workflow variables |
| `enabled` | bool | — | Default: `true` |

**`WorkflowNode`:**

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique node ID |
| `type` | string | `"trigger"`, `"agent"`, `"condition"`, `"loop"`, `"variable"`, `"end"` |
| `label` | string | Display name |
| `config` | object | Type-specific configuration |
| `position` | `{x: float, y: float}` | Canvas position |

**`WorkflowEdge`:** `{id, source_id, target_id, label}`

**`WorkflowVariable`:** `{name, value}`

---

#### `GET /api/workflows/{workflow_id}` / `PUT /api/workflows/{workflow_id}` / `DELETE /api/workflows/{workflow_id}`

Standard CRUD. DELETE also removes the run history.

---

#### `POST /api/workflows/{workflow_id}/run` *(202)*

Start a workflow asynchronously.

**Response:** `{"run_id": "uuid", "status": "started"}`

---

#### `GET /api/workflows/{workflow_id}/runs`

Run history of a workflow.

**Response:** `{"runs": [WorkflowRun], "total": int}`

`WorkflowRun` fields: `id`, `workflow_id`, `workflow_name`, `status` (`idle|running|succeeded|failed`), `started_at`, `finished_at`, `duration_ms`, `steps`, `variables`, `error`, `triggered_by`

---

#### `GET /api/workflows/runs/{run_id}`

Query the live status of a running run (polling).

**`WorkflowRunStep` fields:** `node_id`, `node_type`, `node_label`, `status` (`pending|running|succeeded|failed|skipped`), `started_at`, `finished_at`, `duration_ms`, `output`, `error`

---

### 19.4 Scheduler

#### `GET /api/scheduler/tasks`

List all scheduled tasks.

**Response:** `{"tasks": [ScheduledTaskInfo], "total": int}`

`ScheduledTaskInfo` fields: `id`, `name`, `cron`, `enabled`, `prompt`, `workflow_id`, `agent_id`, `target_module`, `last_run`, `next_run`, `last_result`

---

#### `POST /api/scheduler/tasks` *(201)*

Create a new task.

**Request Body `ScheduledTaskCreate`:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ | — | Task name (1–100 characters) |
| `cron` | string | ✓ | — | Cron expression (e.g. `"0 8 * * *"`) |
| `prompt` | string | — | `""` | Free prompt → orchestrator |
| `workflow_id` | string \| null | — | `null` | Workflow ID → WorkflowEngine |
| `agent_id` | string \| null | — | `null` | Custom agent ID → DynamicAgentPool |
| `target_module` | string \| null | — | `null` | Route directly to a module agent |
| `enabled` | bool | — | `true` | Task active immediately? |

Execution priority: `workflow_id` → `agent_id` → `prompt`.

---

#### `PUT /api/scheduler/tasks/{task_id}`

Update a task (`ScheduledTaskUpdate` — all fields optional).

---

#### `DELETE /api/scheduler/tasks/{task_id}`

Delete a task.

---

#### `PUT /api/scheduler/tasks/{task_id}/toggle`

Enable/disable a task.

**Response:** `ScheduledTaskInfo` with updated `enabled` field.

---

#### `POST /api/scheduler/tasks/{task_id}/run`

Manually trigger a task immediately.

**Response:** `{"status": "triggered", "task_id": "..."}`

---

#### `GET /api/scheduler/tasks/{task_id}/logs`

Execution logs for a task.

**Query params:** `limit` (max 50, default 20)

**Response `TaskExecutionLog`:**

| Field | Type | Description |
|---|---|---|
| `task_id` | string | Task ID |
| `task_name` | string | Task name |
| `timestamp` | datetime | Execution timestamp |
| `status` | string | `"ok"` or `"error"` |
| `module_used` | string \| null | Module used |
| `prompt` | string | Executed prompt |
| `response` | string | LLM response |
| `duration_ms` | int | Execution duration in milliseconds |

---

### 19.5 Settings — LLM

#### `GET /api/settings/llm`

Retrieve current LLM configuration.

**Response `LlmSettingsResponse`:**

| Field | Type | Description |
|---|---|---|
| `backend` | string | `"ollama"`, `"lmstudio"`, `"openai_compatible"`, `"litellm"` |
| `base_url` | string | Provider base URL |
| `model` | string | Active model |
| `api_key` | string | Always `""` (never returned) |
| `api_key_set` | bool | `true` if an API key is stored |
| `source` | string | `"default"` or `"redis"` |

---

#### `PUT /api/settings/llm`

Update LLM configuration. Request Body `LlmSettings`: `backend`, `base_url`, `model`, `api_key`, `verify_ssl` (bool, default `true`).

---

#### `GET /api/settings/llm/embed-model` / `PUT /api/settings/llm/embed-model`

Read/set the global embedding model. PUT body: `{"model": "nomic-embed-text:latest"}`

---

#### `GET /api/settings/llm/providers`

List all configured LLM providers.

**Response:** List of `LLMProvider`

`LLMProvider` fields: `id`, `name`, `backend`, `base_url`, `model`, `api_key` (always `""`), `is_default`, `status` (`unknown|connected|unreachable`), `created_at`, `context_window`, `verify_ssl`

---

#### `POST /api/settings/llm/providers` *(201)*

Create a new LLM provider.

**Request Body `LLMProviderCreate`:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ | — | Display name (1–128 characters) |
| `backend` | string | ✓ | `"ollama"` | `"ollama"`, `"lmstudio"`, `"openai_compatible"`, `"litellm"` |
| `base_url` | string | ✓ | — | Base URL (`/v1` is appended automatically if missing) |
| `model` | string | ✓ | — | Model name (e.g. `"qwen2.5:14b"`) |
| `api_key` | string | — | `""` | API key (only for `openai_compatible`/`litellm`) |
| `is_default` | bool | — | `false` | Set as default |
| `context_window` | int | — | `0` | Override the auto-detected context window |
| `verify_ssl` | bool | — | `true` | Verify TLS certificate |

---

#### `PUT /api/settings/llm/providers/{provider_id}` / `DELETE /api/settings/llm/providers/{provider_id}`

Update / delete a provider.

---

#### `POST /api/settings/llm/providers/{provider_id}/test`

Test the connection to a provider.

**Response:** `{"ok": true, "models": ["model1", "model2"], "latency_ms": 245}` or `{"ok": false, "error": "Connection refused"}`

---

#### `GET /api/settings/llm/context-window`

Query the context window of the active model.

**Response:** `{"context_window": 32768, "model": "qwen2.5:14b", "source": "api"}`

---

#### `PUT /api/settings/llm/default`

Set the default provider. Body: `{"provider_id": "uuid"}`

---

### 19.6 Settings — Branding

#### `GET /api/settings/branding`

Retrieve dashboard branding.

**Response `BrandingSettingsResponse`:**

| Field | Type | Default | Description |
|---|---|---|---|
| `brand_name` | string | `"Ninko"` | Name in the sidebar |
| `page_title` | string | `"Ninko"` | Browser tab title |
| `logo_url` | string | `/static/images/logo_icon.png` | Logo URL |
| `welcome_mode` | string | `"image"` | `"image"`, `"text"`, `"off"` |
| `welcome_title` | string | `"Ninko"` | Welcome text title |
| `welcome_text` | string | `""` | Welcome text (Markdown) |
| `welcome_image_url` | string | (dashboard logo) | Welcome image URL |
| `welcome_show_eyes` | bool | `true` | Show Ninko eye animation |
| `show_quick_actions` | bool | `true` | Show quick action buttons |
| `source` | string | `"default"` | `"default"` or `"redis"` |

---

#### `PUT /api/settings/branding`

Update branding. Same fields without `source`.

**`POST /api/settings/branding/reset`** — Reset to default values.

**`POST /api/settings/branding/upload`** — Upload an image (multipart/form-data, field `file`). Response: `{"url": "/api/settings/branding/assets/logo.png"}`

**`GET /api/settings/branding/assets/{filename}`** — Serve an asset file.

**`DELETE /api/settings/branding/assets/{filename}`** — Delete an asset file.

---

### 19.7 Settings — Language, Modules, Kubernetes, TTS/STT

#### `GET /api/settings/language` / `PUT /api/settings/language`

Read/set the current language.

GET response: `{"language": "de", "source": "redis"}`

PUT body: `{"language": "en"}` — Possible values: `de`, `en`, `fr`, `es`, `it`, `pt`, `nl`, `pl`, `zh`, `ja`

---

#### `GET /api/settings/modules`

List all modules with their configuration.

**Response:** List of `ModuleSettingsItem`

`ModuleSettingsItem` fields: `name`, `display_name`, `enabled`, `description`, `version`, `connection` (key-value map, secrets masked)

---

#### `PUT /api/settings/modules/{module_name}`

Update module settings.

**Request Body `ModuleToggleRequest`:** `{"enabled": true, "connection": {"HOST": "192.168.1.1", "PORT": "80"}}`

Merge strategy: empty fields do not overwrite saved values (passwords are preserved).

---

#### `GET /api/settings/k8s/clusters`

List all configured Kubernetes clusters.

**Response:** `{"clusters": [K8sClusterInfo], "total": int}`

`K8sClusterInfo` fields: `name`, `context`, `is_default`, `has_kubeconfig`

---

#### `POST /api/settings/k8s/clusters` *(201)*

Create a new Kubernetes cluster.

**Request Body `K8sClusterCreate`:**

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | ✓ | Cluster name (lowercase, hyphens, 1–64 characters) |
| `kubeconfig_base64` | string | ✓ | Base64-encoded kubeconfig (min. 10 characters) |
| `context` | string | — | Kubeconfig context name (optional) |
| `is_default` | bool | — | Set as default cluster |

---

#### `DELETE /api/settings/k8s/clusters/{cluster_name}` / `PUT /api/settings/k8s/clusters/{cluster_name}/default`

Delete a cluster / set as default.

---

#### `GET /api/settings/tts` / `PUT /api/settings/tts`

Read/set TTS configuration.

GET response: `{"enabled": true, "voice": "thorsten", "lang": "de", "speed": 1.0}`

---

#### `GET /api/settings/stt` / `PUT /api/settings/stt`

Read/set STT configuration.

GET response: `{"model_size": "base", "language": "de", "device": "cpu"}`

---

### 19.8 Plugins (Marketplace)

#### `POST /api/plugins/upload` *(201)*

Upload and install a plugin ZIP.

Multipart form, field `file`. The ZIP must contain a valid Ninko module (`__init__.py`, `manifest.py`, etc.).

**Response:** `{"module_name": "pihole", "status": "installed"}`

---

#### `DELETE /api/plugins/{plugin_name}`

Uninstall a plugin. Removes files from `backend/plugins/` and unloads the module from the registry.

`plugin_name` is validated against `[a-zA-Z0-9_\-]+` (prevents path traversal).

---

#### `GET /api/plugins/marketplace/repos`

List all configured marketplace repos. The official Ninko repo is pre-installed and cannot be deleted.

---

#### `POST /api/plugins/marketplace/repos` *(201)*

Add a new repo.

**Request Body:**

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | ✓ | Display name |
| `url` | string | ✓ | GitHub repo URL (`https://github.com/owner/repo`) |
| `branch` | string | — | Branch (default: `"main"`) |
| `token` | string | — | GitHub token (for private repos) |

---

#### `PUT /api/plugins/marketplace/repos/{repo_id}` / `DELETE /api/plugins/marketplace/repos/{repo_id}`

Update / remove a repo (official repo is protected).

---

#### `GET /api/plugins/marketplace/repos/{repo_id}/modules`

List available modules from a repo (5-minute cache).

**Response:** `{"modules": [{"name": "...", "display_name": "...", "description": "...", "version": "...", "installed": true|false}]}`

---

#### `POST /api/plugins/install-from-repo/{module_name}` *(201)*

Install a module from a repo. No GitHub API rate limit — uses tarball download.

**Query param:** `repo_id` (default: `"official"`)

**Response:** `{"module_name": "...", "status": "installed", "version": "..."}`

---

### 19.9 Skills

#### `GET /api/skills/`

List all loaded skills (without content).

**Response:** `[{"name": "...", "description": "...", "modules": [...], "source": "builtin"|"runtime"}]`

---

#### `GET /api/skills/{name}`

Retrieve a single skill with full content.

**Response:** `{"name": "...", "description": "...", "modules": [...], "content": "...", "source": "..."}`

---

#### `POST /api/skills/` *(201)*

Create a new skill.

**Request Body `SkillCreate`:**

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | ✓ | Unique skill name (URL-safe) |
| `description` | string | ✓ | Short description (basis for injection matching) |
| `content` | string | ✓ | Skill content (Markdown) |
| `modules` | list[string] \| null | — | Module filter; null/empty = available to all agents |

Skills are written to `data/skills/` and survive container restarts.

---

#### `PUT /api/skills/{name}`

Update a skill. `SkillUpdate` — `description`, `content`, `modules` all optional.

---

#### `DELETE /api/skills/{name}`

Delete a skill. Built-in skills (`source: "builtin"`) cannot be deleted → `403`.

---

### 19.10 SafeGuard — Status & Global Control

#### `GET /api/safeguard/status`

Retrieve global SafeGuard status.

**Response:** `{"enabled": true, "profile_id": "moderate"}`

---

#### `POST /api/safeguard/enable` / `POST /api/safeguard/disable`

Enable SafeGuard globally (sets profile to `"moderate"`) / disable (sets profile to `"disabled"`).

---

#### `GET /api/safeguard/active` / `POST /api/safeguard/active`

Read/set the active global profile.

POST body: `{"profile_id": "strict"}`

---

### 19.11 SafeGuard — Profile Assignment

#### Per-Chat Session

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/safeguard/chats/{session_id}/profile` | Retrieve the session's profile |
| `POST` | `/api/safeguard/chats/{session_id}/profile` | Set profile (TTL 24h). Body: `{"profile_id": "..."}` |
| `DELETE` | `/api/safeguard/chats/{session_id}/profile` | Delete the chat-specific profile |

#### Per-Agent

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/safeguard/agents/{agent_id}/profile` | Retrieve the agent's profile |
| `POST` | `/api/safeguard/agents/{agent_id}/profile` | Set profile for the agent. Body: `{"profile_id": "..."}` |
| `DELETE` | `/api/safeguard/agents/{agent_id}/profile` | Delete the agent's profile |
| `GET` | `/api/safeguard/agents/{agent_id}` | SafeGuard status (legacy) |
| `POST` | `/api/safeguard/agents/{agent_id}/enable` | Enable (legacy) |
| `POST` | `/api/safeguard/agents/{agent_id}/disable` | Disable (legacy) |

#### Classifier Policy (per agent)

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/safeguard/agents/{agent_id}/policy` | Retrieve custom policy |
| `POST` | `/api/safeguard/agents/{agent_id}/policy` | Set policy. Body: `{"policy": "..."}` |
| `DELETE` | `/api/safeguard/agents/{agent_id}/policy` | Delete policy |

---

### 19.12 SafeGuard — Profile CRUD

#### `GET /api/safeguard/profiles`

List all profiles (built-in + custom).

**Response:** List of profile objects

| Field | Type | Description |
|---|---|---|
| `id` | string | Profile ID (e.g. `"moderate"`) |
| `name` | string | Display name |
| `check_user_messages` | bool | Classify user messages |
| `check_tool_calls` | bool | Check tool calls |
| `confirm_categories` | list[string] | Categories that require confirmation |
| `detect_prompt_injection` | bool | Prompt injection detection active |
| `fail_open` | bool | Pass through on LLM error |

---

#### `POST /api/safeguard/profiles` *(201)*

Create a custom profile.

**Request Body `ProfileCreateRequest`:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | string | ✓ | — | Unique profile ID |
| `name` | string | ✓ | — | Display name |
| `check_user_messages` | bool | ✓ | — | Classify user messages |
| `check_tool_calls` | bool | ✓ | — | Check tool calls |
| `confirm_categories` | list[string] | ✓ | — | e.g. `["DESTRUCTIVE", "STATE_CHANGING"]` |
| `detect_prompt_injection` | bool | — | `false` | Injection detection |
| `fail_open` | bool | — | `false` | Pass through on LLM error |

---

#### `GET /api/safeguard/profiles/{profile_id}` / `PUT /api/safeguard/profiles/{profile_id}` / `DELETE /api/safeguard/profiles/{profile_id}`

Read / update / delete a single profile *(204)*.

PUT and DELETE on built-in profiles → `403 Forbidden`.

---

### 19.13 SafeGuard — Audit Log

#### `GET /api/safeguard/audit`

Retrieve audit log entries.

**Query Params:**

| Param | Type | Description |
|---|---|---|
| `category` | string | `SAFE`, `STATE_CHANGING`, `DESTRUCTIVE`, `PROMPT_INJECTION`, `UNKNOWN` |
| `action` | string | `allowed`, `blocked`, `confirmed` |
| `outcome` | string | Outcome of the tool call |
| `agent_id` | string | Filter by agent ID |
| `session_id` | string | Filter by session ID |
| `from_ts` | string | ISO timestamp (earliest date) |
| `to_ts` | string | ISO timestamp (latest date) |
| `search` | string | Free-text search in message/rationale |
| `limit` | int | Max entries (default: 200, max: 2000) |

---

#### `DELETE /api/safeguard/audit`

Delete the entire audit log.

---

### 19.14 Logs

#### `GET /api/logs/`

Retrieve log entries.

**Query Params:**

| Param | Type | Description |
|---|---|---|
| `level` | string | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `category` | string | Category filter (e.g. `"orchestrator"`, `"kubernetes"`) |
| `source` | string | Logger name |
| `search` | string | Free-text search |
| `from_ts` | string | ISO timestamp |
| `to_ts` | string | ISO timestamp |
| `limit` | int | Max entries (default: 500, max: 2000) |

**Response:** `{"logs": [{"ts": "...", "level": "INFO", "category": "...", "source": "...", "message": "..."}]}`

---

#### `DELETE /api/logs/`

Delete all log entries.

---

### 19.15 Themes

#### `GET /api/themes/`

List all themes including the active theme.

**Response `ThemeListResponse`:**

| Field | Type | Description |
|---|---|---|
| `themes` | list[ThemeSummary] | All themes (built-in + custom) |
| `active_theme_id` | string | ID of the active theme |

`ThemeSummary` fields: `id`, `name`, `description`, `version`, `author`, `preview_url`, `is_builtin`, `is_active`, `source`

---

#### `GET /api/themes/item/{theme_id}`

Retrieve a single theme (including full token maps).

**Response `ThemeDefinition`:**

| Field | Type | Description |
|---|---|---|
| `id` | string | Theme ID (1–64 characters) |
| `name` | string | Display name (1–128 characters) |
| `description` | string | Short description |
| `version` | string | Version number |
| `author` | string | Author |
| `preview_url` | string | Preview image URL |
| `tokens_dark` | object | CSS custom property overrides for dark mode |
| `tokens_light` | object | CSS custom property overrides for light mode |

---

#### `GET /api/themes/active` / `PUT /api/themes/active`

Read/set the active theme. PUT body: `{"theme_id": "cyberpunk"}`

---

#### Theme CRUD

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/themes/custom` *(201)* | Create a custom theme (`ThemeDefinition`) |
| `PUT` | `/api/themes/custom/{theme_id}` | Update a theme |
| `DELETE` | `/api/themes/custom/{theme_id}` | Delete a theme |
| `POST` | `/api/themes/custom/{theme_id}/duplicate` *(201)* | Duplicate a theme |

---

#### Theme Repos

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/themes/repos` | List repos |
| `POST` | `/api/themes/repos` *(201)* | Add a repo. Body: `{"name", "repo_url", "branch", "themes_path", "github_token"}` |
| `PUT` | `/api/themes/repos/{repo_id}` | Update a repo |
| `DELETE` | `/api/themes/repos/{repo_id}` | Delete a repo (official repo is protected) |
| `GET` | `/api/themes/repos/{repo_id}/themes` | List themes from a repo |
| `POST` | `/api/themes/install-from-repo/{theme_id}` *(201)* | Install a theme from a repo. Query: `repo_id` |

---

### 19.16 Transcription (STT)

#### `POST /api/transcription/`

Transcribe an audio file (Whisper, runs locally in the backend — no external API call).

**Request:** Multipart form, field `file` (WAV, MP3, OGG, FLAC, M4A, etc.)

**Response `TranscriptionResponse`:**

| Field | Type | Description |
|---|---|---|
| `text` | string | Transcribed text |
| `language` | string | Detected language (e.g. `"de"`) |

**Configuration via env vars:** `WHISPER_MODEL_SIZE` (default: `"base"`), `WHISPER_LANGUAGE` (default: `"de"`), `WHISPER_DEVICE` (default: `"cpu"`)

---

### 19.17 Text-to-Speech (TTS)

#### `GET /api/tts/voices`

List installed Piper voices.

**Response:** `[{"name": "thorsten", "lang": "de", "quality": "medium"}]`

---

#### `POST /api/tts/synthesize`

Synthesize text to WAV audio.

**Request Body `SynthesizeRequest`:**

| Field | Type | Required | Description |
|---|---|---|---|
| `text` | string | ✓ | Text to speak (Markdown, emojis, tables are cleaned internally) |
| `lang` | string \| null | — | Language (e.g. `"de"`) — default: active UI language |
| `voice` | string \| null | — | Voice name — default: first available voice |

**Response:** `audio/wav` (binary). HTTP 503 if TTS is not available.

---

#### `POST /api/tts/voices/download`

Download a voice from HuggingFace.

**Request Body `DownloadRequest`:** `{"lang": "de", "voice": "thorsten"}`

**Response:** `{"status": "downloaded", "lang": "de", "voice": "thorsten"}`

---

#### `DELETE /api/tts/voices/{lang}/{voice}`

Delete an installed voice.

---

### 19.18 Semantic Memory

#### `POST /api/memory/store`

Write an entry to semantic memory.

**Request Body `MemoryStoreRequest`:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `content` | string | ✓ | — | Fact to store (min. 1 character) |
| `category` | string | — | `"general"` | Category (e.g. `"agent_memory"`, `"incident"`) |
| `metadata` | object | — | `{}` | Arbitrary metadata |

**Response `MemoryStoreResponse`:** `{"id": "uuid", "category": "...", "stored_at": "..."}`

---

#### `POST /api/memory/search`

Semantic search in memory.

**Request Body `MemorySearchRequest`:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `query` | string | ✓ | — | Search query |
| `top_k` | int | — | `5` | Number of results (1–50) |
| `category` | string \| null | — | `null` | Search only in this category |

**Response `MemorySearchResponse`:** `{"query": "...", "results": [MemoryEntry], "total": int}`

`MemoryEntry` fields: `id`, `content`, `distance` (cosine distance, 0 = identical), `metadata`

---

#### `GET /api/memory/incidents`

Retrieve current incidents from memory.

**Query params:** `query` (search term), `top_k` (default: 10)

---

#### `GET /api/memory/stats`

Memory statistics.

**Response `MemoryStatsResponse`:** `{"collection": "ninko_memory", "document_count": 142}`

---

### 19.19 Module Connections

#### `GET /api/connections/{module_id}`

List all connections for a module.

**Response:** `{"module_id": "...", "connections": [ConnectionRead], "total": int}`

`ConnectionRead` fields:

| Field | Type | Description |
|---|---|---|
| `id` | string | Connection UUID |
| `module_id` | string | Module ID |
| `name` | string | Connection name |
| `environment` | string | `prod`, `staging`, `dev`, `lab`, `local`, `unknown` |
| `description` | string \| null | Optional description |
| `is_default` | bool | Default connection? |
| `config` | object | Non-secret key-value pairs |
| `vault_keys` | object | Which keys are stored in Vault |
| `status` | string \| null | Connection status (optional) |

---

#### `POST /api/connections/{module_id}` *(201)*

Create a new connection.

**Request Body `ConnectionCreate`:**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | ✓ | — | Connection name |
| `environment` | string | ✓ | `"unknown"` | `prod`, `staging`, `dev`, `lab`, `local`, `unknown` |
| `description` | string \| null | — | `null` | Optional description |
| `is_default` | bool | — | `false` | Set as default |
| `config` | object | ✓ | `{}` | Non-secret parameters (URLs, ports, etc.) |
| `secrets` | object | — | `{}` | Secret fields → stored in Vault |

**Important:** Fields in `config` ending in `_KEY`, `_PASSWORD`, `_TOKEN`, or `_SECRET` are automatically redirected to Vault.

---

#### `PUT /api/connections/{module_id}/{connection_id}`

Update a connection (`ConnectionUpdate` — all fields optional).

**Important:** Empty secret fields (`""`) do **not** overwrite saved Vault values. Secrets are preserved if not explicitly re-set.

---

#### `DELETE /api/connections/{module_id}/{connection_id}` *(204)*

Delete a connection and all its associated Vault secrets.

---

### 19.20 Secrets

#### `GET /api/secrets/`

List all secret keys (**no values** — key names only).

**Response `SecretListResponse`:** `{"keys": ["PIHOLE_PASSWORD", "OPENAI_API_KEY"]}`

---

#### `POST /api/secrets/`

Store or update a secret.

**Request Body `SecretSetRequest`:** `{"key": "MY_SECRET_KEY", "value": "secretvalue123"}`

**Response `SecretSetResponse`:** `{"key": "MY_SECRET_KEY", "status": "stored"}`

---

#### `GET /api/secrets/{key}`

Check whether a secret exists (value is **never** returned).

**Response:** `{"key": "MY_SECRET_KEY", "exists": true}`

---

#### `DELETE /api/secrets/{key}`

Delete a secret.

**Response `SecretDeleteResponse`:** `{"key": "MY_SECRET_KEY", "status": "deleted"}`

---

#### `GET /api/secrets/health/check`

Check the health of the secrets backend.

**Response `VaultHealthResponse`:** `{"backend": "vault"|"sqlite", "healthy": true, "message": "Connected to Vault at http://vault:8200"}`

---

### 19.21 Auth

#### `POST /api/auth/login`

Admin login via session cookie.

**Request Body `LoginRequest`:** `{"username": "admin", "password": "..."}`

**Response:** `{"status": "ok", "role": "admin"}` + `Set-Cookie: ninko_session=...`

---

#### `POST /api/auth/logout`

Admin logout (delete session cookie).

---

#### `GET /api/auth/me`

Retrieve current auth status.

**Response:** `{"authenticated": true, "role": "admin"}` or `{"authenticated": false}`

---

### 19.22 Module Registry

#### `GET /api/modules` / `GET /api/modules/`

List all registered modules.

**Response:** List of `ModuleInfo` with `name`, `display_name`, `description`, `version`, `enabled`, `api_prefix`

---

#### `GET /api/modules/tabs`

Dashboard tab metadata for all enabled modules.

**Response:** List of `ModuleTabInfo` with `id`, `label`, `icon`, `html_url`, `js_url`

---

#### `GET /api/modules/health`

Retrieve the health status of all modules.

**Response:** `{"modules": {"kubernetes": {"status": "ok"}, "pihole": {"status": "error", "detail": "Auth failed"}}}`

---

#### `GET /api/modules/{module_name}/frontend/{filename}`

Serve a module frontend file (`tab.html` or `tab.js`).

---

### 19.23 WebSocket

#### `WS /ws`

Real-time log streaming and alert notifications.

**Connection:** `ws://host:8000/ws` (or `wss://` with TLS)

The WebSocket sends JSON objects:

**Log event:**
```json
{
  "type": "log",
  "ts": "2026-04-03T10:15:30Z",
  "level": "INFO",
  "category": "kubernetes",
  "source": "kubernetes.agent",
  "message": "Pod nginx-abc restarted successfully"
}
```

**Alert event (from the Monitor Agent):**
```json
{
  "type": "alert",
  "severity": "critical",
  "module": "kubernetes",
  "message": "3 pods in CrashLoopBackOff in namespace production",
  "ts": "2026-04-03T10:15:30Z"
}
```

**Status event (from the chat SSE bus):**
```json
{
  "type": "status",
  "session_id": "user-abc-123",
  "message": "Kubernetes agent responding..."
}
```

---

### 19.24 Image Generation

#### `GET /api/images/{filename}`

Serve a generated image (stored locally after generation).

---

#### `GET /api/settings/image-provider`

Retrieve image provider configuration (API key masked).

**Response:** `{"backend": "together", "model": "black-forest-labs/FLUX.1-schnell", "api_key": "sk-***"}`

---

#### `PUT /api/settings/image-provider`

Update image provider configuration.

**Request Body `ImageProviderConfig`:**

| Field | Type | Description |
|---|---|---|
| `backend` | string | Provider ID (e.g. `"together"`, `"openai"`, `"google"`, `"local"`) |
| `api_key` | string | Provider API key |
| `model` | string | Model name (e.g. `"black-forest-labs/FLUX.1-schnell"`) |

---

### 19.25 HTTP Status Codes

| Code | Meaning | When |
|---|---|---|
| `200 OK` | Successful request | Standard success |
| `201 Created` | Resource created | POST endpoints that create |
| `202 Accepted` | Async job started | Workflow run, task trigger |
| `204 No Content` | Successfully deleted | DELETE without response body |
| `400 Bad Request` | Invalid input | Validation error, wrong parameters |
| `401 Unauthorized` | Not logged in | No valid session |
| `403 Forbidden` | Insufficient permissions | Built-in resource is read-only |
| `404 Not Found` | Resource not found | Unknown ID or name |
| `409 Conflict` | Resource already exists | Duplicate ID on creation |
| `422 Unprocessable Entity` | Pydantic validation error | Missing required fields, wrong type |
| `500 Internal Server Error` | Server-side error | LLM unreachable, Redis down |
| `503 Service Unavailable` | Service not available | TTS disabled, ChromaDB down |

---

## 20. Operational Migration Notes (Apr 2026)

- Runtime namespace migrated from `kumio` to `ninko`.
- Connection metadata moved to tenant-aware keys:
  - Legacy: `ninko:connections:<module>`
  - Current: `ninko:connections:default:<module>` (single-tenant default)
- Backend now includes compatibility fallback to read legacy keys and auto-migrate them.
- First-login password change updates the session cookie immediately to avoid stale auth lockout.
- SafeGuard destructive prefilter no longer treats `wissen` as destructive to prevent German false positives.
- Image generation writes to a verified writable directory chain (`$NINKO_IMAGES_DIR`, `/app/data/images`, `data/images`, `/tmp/ninko-images`).

---

*Contributor notes, known gotchas, and architecture decisions: [CLAUDE.md](CLAUDE.md) · Version history: [CHANGELOG.md](CHANGELOG.md)*
