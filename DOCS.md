# Ninko — User & Developer Documentation

This document covers the Ninko platform in depth: the dashboard, AI agent architecture, modules, memory system, automation features, and developer extension points.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [The Orchestrator — 4-Tier Routing](#2-the-orchestrator--4-tier-routing)
3. [How an Agent Processes a Request](#3-how-an-agent-processes-a-request)
4. [Safeguard Middleware](#4-safeguard-middleware)
5. [Semantic Memory](#5-semantic-memory)
6. [Skills System](#6-skills-system)
7. [Soul System](#7-soul-system)
8. [LLM Providers](#8-llm-providers)
9. [Module Connections](#9-module-connections)
10. [Chat Interface](#10-chat-interface)
11. [Custom Agents](#11-custom-agents)
12. [Workflows (DAG Automation)](#12-workflows-dag-automation)
13. [Scheduler (Scheduled Tasks)](#13-scheduler-scheduled-tasks)
14. [Modules Reference](#14-modules-reference)
15. [Security](#15-security)
16. [Developing a Module](#16-developing-a-module)
17. [Startup Sequence & Persistence Reference](#17-startup-sequence--persistence-reference)

---

## 1. Architecture Overview

Ninko is a modular, AI-powered IT Operations platform. Its design follows two core principles:

- **Immutable core** — no module name is hardcoded in the orchestrator or routing logic. Every module registers itself at startup.
- **Auto-discovering modules** — adding a new module requires only creating a folder under `backend/modules/`. Nothing else in the codebase needs to change.

```
┌───────────────────────────────────────────────────────┐
│                    Ninko Dashboard                    │
│    Chat  │  Kubernetes  │  Proxmox  │  GLPI  │  …    │
└───────────────────────┬───────────────────────────────┘
                        │
┌───────────────────────▼───────────────────────────────┐
│              Orchestrator Agent                       │
│  Tier 1: Direct  │  Tier 2: Module  │  Tier 3: Dyn.  │
│                  Tier 4: Pipeline                     │
└───────────────────────┬───────────────────────────────┘
                        │
┌───────────────────────▼───────────────────────────────┐
│               Module Registry                         │
│         Auto-Discovery · backend/modules/             │
└──────┬──────────┬──────────┬──────────┬──────────────┘
       │          │          │          │
  Kubernetes  Proxmox     GLPI     + 12 more modules
       │          │          │
┌──────▼──────────▼──────────▼────────────────────────┐
│  LLM Factory  │  ChromaDB  │  Redis  │  Vault/SQLite │
│  (Ollama/LMS) │  (Memory)  │ (Cache) │   (Secrets)   │
└─────────────────────────────────────────────────────┘
```

**Request lifecycle (simplified):**

```
User input → Safeguard (pre-check) → Orchestrator (tier routing)
  → [Module Agent | Dynamic Agent | Pipeline] → BaseAgent.invoke()
  → [Soul + RAG + Skills + Language] → ReAct loop with tools → Response
  → Auto-memorize (background) → Response to user
```

---

## 2. The Orchestrator — 4-Tier Routing

The `OrchestratorAgent` is the central brain. Every user message passes through it (unless safeguard blocks it first). It determines the best way to handle the request via a 4-tier decision hierarchy.

### Tier 1 — Direct Answer

**Condition:** The message is short (< 120 characters) AND contains no action verbs.

Action verbs that trigger escalation: `create`, `delete`, `update`, `install`, `configure`, `restart`, `scale`, `deploy`, `run`, `start`, `stop`, `remove`, `show me`, and their equivalents in all 10 supported languages.

If the message passes both checks, the orchestrator answers directly from LLM knowledge — no module invocation, no tool use. This makes simple questions like "What is a Kubernetes pod?" fast and cheap.

### Tier 2 — Module Agent

**Condition:** The message is about a specific module (e.g., Kubernetes, Pi-hole, Proxmox).

Module detection is a **two-stage** process:

**Stage 1 — Keyword fast-path** (no LLM call):
- Each module registers `routing_keywords` in its manifest.
- The orchestrator scores every module against the tokenized message.
- Short keywords (< 7 chars) require `\b` word-boundary matching (e.g., `"pod"` won't match `"tripod"`).
- Long keywords (≥ 7 chars) also use compact substring matching (e.g., `"ipadresse"` matches `"ip-adresse"`).
- If **exactly one** module scores above zero → dispatch immediately.

**Stage 2 — LLM classification** (fires only when Stage 1 is ambiguous):
- Fires when: no module matched at all (score = 0) OR two or more modules tied.
- Builds a dynamic prompt from all module descriptions and routing keywords — no hardcoding.
- 8-second timeout; falls back to keyword behavior on timeout or error.
- Result is cached by MD5(message) with a 60-second TTL to avoid duplicate calls.

Once a module is identified, the orchestrator calls `call_module_agent(module_name, user_task)`, which routes to that module's `BaseAgent` subclass.

### Tier 3 — Dynamic Agent

**Condition:** No module match AND the message is complex (not a simple query).

The orchestrator searches the `DynamicAgentPool` for an existing custom agent that is a good match for the task (Jaccard keyword-overlap ≥ 18%). If found, it reuses that agent. If not found, it creates a new one on the fly:

1. LLM generates an agent specification (name, description, system prompt) as JSON.
2. `create_custom_agent(name, system_prompt, description)` registers the agent in Redis and instantiates it as a `BaseAgent`.
3. The new agent has 4 base tools: `execute_cli_command`, `call_module_agent`, `recall_memory`, `remember_fact`.
4. The agent handles the task and is available for future requests.

### Tier 4 — Pipeline (Multi-step / Compound)

**Condition:** The message involves multiple modules simultaneously, or contains explicit multi-step patterns like "first … then …", "step 1 … step 2 …".

The orchestrator uses `run_pipeline`, which:
1. Makes a single LLM call to produce a structured JSON execution plan.
2. Executes each step sequentially via the `WorkflowEngine`.
3. Passes the output of each step to the next as `{previous_output}`.

Example: *"Check Kubernetes and send me a Telegram report"* → two pipeline steps (kubernetes → telegram).

### Core Orchestrator Tools

Beyond routing, the orchestrator has its own tools it can invoke during a conversation:

| Tool | What it does |
|---|---|
| `execute_cli_command` | Run a shell command on the backend host |
| `create_custom_agent` | Create and register a new Tier-3 dynamic agent |
| `install_skill` | Write a SKILL.md to the persistent volume and hot-reload |
| `create_linear_workflow` | Build and save a workflow programmatically |
| `execute_workflow` | Trigger a saved workflow by ID |
| `remember_fact` | Store a fact in semantic memory |
| `recall_memory` | Semantic search over long-term memory |
| `forget_fact` / `confirm_forget` | Two-step memory deletion (preview then confirm) |
| `call_module_agent` | Delegate a task to any module agent by name |
| `run_pipeline` | Execute a sequential JSON plan |

---

## 3. How an Agent Processes a Request

All agents — module agents, dynamic agents, and the orchestrator — share the same `BaseAgent.invoke()` foundation. Understanding this flow explains everything from context management to why Ninko "remembers" things.

### Invoke Flow

```
BaseAgent.invoke(user_message, session_id, chat_history)
│
├─ 1. Context-window calibration (first call only, cached)
│     Query LLM provider for model's context window.
│     Set history budget = 25% of window − MAX_OUTPUT_TOKENS.
│
├─ 2. History trimming / compaction
│     If token count > budget:
│     └─ LLM summarizes old messages into a compression summary.
│        Summary is inserted as a SystemMessage at position 1.
│
├─ 3. System prompt assembly (in this exact order):
│     a. Soul MD            ← persistent agent identity
│     b. Core system_prompt ← tools + behavior instructions
│     c. Connection context ← active connections for this module
│     d. Compression summary ← if history was compacted
│     e. RAG context         ← top-3 semantic memory hits (cosine < 0.5)
│     f. Skills injection     ← max 2 matching SKILL.md files (threshold 12%)
│     g. Language instruction ← "Answer in Spanish. Use emojis."
│
├─ 4. JIT Tool Injection (if agent has > 6 tools)
│     Score each tool against the message.
│     Keep only the top 8 most relevant tools.
│     Create a temporary agent with the reduced tool set.
│
├─ 5. ReAct agent execution (LangGraph)
│     Timeout: 1800 seconds. Recursion limit: 10000 (effectively unlimited).
│     Real-time status events emitted to frontend (SSE status bus).
│
├─ 6. Response extraction
│     Strip <think>…</think> blocks (thinking models like Qwen3.5).
│     Extract final text from AIMessage.
│
└─ 7. Auto-memorize (background asyncio task — never blocks response)
      Cooldown: 60 seconds per agent.
      Skipped for: monitor, scheduler agents; responses < 80 chars.
      LLM extracts 1–2 permanent facts.
      Stored in ChromaDB under category "agent_memory".
```

### The Three Context Layers Explained

**Soul** — *Who is this agent?*
Injected first. Defines the agent's role, purpose, and behavior guidelines. Think of it as the agent's "personality card." Built-in souls (stored in `backend/souls/`) are baked into the image. Dynamic agent souls are auto-generated and stored in Redis.

**RAG Context** — *What does Ninko already know about this?*
Before each response, a semantic search runs against ChromaDB using the user's message as the query. Hits with a cosine distance below 0.5 are injected as context. This is how Ninko "remembers" that your Pi-hole runs on `192.168.1.10` even after a container restart.

**Skills** — *How should this agent approach this specific type of problem?*
Procedural know-how files (SKILL.md) are auto-injected when they match the message (keyword overlap ≥ 12%). Example: a "kubernetes-incident-response" skill gets injected when diagnosing CrashLoopBackOff errors.

---

## 4. Safeguard Middleware

Safeguard runs **before** the orchestrator on every user message. It classifies requests and requires explicit confirmation for anything destructive or state-changing.

### Categories

| Category | Meaning | Requires confirmation |
|---|---|---|
| `SAFE` | Read-only (status, list, show, logs) | No |
| `STATE_CHANGING` | Creates or modifies something (create pod, update DNS) | Yes |
| `DESTRUCTIVE` | Irreversible (delete, rm -rf, DROP TABLE) | Yes |
| `UNKNOWN` | Parse error or LLM failure | Yes (fail-safe) |

### Three-Stage Evaluation

**Stage 1 — Disabled check**
If safeguard is globally disabled (`POST /api/safeguard/disable`) or disabled for this specific agent, the request passes immediately. No LLM call.

**Stage 2 — Keyword pre-filter** (messages ≤ 200 characters)
A fast in-process check against curated keyword lists in all 10 supported languages:
- Safe patterns: `show`, `list`, `get`, `logs`, `status`, `what`, `explain`, `wie`, `pokaż`, `显示`, `表示`, …
- Destructive terms: `delete`, `rm -`, `drop`, `lösche`, `supprim`, `elimin`, `削除`, …
- State-changing terms: `create`, `deploy`, `scale`, `erstell`, `crée`, `crea`, `作成`, …

Priority: safe → destructive → state-changing. First match wins. No LLM call needed.

> **Note:** `"del"` is intentionally absent from destructive keywords. In Spanish, Italian, and French it is a common preposition ("del pod" = "of the pod"). The LLM classifier handles the rare `del` command case.

**Stage 3 — LLM classifier** (if no pre-filter match)
An LLM call with `max_tokens=150` and an 8-second timeout classifies the request. The response is parsed robustly: `<think>` blocks are stripped first, markdown fences removed, and the first `{…}` JSON object is extracted if the model wraps it in prose.

### Confirmation Flow

**Dashboard (REST API):**
When safeguard blocks a request, the frontend receives `confirmation_required: true` and displays a confirmation dialog. The user's next click sends `confirmed: true` in the request body, which bypasses safeguard for that specific request.

**Telegram / Teams (bot channels):**
Bots cannot add a `confirmed: true` field to a follow-up message. Ninko stores the pending message in Redis with a 300-second TTL (`ninko:safeguard_pending:{session_id}`). If the user replies with a confirmation word (`yes`, `ja`, `confirm`, `ok`, `si`, `oui`, …) within 5 minutes, the original message is re-executed. Any other message starts a fresh normal flow.

### Per-Agent Toggle

Each agent can override the global safeguard setting:
- Enable: `POST /api/safeguard/agents/{agent_id}/enable`
- Disable: `POST /api/safeguard/agents/{agent_id}/disable`
- Status: `GET /api/safeguard/agents/{agent_id}`

This is also configurable via the Agent editor in the dashboard (Safeguard toggle in the General section).

**Priority:** per-agent setting > global toggle.

### Global Toggle

```
POST /api/safeguard/enable     # Enable globally
POST /api/safeguard/disable    # Disable globally (stored in Redis, survives restart)
GET  /api/safeguard/status     # Current state
```

> **Warning:** If the LLM backend is unavailable, the LLM classifier cannot run and safeguard defaults to `requires_confirmation: true` for every message. This makes Ninko unusable. Workaround: call `POST /api/safeguard/disable` until the LLM is back.

---

## 5. Semantic Memory

Ninko has a **persistent long-term memory** backed by ChromaDB vector embeddings. Unlike chat history (short-term, 7-day TTL in Redis), semantic memory survives container restarts and new sessions.

### Automatic Memory

After every agent response, a background task checks whether the conversation contained a permanently relevant fact (user preferences, known IPs, resolved incidents, decisions). If so, it is stored silently without delaying the response.

The extraction uses the active LLM with a focused prompt. It skips storage if:
- The response is shorter than 80 characters.
- The agent is `monitor` or `scheduler` (background agents).
- A 60-second cooldown is still active for this agent.

### Manual Storage

```
"Remember: the Pi-hole runs on 192.168.1.10"
"Please note that I work in the Infrastructure team"
"Save this: prod cluster runs on node k3s-prod-01"
```

### Retrieval

```
"What do you know about our infrastructure?"
"Do you remember which IP the Pi-hole was on?"
"What was the outcome of last week's incident?"
```

### Memory Deletion (Two-Step)

Deletion is intentionally two-step to prevent accidental data loss:

**Step 1 — Preview:**
```
"Forget that the Pi-hole runs on 192.168.1.10"
```
Ninko finds matching entries and shows them with their content and ID. Nothing is deleted yet.

**Step 2 — Confirm:**
```
"Yes, delete that" / "confirm" / "delete all"
```
Only after confirmation are the entries permanently removed from ChromaDB.

### How RAG Works

At every `invoke()` call, the user's message is embedded and compared against all stored memory entries via cosine similarity. Entries with a distance below 0.5 (where 0 = identical, 1 = completely different) are prepended to the system prompt as context:

```
Relevant context from memory:
- Pi-hole runs on 192.168.1.10
- Prod cluster is on node k3s-prod-01
```

This happens transparently — the agent "knows" things without being explicitly told in the current conversation.

---

## 6. Skills System

Skills are procedural domain knowledge files (SKILL.md) that are automatically injected into agent prompts when they match the current request.

**Skills vs. Memory vs. Soul:**
- **Soul** → *Who the agent is* (identity, role, behavioral guidelines)
- **Skills** → *How to approach a specific problem* (step-by-step procedures, best practices)
- **Memory** → *What has happened* (facts, IPs, past decisions, preferences)

### SKILL.md Format

```markdown
---
name: kubernetes-incident-response
description: Step-by-step guide for diagnosing pod failures in Kubernetes
modules: [kubernetes]
---

## Step 1 — Check pod status
Run `get_failing_pods()` to identify which pods are in a non-running state.

## Step 2 — Analyze logs
…
```

The `modules` field restricts injection to specific agents. An empty array means the skill is available to all agents.

### Built-in Skills

| Skill | Applies to | Purpose |
|---|---|---|
| `kubernetes-incident-response` | kubernetes | CrashLoopBackOff, OOMKilled, eviction diagnosis |
| `pihole-session-management` | pihole | Session token caching, 429 handling, rate limits |
| `ionos-dns-quirks` | ionos | IONOS API quirks (zones vs. records, em-dash in keys) |
| `proxmox-troubleshooting` | proxmox | Common Proxmox error patterns |

### Installing Custom Skills

The orchestrator can install skills via the `install_skill` tool:

```
"Teach Ninko how to handle a specific incident: [describe the procedure]"
```

Or install directly via API:
```
POST /api/skills/install
{
  "name": "my-runbook",
  "description": "Runbook for restarting the payment service",
  "content": "## Step 1\n…",
  "modules": ["kubernetes", "docker"]
}
```

Installed skills are written to `/app/data/skills/` (persistent volume) and survive container restarts.

### Injection Logic

At each `invoke()` call, `SkillsManager.find_matching_skills(message, agent_name)` runs:
1. Tokenizes the message.
2. For each skill: checks module filter, then calculates keyword overlap.
3. Returns the top 2 skills with overlap ≥ 12%.
4. They are appended to the system prompt as formatted markdown.

---

## 7. Soul System

Every agent in Ninko has a "Soul" — a Markdown file that defines its persistent identity, purpose, capabilities, and behavioral constraints. The soul is injected at the very beginning of the system prompt, before RAG context, skills, or language instructions.

### Soul Types

**Built-in Souls** (`backend/souls/*.md`)
Baked into the Docker image. Protected from deletion. Ninko's own soul (`ninko.md`) is injected into the orchestrator, shaping how it communicates and makes decisions.

**Module Agent Souls**
Auto-generated at startup from the module's manifest description and tool names. Only created if no soul exists yet. Example: the Kubernetes agent receives a soul that explains its role as a Kubernetes specialist.

**Dynamic Agent Souls**
Auto-generated when a custom agent is created via `create_custom_agent` or the Agents UI. Generated from the agent's name, description, and system prompt bullets. Stored in Redis (`ninko:souls`).

### Soul Structure

A generated soul includes:
- **Identity** — "You are [Name], [role] for Ninko."
- **Purpose** — The agent's primary mission.
- **Capabilities** — Extracted from system prompt bullet points.
- **Behavior Guidelines** — Tone, escalation paths, tool usage conventions.
- **Constraints** — What the agent should NOT do.
- **Escalation Rules** — When to call back to the orchestrator.

Souls can be viewed and edited via `GET /api/agents/{id}` (includes `soul_md` field) and through the Agent editor in the dashboard.

---

## 8. LLM Providers

Ninko supports three LLM backend types. All providers use a unified interface (`LLMFactory`) so modules and agents never need to know which backend is active.

### Supported Backends

| Backend | Use case | API key required |
|---|---|---|
| `ollama` | Local model server (Ollama) | No |
| `lmstudio` | Local model server (LM Studio) | No |
| `openai_compatible` | Any OpenAI-compatible API (OpenRouter, Groq, Heimaker, etc.) | Yes |

### Adding a Provider

1. Go to **Settings → LLM Providers**.
2. Click **Add Provider**.
3. Select the backend type.
4. Enter the base URL:
   - Ollama (Docker): `http://ollama:11434`
   - LM Studio (on your machine): `http://192.168.1.100:1234` — `/v1` is appended automatically if missing.
   - External API: full URL, e.g. `https://openrouter.ai/api/v1`
5. Enter the default model name exactly as the provider expects it (e.g., `qwen2.5:14b`, `llama3.2:3b`).
6. Toggle **Set as Default** to make this the active provider.

Switching providers takes effect immediately — no restart required. The LLM factory invalidates its context-window cache and all agents reinitialize on their next call.

### Embedding Model

The embedding model used for ChromaDB (semantic memory and RAG) is configured separately under **Settings → LLM Providers → Embedding Model**. It is independent of the active LLM provider. Changing the embedding model requires re-embedding existing memories for consistency.

### Thinking Models (Qwen3.5, DeepSeek-R1)

These models emit `<think>…</think>` blocks before their actual response. Ninko automatically strips these before returning the result to the user, before parsing safeguard JSON, and before storing to memory. No configuration needed.

---

## 9. Module Connections

Ninko supports **multi-connection** per module: one module (e.g., Kubernetes) can manage multiple environments simultaneously (prod, staging, dev, lab).

### Creating a Connection

1. Click the **gear icon** (Settings) in the top right.
2. Select a module from the left navigation (e.g., `kubernetes`, `proxmox`, `pihole`).
3. Click the **Connections** tab.
4. Fill in the fields:
   - **Name** — A descriptive label (e.g., "Prod Cluster Frankfurt").
   - **Environment** — `prod`, `staging`, `dev`, `lab`, or `local`. This label helps the Safeguard middleware assess risk.
   - **Non-secret fields** — URLs, usernames, options.
   - **Secret fields** (Vault) — Passwords, API keys, tokens. These fields always appear empty in the UI even when a value is stored, for security reasons.
5. **Set as default** — When enabled, this connection is used automatically unless a different one is requested in the chat.
6. Click **Save**.

> **Note:** Empty secret fields never overwrite previously saved secrets. You can update only non-secret fields without re-entering passwords.

### Using a Specific Connection in Chat

```
"Restart the nginx pod in the staging cluster"
"Scale the payment service in the prod connection"
"Show me the Pi-hole stats on the 'Home Lab' connection"
```

The orchestrator extracts connection hints from the message and passes them to the module agent.

### Troubleshooting

- **Profile disappears after save** — Check that the environment label exactly matches one of the allowed values (`prod`, `staging`, `dev`, `lab`, `local`). A mismatch in the Pydantic `Literal` type causes a silent 422 error.
- **Duplicate profiles** — The UI disables the Save button on click to prevent race conditions. If duplicates appear, they can safely be deleted; their Vault secrets are cleaned up automatically.

---

## 10. Chat Interface

### Sending Messages

Type your request in natural language. The orchestrator handles routing automatically. You don't need to specify a module — Ninko detects intent from keywords and context.

Examples:
- `"Show me all failing pods"` → Tier 2 → Kubernetes agent
- `"What is BGP?"` → Tier 1 → Direct LLM answer
- `"Check the cluster and send a Telegram report"` → Tier 4 → Pipeline
- `"Create an agent that monitors my Docker containers"` → Tier 3 → Dynamic agent creation

### Voice Input

Click the microphone button to record a voice message. Ninko transcribes it using Whisper (running locally inside the backend — no external API call) and sends the text as a chat message.

Supported configuration via env vars:
- `WHISPER_MODEL_SIZE` (default: `base`) — Larger models are more accurate but slower.
- `WHISPER_LANGUAGE` (default: `de`) — Helps Whisper choose the right language.
- `WHISPER_DEVICE` (default: `cpu`)

> **Note:** The microphone only works over HTTPS or `localhost`. Over plain HTTP, browsers block `navigator.mediaDevices`. Configure a Traefik IngressRoute with TLS for production use.

### Multilingual Support

Ninko supports 10 languages: German, English, French, Spanish, Italian, Portuguese, Dutch, Polish, Chinese, and Japanese. The UI language can be changed in **Settings → Language** without a page reload. Agent responses automatically switch to the selected language.

---

## 11. Custom Agents

Custom agents are specialized AI personas that can be created manually or generated automatically by the orchestrator (Tier 3).

### Creating an Agent via the UI

1. Go to the **Agents** tab.
2. Click **New Agent**.
3. Fill in:
   - **Name** — Used for routing and soul generation.
   - **Description** — Helps the Tier-3 routing match this agent to future requests.
   - **System Prompt** — Defines the agent's role and knowledge. Use bullet points for capabilities; the soul generator uses them.
   - **LLM Provider** — Leave empty to use the global default.
   - **Safeguard** — Toggle whether this agent requires confirmation for state-changing actions.
4. Click **Save**.

The agent is immediately registered in the `DynamicAgentPool`, stored in Redis (`ninko:agents`), and available for routing.

### Using an Agent

Once registered, the orchestrator automatically routes relevant requests to your agent based on keyword overlap (threshold: 18% Jaccard similarity). You can also explicitly invoke it:

```
"Ask the security-analyst agent to review the Kubernetes RBAC setup"
```

### Agent Base Tools

All custom agents receive 4 base tools regardless of their system prompt:
- `execute_cli_command` — Run shell commands
- `call_module_agent` — Invoke any module agent
- `recall_memory` — Search semantic memory
- `remember_fact` — Store to semantic memory

---

## 12. Workflows (DAG Automation)

The Workflow editor provides a visual canvas for building multi-step automation pipelines as Directed Acyclic Graphs (DAGs).

### Node Types

| Node | Configuration | Purpose |
|---|---|---|
| **Trigger** | — | Entry point of every workflow |
| **Agent** | `agent_id`, `prompt` | Delegate a task to the orchestrator (full 4-tier routing) |
| **Condition** | `expression`, `true_label`, `false_label` | Branch: `output.contains("error")` → take true path |
| **Variable** | `name`, `value` | Set a variable, supports `{other_variable}` interpolation |
| **Loop** | `variable`, `items` | Iterate over a list |
| **End** | `status` | Terminal node |

### Building a Workflow

1. Go to the **Workflows** tab and click **New Workflow**.
2. Drag nodes from the **Palette** onto the canvas.
3. Connect nodes by dragging from the output dot (bottom of a node) to the input dot (top of the next node).
4. Click a node to open the **Inspector** panel on the right and configure it.
5. Click **Save** to persist the workflow.

### Variable Interpolation

Outputs flow through the workflow via the `{previous_output}` variable. You can also define named variables with the Variable node:

```
Variable: result = "Cluster is healthy"
Agent prompt: "Summarize this for a status report: {result}"
```

### Running a Workflow

- **Manual:** Click the ▶ Run button on the workflow card.
- **Scheduled:** Assign the workflow to a scheduled task (see Section 13).
- **Via chat:** `"Execute the daily-k8s-report workflow"` — the orchestrator calls `execute_workflow`.

### Monitoring

The **Run Dashboard** shows live execution status:
- Each step shows its current state (pending → running → succeeded/failed).
- Click a step to see the full LLM output and duration.
- Failed runs show the error message and which step failed.

---

## 13. Scheduler (Scheduled Tasks)

The Scheduler runs tasks automatically on a cron schedule using background coroutines inside the backend process.

### Creating a Scheduled Task

1. Go to the **Tasks** (Aufgaben) tab.
2. Click **New Task**.
3. Fill in:
   - **Name** — A descriptive label.
   - **Schedule (Cron)** — A standard cron expression. Use the template dropdown for common intervals.
4. Select a **Task Type**:
   - **Agent Prompt** — A natural-language prompt sent through the full orchestrator routing.
   - **Call Custom Agent** — Direct invocation of a specific custom agent (bypasses orchestrator routing).
   - **Execute Workflow** — Trigger a saved workflow by ID.
5. Click **Save**.

### Cron Syntax Reference

| Expression | Meaning |
|---|---|
| `*/5 * * * *` | Every 5 minutes |
| `0 * * * *` | Every hour |
| `0 8 * * *` | Daily at 08:00 |
| `0 8 * * 1` | Every Monday at 08:00 |
| `0 */6 * * *` | Every 6 hours |

### Execution Paths

The scheduler runs tasks through three prioritized paths:

```
1. workflow_id present → WorkflowEngine.execute(workflow)
2. agent_id present   → DynamicAgentPool.get_agent_by_id(agent_id) → agent.invoke()
3. prompt present     → orchestrator.route(prompt)  [default path]
```

Scheduled tasks do **not** go through safeguard — they are trusted background processes.

### Task Logs

Click the log icon on any task card to view the last 50 execution logs, including timestamps, duration, status (ok/error), and full LLM output.

---

## 14. Modules Reference

### Kubernetes (☸)

Manages Kubernetes clusters via the official Python client.

**Capabilities:**
- Cluster health and node status
- Pod listing, log retrieval, restart
- Deployment scaling and rollout restart
- **Write operations** (v0.5.6+): `apply_manifest` (server-side apply, any resource kind), `delete_resource`, `get_resource_yaml`, `create_namespace`, `list_deployments`
- Event analysis and failure diagnosis

**Connection fields:** kubeconfig path or in-cluster service account.

**Examples:**
```
"Show all failing pods in the production namespace"
"Restart the payment-api pod"
"Create a nginx test pod in the default namespace"
"Scale the frontend deployment to 3 replicas"
"Apply this manifest: [YAML]"
```

### Proxmox (🖥)

VM and LXC container management via the Proxmox REST API.

**Examples:**
```
"List all VMs on pve-01"
"Start VM 105"
"Take a snapshot of VM 200 named 'pre-update'"
```

### GLPI Helpdesk (🎫)

Ticket and asset management via the GLPI REST API.

**Examples:**
```
"Create an incident ticket: server unreachable"
"What is the status of ticket #1234?"
"Show all open tickets assigned to me"
```

### IONOS DNS (🌐)

DNS zone and record management via the IONOS Hosting API.

**Authentication:** API key in `prefix.secret` format (two parts separated by `.`).

**Known quirk:** The IONOS API embeds records inside the zone object (`GET /zones/{id}`) rather than as a separate records endpoint. Ninko handles this automatically.

**Examples:**
```
"Which DNS zones do we have on IONOS?"
"Create an A record for dev.example.com pointing to 10.0.0.5"
"Delete the TXT record _acme-challenge.example.com"
```

### FritzBox (📶)

Home and small office network management.

**Examples:**
```
"What is my external IP address?"
"Enable the guest Wi-Fi"
"Show connected devices"
```

### Home Assistant (🏠)

Smart home automation control.

**Examples:**
```
"Turn on the living room lights"
"Set the heating to 21°C"
"What is the current temperature in the bedroom?"
```

### Pi-hole (🛡)

DNS-level ad blocking and custom DNS management (Pi-hole v6).

**Authentication:** Pi-hole web UI password, stored as a connection secret.

**Known quirk:** Pi-hole v6 uses a session-based API with rate limiting. Ninko caches the session token (5-minute TTL) and handles 429 errors with automatic retry.

**Examples:**
```
"Block the domain tracking.example.com"
"Show today's network statistics"
"Add a local DNS record for nas.home → 192.168.1.50"
```

### Docker (🐳)

Container management via the Docker socket API.

**Examples:**
```
"List all running containers"
"Show logs for container nginx-proxy"
"Restart the container my-app"
```

### Linux Server (🖥)

SSH-based remote server administration.

**Examples:**
```
"Check disk usage on server web-01"
"Show the last 50 lines of /var/log/syslog"
"Restart the nginx service"
```

### WordPress (📝)

Content management via the WordPress REST API.

**Prerequisite:** WordPress must use any permalink format other than "Plain" (Settings → Permalinks). Plain permalinks disable the REST API.

**Examples:**
```
"Create a draft post titled 'Q1 Recap'"
"List the last 5 published posts"
```

### Web Search (🔍)

Web search via a local SearXNG instance (aggregates Bing, Mojeek, Qwant).

**Configuration:** Set `SEARXNG_URL` environment variable. In Docker Compose this is set automatically; in Kubernetes it must be added to `deployment.yaml`.

**Examples:**
```
"What does Bitcoin cost right now?"
"Search the web for Kubernetes 1.30 release notes"
"Latest news about Redis 8"
```

### Email (📧)

SMTP sending and IMAP retrieval.

**Examples:**
```
"Send an email to ops@example.com: the deployment was successful"
"Show my last 5 unread emails"
```

### Telegram Bot (💬)

Full bidirectional Telegram messenger integration.

**Features:**
- Voice messages are automatically transcribed via Whisper and processed as text.
- Replies can be sent as voice (TTS via Piper) if TTS is enabled.
- Safeguard uses a pending-confirmation flow for bot channels (see Section 4).
- Session ID is tied to the Telegram User ID and persists across restarts.

**Commands:**
- `/start`, `/clear`, `/reset` — Wipe the chat history for the current session.

### Image Generation (🎨)

AI image generation via any compatible API.

**Examples:**
```
"Generate an image of a Kubernetes cluster diagram"
```

---

## 15. Security

### Local AI by Default

All LLM calls stay within your network when using Ollama or LM Studio. No data is sent to external services unless an OpenAI-compatible external provider is explicitly configured.

### Secrets

All module credentials (API keys, passwords, tokens) are stored encrypted via HashiCorp Vault or an SQLite fallback. They are never stored in plaintext on disk or returned in API responses (secret fields always appear empty in the UI).

### Safeguard

Every user-initiated message is classified before execution. State-changing and destructive operations require explicit confirmation. See Section 4 for full details.

### Destructive Action Confirmation (Proxmox)

The Proxmox module has an additional layer of protection for destructive VM operations. Set `PROXMOX_CONFIRM_DESTRUCTIVE=true` (default) to require agent-level confirmation before executing irreversible actions.

### Network Exposure

Ninko is designed for internal network use only. It is **not** designed to be exposed directly to the internet. For production use, place a reverse proxy (Traefik, Nginx) with TLS and optionally basic auth or OAuth middleware in front.

### Log Safety

Ninko writes logs to a capped Redis list (`ninko:logs`, visible in the Logs tab). Secret API keys passed through tools are not automatically masked in logs. Avoid including raw secrets in system prompts or chat messages.

### `.env` File

Never commit `.env` to version control. It is listed in `.gitignore`. Use `.env.example` as the template.

---

## 16. Developing a Module

Every module follows the same self-contained structure. Adding a new module requires only creating a folder — nothing in the core changes.

### File Structure

```
backend/modules/mymodule/
├── __init__.py       ← exports: module_manifest, agent, router
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
    name="mymodule",                          # Internal ID, lowercase
    display_name="My Module",                 # UI label
    description="Manages MyService instances",# Used by LLM for routing — keep it descriptive
    version="1.0.0",
    routing_keywords=[
        "myservice", "my-module", "specific-term",
        # Keep keywords unique across all modules to avoid routing ambiguity.
        # Short keywords (< 7 chars) use \b word-boundary matching only.
        # Keywords >= 7 chars also match inside compound words.
    ],
    api_prefix="/api/mymodule",
    dashboard_tab={"id": "mymodule", "label": "My Module", "icon": "🔧"},
    health_check=lambda: {"status": "ok"},
)
```

### agent.py

```python
from backend.agents.base_agent import BaseAgent
from backend.modules.mymodule.tools import my_tool, my_other_tool

class MyModuleAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="mymodule",
            system_prompt="You are the My Module specialist for Ninko.\n\n"
                          "Capabilities:\n"
                          "- Do X\n"
                          "- Do Y\n\n"
                          "Rules:\n"
                          "- Always confirm before deleting\n",
            tools=[my_tool, my_other_tool],
        )
```

### tools.py

```python
from langchain_core.tools import tool

@tool
def my_tool(resource_id: str, connection_id: str = "") -> str:
    """
    Retrieve the status of a resource.

    Args:
        resource_id: The ID of the resource to inspect.
        connection_id: Optional connection profile to use.

    Returns a JSON string with status details.
    """
    # Tool docstrings matter — the agent LLM uses them to decide which tool to call.
    # Keep them accurate and descriptive.
    conn = ConnectionManager.get_default_connection("mymodule", connection_id)
    ...
```

### routes.py

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/mymodule", tags=["mymodule"])

@router.get("/status")
async def get_status(connection_id: str = ""):
    """Dashboard API — always accept connection_id and pass it to tools."""
    ...
```

### frontend/tab.js

```javascript
// Must NOT use ES module syntax (no export/import).
// Core modules: define a global object and register in app.js:getTabObject()
const MyModuleTab = {
    async init() {
        // Called when the tab is first activated.
    }
};

// For plugins (ZIP-installed, cannot edit app.js):
if (typeof Ninko !== 'undefined') Ninko._pluginTabs['mymodule'] = MyModuleTab;
```

### Enabling the Module

```env
NINKO_MODULE_MYMODULE=true
```

Ninko discovers and loads the module automatically on next startup.

### Registering Secret Fields

If your module has secret connection fields (ending in `_KEY`, `_PASSWORD`, `_TOKEN`, `_SECRET`), register them in `backend/api/routes_settings.py`:
- `_get_secret_keys()` — list of field names to route through Vault
- `_get_env_connection()` — env-var fallback mapping

### Checklist

- [ ] `routing_keywords` are unique across all modules.
- [ ] Tool docstrings accurately describe what each tool does and returns.
- [ ] `manifest.description` is informative (used by LLM for routing decisions).
- [ ] `ModuleManifest.version` is bumped on breaking changes.
- [ ] Secret fields registered in `routes_settings.py`.
- [ ] Frontend tab.js does NOT use `export`/`import`.
- [ ] `routes.py` endpoints accept `connection_id: str = ""`.

---

## 17. Startup Sequence & Persistence Reference

### Startup Order (`main.py` lifespan)

```
1. ModuleRegistry        — scan backend/modules/ + backend/plugins/, import manifests
2. SoulManager.load()    — load built-in souls from backend/souls/
3. SoulManager.load_from_redis()        — merge dynamic souls from Redis
4. ModuleRegistry.auto_generate_module_souls() — create souls for modules that don't have one
5. SkillsManager.load()  — load from backend/skills/ + /app/data/skills/
6. SafeguardMiddleware.init() — restore global toggle from Redis
7. DynamicAgentPool.load_from_redis()   — instantiate custom agents from Redis
8. OrchestratorAgent()   — initialize with module registry
9. SchedulerAgent.start_loop()          — background cron loop
10. MonitorAgent.start_loop()           — background health check loop
```

### Persistence Reference

| Data | Storage key / path | Durability | Restored at |
|---|---|---|---|
| LLM provider settings | Redis `ninko:settings:llm_providers` | Persistent | Startup |
| Embedding model | Redis `ninko:settings:embed_model` | Persistent | Startup |
| Global safeguard toggle | Redis `ninko:settings:safeguard` | Persistent | Startup |
| Module settings | Redis `ninko:settings:modules` | Persistent | On demand |
| Module connections | Redis `ninko:connections:{module_id}` | Persistent | ConnectionManager |
| Connection secrets | Vault / SQLite (`ninko:secrets`) | Persistent | Per request |
| Dynamic agents | Redis `ninko:agents` | Persistent | load_from_redis() |
| Agent souls | Redis `ninko:souls` | Persistent | load_from_redis() |
| Per-agent safeguard | Redis `ninko:agent_configs` (hash) | Persistent | Per request |
| Semantic memory | ChromaDB collection `ninko_memory` | Persistent (PVC) | Auto-connect |
| Chat history | Redis `ninko:history:{session_id}` | 7-day TTL | Per session |
| Workflows | Redis `ninko:workflows` | Persistent | load() |
| Workflow run logs | Redis `ninko:workflow:runs:{id}` | Persistent | Per request |
| Scheduled tasks | Redis `ninko:scheduler:tasks` | Persistent | Startup |
| Task execution logs | Redis `ninko:scheduler:log:{task_id}` | 50-entry cap | Per request |
| Built-in skills | `backend/skills/` (in image) | Image-baked | load() |
| Custom skills | `/app/data/skills/` (PVC) | Persistent | load() |
| Built-in souls | `backend/souls/` (in image) | Image-baked | load() |
| Pending safeguard (bot) | Redis `ninko:safeguard_pending:{session}` | 300s TTL | Per request |

### Infrastructure

| Service | Container | Port |
|---|---|---|
| Backend (FastAPI) | `ninko-backend` | 8000 |
| Redis | `ninko-redis` | 6379 |
| ChromaDB | `ninko-chromadb` | 8100 → 8000 |
| SearXNG | `ninko-searxng` | 8080 |
| Whisper | Inside `ninko-backend` | — |
| Piper TTS | Inside `ninko-backend` | — |

> **Piper TTS** is only included in the image when built with `--build-arg INSTALL_PIPER=true`. `docker compose build backend` handles this automatically.

---

*For contributor notes, known gotchas, and architectural decisions, see [CLAUDE.md](CLAUDE.md). For the version history, see [CHANGELOG.md](CHANGELOG.md).*
