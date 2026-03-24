# Changelog

All notable changes to Ninko are documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

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
