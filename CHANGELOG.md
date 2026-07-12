# Changelog

All notable changes to Ninko are documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added

- **Chat trace steps ("Denkschritte") persistence** (`backend/schemas/chat.py`, `frontend/app.js`): a new `StepTraceEntry` model and `HistoryMessage.steps` field let the already-rendered trace-step wrapper of an AI reply be snapshotted (`_serializeStepsFromWrapper`) and saved alongside the message via `POST /api/chat/ui-history`. `loadHistoryEntry()` rebuilds the same wrapper (`_buildStaticStepsWrapper`) on reload/history-switch instead of losing the steps, which previously only lived in the live DOM. Snapshot fields are capped client-side to the schema's `max_length` limits so an oversized trace preview can no longer make the whole history save silently fail with 422.
- **Debug-mode toggle for trace-step phases** (`frontend/app.js`, `frontend/style.css`, `frontend/index.html`): new quick-toggle button in the chat "+" menu (`toggleDebugMode`, persisted in `localStorage`). By default only `agent`/`llm`/`tool` phases and thinking-content are shown; `safeguard`/`routing`/`context`/`pipeline`/`request` phases (internal wiring) are hidden via `body.debug-mode .typing-step[data-phase=...]` CSS rules and only revealed with debug mode on.
- **Theme editor "adopt current values" button** (`frontend/features/themes.js`): `prefillThemeEditorTokens()` reads a curated list of ~55 themeable CSS custom properties via `getComputedStyle` and writes them as JSON into the Tokens-Dark textarea, giving custom-theme authors a discoverable starting point instead of guessing token names.
- **Five new built-in theme presets** (`backend/themes/{ocean,emerald,sunset,crimson,graphite}/theme.json`): Ocean Deep, Emerald Grove, Sunset Ember, Royal Crimson and Graphite Steel, each with full `tokens_dark`/`tokens_light` coverage of all ~55 themeable tokens (panels, sidebar, cards, shadows, borders, gradients, status colors) built the same way as the Arctic Flow fix above — not just a base-background tint. Seed colors are taken from the existing "Hintergrundfarben" background-preset palette (same names/hues: Ozean, Smaragd, Sonnenuntergang, Purpur, Graphit) so the two pickers feel like the same design language, with the rest of each palette (surfaces, text, shadows, accents) derived programmatically from that seed for internal consistency. `Ninko._activeThemeId` switches between all 7 presets (Default, Arctic + the 5 new ones) with distinct, verified token sets and no console errors.

### Changed

- **Theme system now reaches nearly all UI surfaces** (`frontend/style.css`, `frontend/index.html`, `frontend/features/agents.js`, `backend/themes/arctic/theme.json`): ~300 previously hardcoded hex/rgba color literals (hover/border/glass overlays, status/priority badges, SafeGuard category colors, mic-recording state, favorite-star, workflow-node-palette) were extracted into new CSS custom properties (`--fg-rgb`, `--shadow-rgb`, `--status-*`, `--sg-*`, `--wf-node-*`, `--accent-favorite`, `--error-color(-rgb)`, plus missing `--accent-*-rgb` companions) with the previous literal as default, so a theme switch now visibly re-skins those areas instead of only base colors. The built-in "Arctic Flow" theme was extended with a representative subset of the new tokens to demonstrate the wider reach.
- **Chat "+" menu widened** (`frontend/style.css`): `.chat-plus-dropdown` from 296px to 328px.

### Fixed

- **User chat bubble ignored the active theme entirely** (`frontend/style.css`): `.chat-message.user .chat-bubble` hardcoded `background: #1a1f37` — the `--bg-chat-user` token was already defined and set per-preset in every theme (including all 5 new ones), but nothing actually consumed it, so the single most prominent, always-visible chat element stayed the exact same dark navy regardless of active theme. Found by comparing computed background color across themes: it was byte-identical in every screenshot even though the surrounding page background clearly shifted, which is what had made it look like it was changing (contrast illusion against the different backdrop) on first glance. Now uses `var(--bg-chat-user)`; verified 5 distinct bubble colors across default/ocean/sunset/emerald/graphite with no console errors.
- **~30 more hardcoded panel/badge/status colors found via full literal sweep, not just the high-frequency ones** (`frontend/style.css`, `backend/themes/*/theme.json`): the previous two rounds only mapped literals matching the ~20 most-repeated exact RGB values; a full sweep of all remaining occurrences (not just top-N by frequency) turned up ~30 more one-off and low-frequency hardcoded literals, including the Module-Marketplace "Plugin installieren" card (`.module-upload-panel`, a hand-copied near-duplicate of the `--bg-card` gradient with a different alpha, visibly off-hue against non-default themes — e.g. looked purple against the Ocean theme instead of blending in), several status/badge text colors (`.text-error`, `.task-badge-error`, `.log-entry-error`, `#opnsense-tab-content .status-*`) that duplicated `--status-ok`/`--status-warning`/`--status-danger` as literals instead of referencing them, and a few more near-duplicate "glass panel" gradient stops. Added `--bg-tint-rgb`, `--bg-card-start-rgb`, `--bg-card-end-rgb` and `--bg-panel-strong-rgb` companions (backfilled into all 6 non-default theme presets) to cover the panel family; mapped the rest to existing tokens by semantic role. Deliberately left the four `.trace-phase-*` (Denkschritte phase badge: routing/agent/tool/llm) colors and the mic-recording pulse animation as theme-independent literals — those are meant to stay visually consistent and recognizable across themes, same reasoning as `--sg-injection`/`--accent-favorite`.
- **`app.js` cache version was never bumped for the last two frontend changes** (`frontend/index.html`): the Denkschritte-persistence/debug-mode-filter/popover-positioning commit and the subsequent background-settings-race-condition fix both edited `frontend/app.js`'s actual behavior without bumping its `?v=` cache-busting parameter — it stayed at `v90` (last bumped for an earlier, unrelated change) across both. Any browser that had already cached `app.js?v=90` kept serving that older build indefinitely, silently missing both fixes, regardless of what the server/CSS shipped afterwards. Investigated as the likely cause of a report that Denkschritte became invisible after activating one of the new theme presets — could not reproduce that symptom against a fresh (uncached) session across all 7 themes (static embed and live-typing paths, no console errors, byte-identical rendering), which points at exactly this kind of stale-cache mismatch between an old cached JS build and the current CSS/backend rather than a theme-specific regression. Bumped to `v91`; a hard refresh (or normal cache expiry) picks up the current code. Note: `check_cache_bump.py` only compares against `main`, so it doesn't catch a file being re-edited without a further bump once it has already diverged from `main` once in the same branch — worth remembering to re-run it after every `app.js`-touching commit, not just the first one in a session.
- **Telegram safeguard confirm buttons stayed clickable after use** (`backend/modules_catalog/telegram/bot.py`): `_handle_callback_query()` only called `answerCallbackQuery` (dismisses the button's loading spinner) but never removed the message's inline keyboard itself, so the Ja/Nein buttons remained tappable after the user already confirmed or cancelled — a second tap re-fired the same callback. New `_remove_inline_keyboard()` helper calls `editMessageReplyMarkup` with an empty keyboard immediately after acknowledging the callback, for all four confirm/cancel variants (`confirm_yes`, `confirm_no`, `confirm_tool_yes`, `confirm_tool_no`).
- **Telegram streaming preview never updated during a real run** (`backend/modules_catalog/telegram/bot.py`): `_route_with_live_preview()`'s pseudo-streaming fallback only reacted to the legacy `status_bus.emit()` events (`type: "status"`), but a real agent run emits almost exclusively `status_bus.emit_trace()` events (`type: "trace_event"` — the same stream backing the web UI's "Denkschritte"). Since the preview never saw a matching event, it stayed on the initial "💭..." placeholder until the final answer replaced it in one shot, indistinguishable from streaming being off. Now also handles `trace_event`, filtering out the same internal-wiring phases (`safeguard`, `routing`, `context`, `pipeline`, `request`) the web frontend's debug mode hides, so the preview shows live `agent`/`tool`/`llm` phase labels instead. (Real token-by-token streaming stays disabled for tool-using agents — that's intentional: `ResponseExtractionMiddleware.post_process()`, including narration-stripping, table-augmentation and image-marker extraction, only runs against `ctx.result`'s structured messages, which raw token accumulation can't provide; this fix only restores the intermediate status-preview.)
- **Theme presets only changed the base background, not panels/sidebar/cards/shadows** (`frontend/style.css`, `frontend/features/themes.js`, `backend/themes/arctic/theme.json`): the round above added ~55 themeable tokens, but the actual "glass" surfaces users see everywhere — `.sidebar`, `.module-config-card`, chat panels, popovers, box-shadows and hover/active tints — either still hardcoded raw rgba/hex literals in `style.css` instead of referencing a CSS custom property, or referenced properties (`--bg-panel`, `--bg-panel-strong`, `--bg-panel-soft`, `--bg-card`, `--bg-card-solid`, `--bg-sidenav`, `--bg-chat-user`, `--bg-active`, `--bg-body`, `--shadow-sm/md/lg/glow/card/surface`, `--border-strong/-active`, `--primary-gradient(-hover)`, `--accent-gradient-soft`) that were never part of `_THEMEABLE_TOKENS` and that the built-in "Arctic Flow" preset never overrode — so activating a theme changed `--bg-primary/secondary/tertiary` and a few accents but left every panel, the sidebar, cards and shadows in the default palette, making preset switches look broken. Added `-rgb` companions for the panel/card/surface tokens plus two new tokens for previously-untracked recurring literals (`--accent-blue-soft(-rgb)`, `--bg-surface(-rgb)`), converted ~80 more matching hardcoded literals in `style.css` to reference them, added all of the above to `_THEMEABLE_TOKENS`, and fully re-tuned Arctic's `tokens_dark`/`tokens_light` to override every one of them with a coherent cool-blue palette. Verified via a scripted Playwright run against the local stack: computed `--bg-panel`, `--bg-card-solid`, `--bg-sidenav` and `--shadow-md` (and the `.sidebar` element's actual computed `background-image`) all changed on `activateTheme('arctic')` and reverted on `activateTheme('default')`, with no console errors and no visual regression to the default theme (byte-identical resolved values, since every hardcoded literal was replaced with a variable defaulting to that exact same literal).
- **Background-color settings could silently overwrite the active theme's tint/accent on load** (`frontend/app.js`): `loadBackgroundSettings()` was fired without awaiting it, before the active theme's tokens were applied. Its async `/api/settings/background` fetch could resolve after `applyActiveThemeTokens()`, re-overwriting `--bg-tint`/`--bg-accent-1`/`--bg-accent-2` back to the stored background preference regardless of which theme was active — a race that would have undermined the theme fix above and every new preset's own tint/accent colors. Now awaited so the active theme always applies last and wins.
- **Chat "+" menu popovers no longer clipped/forced into scroll** (`frontend/app.js`, `frontend/features/safeguard.js`, `frontend/style.css`): the SafeGuard-profile picker and module-picker dropdown were `position: absolute` descendants of `.chat-plus-dropdown`, whose `overflow-y: auto` either clipped them or turned the whole menu scrollable when they opened. New `_positionFloatingPopover()` helper detaches the popover to `document.body` and positions it `position: fixed` relative to its trigger (flipping upward when there isn't room below), immune to any ancestor's overflow. Outside-click and menu-close handling were updated so clicks inside a detached popover no longer prematurely close the parent "+" menu, and closing the "+" menu now cascades to close any open popover. Also fixed a resize-doesn't-reposition edge case (closes on `resize`) and a SafeGuard-picker outside-click listener that could be permanently consumed by an inner click.
- **Built-in theme activation was broken in Docker/Kubernetes** (`backend/core/theme_manager.py`): `BUILTIN_THEMES_DIR` was computed as `<repo-root>/backend/themes`, which only exists in the local dev checkout — inside the container (`WORKDIR /app`, `COPY backend/ .`) the themes live at `/app/themes`, so every non-default theme returned 404 on activation. Now checks `/app/themes` first, falling back to the repo-root path for local/non-container runs.
- **Missing/mismatched `role` after history reload** (`frontend/app.js`): the backend normalizes `role: "ai"` to `role: "assistant"` when persisting via `HistoryMessage`. `loadHistoryEntry()` replayed the raw stored role, so `role === 'ai'` checks (trace-step embedding, retry button, TTS button) silently stopped working for any message loaded from history. Now normalized back to `'ai'` at the replay call site.
- **Leaked tool-plan/retry narration in chat answers** (`backend/agents/middleware/postprocess.py`, `backend/modules_catalog/telegram/bot.py`, `backend/modules_catalog/kubernetes/agent.py`): the model occasionally emitted its tool-calling plan or self-correction narration ("I will call get_cluster_status to…", "⚠️ N consecutive tool errors. My previous approach is wrong…") as prose directly into the final message content — sometimes glued onto the real answer with no separator (`…overview.✅ Status …`), and in one observed case repeated dozens of times when the agent kept retrying the same failing tool call. This exact class of leak already had a robust, line-by-line fix in the Telegram bot (`_strip_agent_meta_chatter`/`_strip_pipeline_headers`, tested against retry-meta leaks) that the main chat pipeline never used. Moved `_strip_agent_meta_chatter` into `agents/middleware/postprocess.py` (core), widened its recognized narration prefixes (`I will use …`, `Let's start with …`, plus the existing set), added a glued-content-marker un-gluing pre-pass, and wired it into `ResponseExtractionMiddleware` so every chat surface gets the same protection Telegram already had; the Telegram bot now imports the shared function instead of keeping its own copy. Added an explicit "never narrate tool calls" rule to the Kubernetes system prompt as a direct root-cause nudge. Regression tests cover the exact leaked-narration string, a 20×-repeated retry-error block, and a legitimate reply that merely opens with "I will …". Note: agent tool-retry is already bounded (`max_iterations = 50` in `base_agent.py`) — not a true unbounded loop, just inefficient; not addressed here.

## [1.3.9] – 2026-07-04

### Changed

- **Routing documentation aligned with runtime** (`DOCS.md`, `backend/README.md`, `PLAN.md`): removed the old 4-tier-router description from the current docs and documented the Function-Calling-first routing path, deterministic fast-paths, dynamic-agent dispatch, and pipeline fallback behavior.
- **Workflow run writes serialized** (`backend/core/workflow_engine.py`, `backend/agents/core_tools.py`): workflow run creation and updates now share the same per-workflow lock so concurrent read-modify-write paths do not overwrite each other.
- **TTS output handling** (`backend/core/tts/__init__.py`, `backend/api/routes_tts.py`): generated WAV output is stored as short-lived served files instead of being pushed through oversized tool responses.

### Fixed

- **Pipeline confirmation resume** (`backend/core/pipeline_engine.py`, `backend/api/routes_chat.py`): confirmed multi-step pipelines now execute only the confirmed step, preserve completed checkpoint results, pause again for the next unconfirmed destructive step, and return `confirmation_required=true` metadata on JSON resume responses.
- **Agent API validation** (`backend/api/routes_agents.py`): agent create/update requests now enforce reserved-name checks and the maximum system-prompt length at the API boundary instead of relying only on `DynamicAgentPool.register()`.
- **Tool permission hardening** (`backend/core/tool_permissions.py`, `backend/core/tool_registry.py`, `backend/core/safeguard.py`): read-only inference and mutation keyword handling were tightened so destructive tool names are classified conservatively.
- **Agent lifecycle/state consistency** (`backend/core/agent_pool.py`, `backend/core/agent_config_store.py`, `backend/agents/scheduler_agent.py`, `backend/agents/monitor_agent.py`): custom-agent synchronization, scheduler state, and live-agent updates now handle Redis/live-object drift more defensively.
- **Proxmox LXC power operations** (`backend/modules_catalog/proxmox/tools.py`): smart start/stop/reboot now read the guest `type` from `/cluster/resources?type=vm`, avoiding LXC containers being misclassified as QEMU VMs.

### Tests

- Added regression coverage for step-wise pipeline confirmation resume, oversized agent prompts, and Proxmox LXC/QEMU endpoint selection.
- Verified in Docker with `docker compose run --rm --no-deps --user root ... pytest tests/test_pipeline_engine.py tests/test_proxmox_power_tools.py tests/test_agent_workflow_regressions.py -q`: **64 passed**.

## [1.3.8] – 2026-06-23

### Added

- **Knowledge Graph tenant isolation** (`backend/core/knowledge_graph.py`): the singleton KG was replaced with a per-tenant `dict[str, nx.DiGraph]`. All 19 public methods now require `tenant_id: str` as the first parameter; node metadata stores the tenant as defense-in-depth. Persistence is per-tenant at `data/knowledge_graph/graph_<tenant>.json` (atomic write via `.tmp` + `replace`); legacy `graph_export.json` is still loaded for backward compat. Health check and startup log now report tenant count.
- **Per-tenant KG test coverage** (`backend/tests/test_knowledge_graph_tenant_isolation.py`): 19 focused tests covering cross-tenant isolation (read/write/delete), scope of `find_by_type`/`get_path`/`get_neighbors`, per-tenant file storage, export/import scoping, and `extract_from_incident` scoping. 1 test skipped (networkx.pagerank needs `scipy`).
- **Test infrastructure** (`backend/tests/conftest.py`): `mock_redis` fixture rewritten to use `AsyncMock` for every method production code awaits (`get_session_owner`, `set_session_owner`, `store_chat_message`, `ui_history_*`, etc.), eliminating the `'MagicMock' object can't be awaited` errors in chat-streaming tests.
- **Proxmox bulk-IP tool hardening** (`backend/modules_catalog/proxmox/tools.py:list_vm_ip_addresses`): defensive `isinstance` checks + JSON-parse fallback when the @tool wrapper returns a string (langchain tool-wrapping can serialize lists). Non-list / non-dict entries are skipped with a warning. `AttributeError`/`TypeError`/`KeyError` inside the per-VM loop are caught locally instead of crashing the whole bulk call.
- **4 i18n keys in 8 locales** (`frontend/i18n/{es,fr,it,ja,nl,pl,pt,zh}.json`): added idiomatic translations for `settings.sttLanguage`, `settings.sttModelSize`, `settings.sttDevice`, `settings.sttComputeType`. All 10 locales now have a consistent 435-key set.

### Changed

- **Proxmox tools return Markdown to the LLM** (`backend/modules_catalog/proxmox/tools.py`): 12 list/dict-returning @tools were refactored into thin `_X_raw()` internal functions (returning the original structured type for routes and the agent's fast-path) and `@tool _X()` wrappers (returning formatted Markdown strings to the LLM). Added `_format_vms_as_markdown`, `_format_nodes_as_markdown`, `_format_ips_as_markdown`, `_format_vm_ip_dict_as_markdown` helpers. Tool names, signatures, and descriptions are unchanged (LLM API compatibility preserved). `routes.py` now imports `_X_raw()` directly; `agent.py` fast-path uses the raw functions to keep receiving lists.
- **Core decoupled from marketplace** (`backend/agents/fast_path_tool_resolver.py`): added `try_get_module_tool(registry, module_id, tool_name)` so the orchestrator's FRITZ!Box/Tasmota fast-path no longer imports `modules_catalog.fritzbox.tools` directly. Returns `None` (graceful skip) when the module or tool is not registered.
- **Container images pinned** (`k8s/backend/deployment.yaml`, `docker-compose.yml`): `natorus87/ninko-backend:latest` → `natorus87/ninko-backend:1.3.7` (with `imagePullPolicy: IfNotPresent`); `searxng/searxng:latest` → `searxng/searxng:2024.12.13`. Eliminates supply-chain risk from `:latest` tags and gives reproducible deploys.

### Fixed

- **CRITICAL — Knowledge Graph data leak between tenants**: `tenant_id = auth_tenant_id(...)` was extracted in 18 endpoints in `routes_knowledge_graph.py` but never passed to the underlying KG methods (which didn't even accept it). Any authenticated user could read, modify, or delete any other tenant's entities. Fixed by adding the per-tenant KG refactor.
- **CRITICAL — XSS in safeguard profile picker** (`frontend/app.js:2699`): `p.id` and `p.name` from `/api/safeguard/profiles` were inserted into `innerHTML` without escaping. An admin could create a profile with `name = "</option><img src=x onerror=...>"` to inject script. Replaced with `createElement` + `textContent` + `replaceChildren` in 5 places: agent-safeguard select, safeguard picker, TTS voice select, TTS download status, and module-noDashboard placeholder.
- **CRITICAL — Teams bot crashed on every exception** (`backend/modules_catalog/teams/bot.py:403`): `except (...) as e: ... f"❌ {str(exc)[:300]}"` referenced the undefined `exc` (should be `e`), causing a `NameError` on every error path. Also fixed 2 other F821 errors (missing `import asyncio`) in the same file.
- **SQL-injection vector in `message_hub/db.py`**: `UPDATE routes SET {set_clause}` interpolated dict keys from the request body via f-string. SQL parameter binding only protects values, not column names. Fixed with `ALLOWED_ROUTE_UPDATE_FIELDS` whitelist + static `_UPDATE_ROUTE_SQL` lookup table that maps column-sets to prebuilt SQL statements, eliminating dynamic f-string SQL construction (S608).
- **Microsoft Entra `list_entra_users` crashed on every non-empty response** (`backend/modules_catalog/microsoft_entra/tools.py:159`): `total` and `count` were referenced in f-strings but never defined. Added `total = len(users)` and `shown = min(total, 15)`; rewrote the i18n branches to reference `{total}`/`{extra}`.
- **Redmine tool crashed on every call** (`backend/modules_catalog/redmine/tools.py:289`): undefined `params` argument + wrong endpoint (`issues.json` for what was actually project info). Built a proper `params` dict from function args and changed the endpoint to `projects/{project_id}.json`.
- **Microsoft Intune unparseable on Python 3.11** (`backend/modules_catalog/microsoft_intune/tools.py:274, 290`): f-strings with same-quote-character as the outer delimiter (PEP 701, Python 3.12+ only). The project's `target-version = "py311"`, so this would fail to parse on 3.11. Hoisted `_t(...)` calls for `Ja`/`Nein` into local variables.
- **PIPER binary trust** (`backend/api/routes_tts.py`): `subprocess.run([binary, "--version"])` with `binary = cfg.PIPER_BINARY` was unbounded. Added `ALLOWED_TTS_BINARIES` frozenset; non-matching binaries log a warning and the local version is reported as empty.
- **Paramiko `AutoAddPolicy` MITM** (`backend/modules_catalog/linux_server/tools.py`): SSH auto-trusted unknown host keys. Replaced with TOFU (trust-on-first-use) — `RejectPolicy` once `data/linux_server/known_hosts` exists; nested `_TofuHostKeyPolicy` subclass accepts and persists new keys on first connect.
- **61 unit tests were falsely failing** (now 0): Redis/SQLite-dependent tests (`test_workflows_integration.py`, `test_agents_integration.py`, `test_scripting_integration.py`) were missing `@pytest.mark.integration` markers. `test_telegram_bot_formatting.py` had a module-level `sys.modules` stub that leaked into every subsequent test (broke 8 base_agent_prompts tests). `test_config_security.py` used a 25-char `SESSION_SECRET` that prod correctly rejects. Async-mock mismatches in `test_chat_streaming.py` (3-tuple vs 4-tuple for `orchestrator.route`).
- **61 `raise-without-from-inside-except`** (B904): All `raise HTTPException(...)` in `except` blocks now use `from exc` to preserve the exception chain for Sentry/Logfire.
- **8 `try-except-pass`** (S110): Each replaced with `logger.warning(...)` + context message ("Thinking-Content-Event konnte nicht emittiert werden", "IMAP-IDLE readline fehlgeschlagen", "Embed-Provider-Config nicht lesbar, nutze Defaults", etc.).
- **14 `B025` duplicate-try-except** (mostly `pihole/routes.py`): removed dead `except (RuntimeError, ValueError, ...)` handlers that duplicated earlier `except ValueError` handlers in the same try block.
- **108 unused imports + 35 unused variables** (F401/F841): resolved via `ruff --fix`; the largest impact was 18 `routes_*.py` files where `tenant_id = auth_tenant_id(...)` was extracted but never used.
- **False positive F821 in `core/safeguard_profiles.py`**: string annotation `"SafeguardProfile | None"` before the lazy import. Fixed with `from __future__ import annotations` + `if TYPE_CHECKING: from core.safeguard import SafeguardProfile`.
- **7 hardcoded `/tmp` paths** (S108): replaced with `tempfile.mkdtemp(prefix="ninko-...")` or moved persistent files to `data/`. Kept the bwrap `--tmpfs /tmp` argument (bwrap creates an isolated tmpfs namespace, not a host path) with a `noqa: S108`.

## [1.3.7] – 2026-05-25

### Added

- **Telegram/K8s regression coverage** (`backend/tests/test_k8s_telegram_regressions.py`): Focused tests for Telegram/Safeguard failures, callable tool selection, FRITZ!Box/Tasmota discovery, and LLM fallback error handling.
- **FRITZ!Box/Tasmota deterministic fast path** (`backend/agents/orchestrator.py`): Explicit requests such as "Benutze FRITZ!Box, um alle Tasmota Geräte zu finden" now query the FRITZ!Box device list directly and filter Tasmota matches without relying on LLM routing.
- **Workflow restart recovery stage 1** (`backend/core/workflow_engine.py`, `backend/main.py`): Startup sweeper marks orphaned in-flight workflow runs as `interrupted` after backend restarts.

### Changed

- **Telegram reliability** (`backend/modules_catalog/telegram/bot.py`): User-facing execution errors now distinguish unreachable LLM backends and timeouts from generic processing failures.
- **Embedding provider restoration** (`backend/main.py`): Startup now restores the separate Redis-backed embedding provider (`ninko:settings:embed_provider`) instead of falling back to the active chat LLM endpoint.
- **Workflow API behavior** (`backend/api/routes_workflows.py`): Version listing includes the current workflow version plus history, and workflow runs can be persisted even when the orchestrator is not initialized.
- **Safeguard read-only prefilter** (`backend/core/safeguard.py`): German read-only discovery requests using `finden` are classified as safe when no write/destructive intent appears in the same message.
- **Agent tool metadata handling** (`backend/agents/base_agent.py`): JIT tool selection now handles both LangChain tools and plain callables without assuming `.name` / `.description`.

### Fixed

- **Telegram confirmation failures**: Confirmed Safeguard actions no longer fall through to opaque "Fehler bei der Ausführung" for common LLM connection failures.
- **Safeguard false confirmations**: Read-only German discovery/search requests are no longer forced into fail-safe confirmation solely because the classifier is unavailable.
- **ReAct fallback crash**: Plain callable tools no longer crash the ReAct fallback with `'function' object has no attribute 'name'`.
- **Embedding endpoint mismatch**: Semantic routing/cache code now uses the configured embedding endpoint after container restarts, fixing accidental `/embeddings` calls against chat-only providers.
- **Secret and auth hardening**: Secret routes now require admin access, SQLite vault decryption failures raise instead of silently returning `None`, and API token creation responses are marked `no-store`.
- **Frontend sanitization**: Module HTML sanitization removes inline event handlers and fails closed if DOMPurify is unavailable.
- **Pipeline and chat error hygiene**: Pipeline/agent execution errors avoid leaking raw exception details to end users while preserving server-side diagnostics.

## [1.3.6] – 2026-05-16

### Added

- **Kubernetes module v1.3.0** (`backend/modules_catalog/kubernetes/`): 17 neue Tools für vollständige Cluster-Inspektion — `list_nodes`, `describe_node`, `describe_pod`, `list_statefulsets`, `list_daemonsets`, `list_replicasets`, `list_jobs`, `list_cronjobs`, `list_configmaps`, `list_secrets` (metadata only), `list_persistent_volumes`, `list_storage_classes`, `list_endpoints`, `list_network_policies`, `list_hpas`, `get_top_nodes`, `get_top_pods`. Routing-Keywords erweitert um Node/Daemonset/Cronjob/HPA/Metrics-Begriffe.
- **`KeywordRouter` compat shim** (`backend/agents/orchestrator.py`): Minimaler Keyword-Router ersetzt das entfernte `core/router.py` für Legacy-Telemetrie (`classify_tier`), Force-/Fallback-Helper und Tests. Primäres Routing bleibt LLM-Native Function Calling.
- **Response formatting regression tests**: Added focused coverage for language middleware, module table rendering, explicit JSON requests, module-qualified preferred columns, and short AI-answer augmentation.

### Changed

- **Routing-Architektur vereinfacht**: 4-Tier-Routing-Modul (`core/router.py`, 408 LOC) entfernt. Primäres Routing erfolgt jetzt ausschließlich über LLM-Native Function Calling auf manifest-generierten Tool-Definitionen. Tier-Klassifikation existiert nur noch als Telemetrie über den Compat-`KeywordRouter`.
- **Kubernetes list-Tools cluster-weit per Default**: `get_all_pods`, `list_deployments`, `list_services`, `list_ingresses`, `list_pvcs`, `get_recent_events` liefern bei leerem `namespace`-Parameter Ergebnisse über alle Namespaces statt nur `default`. Behebt Agent-Antworten der Form "kann keine globale Liste abfragen".
- **README & backend/README**: 4-Tier-Routing-Beschreibung durch Function-Calling-Beschreibung ersetzt; Architektur-ASCII-Diagramm aktualisiert.
- **Kubernetes-Modul-README**: Veraltete Tool-Liste (5 Einträge mit falschen Namen) durch vollständige Tabelle aller 39 Tools ersetzt, inkl. Sicherheitshinweise zu Secrets und Server-Side-Apply.
- **Canonical English module prompts**: Migrated high-risk, catalog, template, and core module system prompts to English canonical prompts while keeping response language centralized in middleware.
- **Module marketplace versions**: Bumped affected module manifest versions and synchronized `backend/modules_catalog/catalog.json`.
- **Release metadata**: README, VERSION, Helm chart `appVersion`, chart version, and default Helm image tag updated for v1.3.6.

### Removed

- **Evidence Layer** (`backend/core/evidence/`): Komplettes Subsystem entfernt (`confidence`, `constellation_validator`, `evidence_trace`, `glossary_store`, `module_semantic_index`, `schemas`, `semantic_resolver`).
- **Prestructure Layer** (`backend/core/prestructure/`): Komplettes Subsystem entfernt (`entity_extractor`, `intent_detector`, `module_ranker`, `normalizer`, `risk_assessor`, `routing_hints`, `schemas`, `task_sketch_builder`).
- **Core Router** (`backend/core/router.py`): Ersetzt durch Function-Calling-Routing + `KeywordRouter`-Shim im Orchestrator.

### Fixed

- **Pydantic v2 import** (`backend/api/routes_settings.py`): `Literal` wird jetzt aus `typing` statt aus `pydantic` importiert (Pydantic v2 entfernt das Re-Export).
- **Structured module response rendering**: Tool results for Kubernetes, Proxmox, Docker, Linux Server, Checkmk, OPNsense, and Zabbix now render as Markdown tables for normal answers and JSON code blocks when explicitly requested.
- **Preferred table column collisions**: Preferred columns are now module-qualified so same-named tools such as `list_services` no longer reuse the wrong table schema.
- **Short AI responses**: Concise module summaries now append structured tool details when needed and avoid duplicating existing Markdown tables.
- **Zabbix agent initialization**: Fixed the Zabbix `BaseAgent` constructor usage and removed the obsolete `_register_tools` path.

## [1.3.5] – 2026-05-10

### Added

- **Network Analysis Module** (`backend/modules/network_analysis/`): Core module with `dns_lookup`, `reverse_dns`, `traceroute`, `ping_host`, `get_network_info` tools for real network diagnostics. Routing keywords: `netzwerkanalyse`, `dns lookup`, `traceroute`, `whois`, etc.
- **Kubernetes NET_RAW capability**: Pod now requests `NET_RAW` capability for `ping`/`traceroute` ICMP/raw socket access.
- **Routing keyword linter CI**: New GitHub workflow and script reject stopwords, accidental duplicate keywords, and unsafe short keywords before they degrade routing quality.
- **Routing confidence telemetry**: Chat responses now expose `routing_confidence`, the frontend warns below 70 %, and admin endpoints expose routing correction statistics.
- **Embedding/TF-IDF tie-breaker**: Ambiguous keyword matches can be ranked semantically via the configured embedding backend, with deterministic TF-IDF fallback and correction-based soft learning.
- **WebSocket session blacklist checks**: WebSocket authentication now honors revoked session tokens asynchronously.

### Changed

- **Dockerfile**: Added `iputils-ping` and `traceroute` packages for network diagnostics.
- **Router extraction**: Keyword routing logic moved into `core/router.py`, reducing `orchestrator.py` complexity and making routing decisions directly testable.
- **Routing behavior**: Removed broad substring fallback, limited compound detection to explicit sequence intent, and added conservative German token normalization for common flexions.
- **Module aliases**: Technical module names are automatically added as routing aliases with the existing name boost, removing an implicit manifest-author contract.
- **Telegram module**: Telegram now behaves as a transparent transport bridge and delegates content questions back to the main orchestrator instead of answering as a siloed bot.
- **Frontend event handling**: Large parts of the static UI migrated from inline handlers to `data-action` delegation while preserving CSP compatibility for legacy module tabs.
- **Security defaults**: Example and Compose configuration no longer provide an `admin` bootstrap password by default; deployments must set an explicit password and 32+ character `SESSION_SECRET`.
- **Release metadata**: README, VERSION, Helm chart `appVersion`, and default Helm image tag updated for v1.3.5.

### Fixed

- **CSP regression guard**: Global CSP remains compatible with existing module frontends that still use inline handlers while the UI migration continues.
- **Routing admin auth**: `/api/routing/corrections` now checks dict-based auth contexts correctly and requires an admin role.
- **Stale routing confidence**: Orchestrator routing state is reset at the start of every turn and early return paths set their tier explicitly.
- **Over-broad routing corrections**: Correction telemetry now matches the same message hash and consumes the pending auto-routing state after a manual module choice.
- **Safeguard false positives**: `netzwerkanalyse`, `traceroute`, `tracepath`, `dns lookup`, `ip-adresse`, `server-analyse`, `website-analyse` added to safe search keywords in `_fast_prefilter_short()`.
- **Routing keyword conflict**: Removed `netzwerkanalyse`, `netzwerk-analyse`, `website-analyse`, `server-analyse` from `web_search` manifest — these now route correctly to `network_analysis` module.
- **RedisRateLimiter NOSCRIPT recovery**: Added `_get_script_sha()` with NOSCRIPT exception handling and automatic script reload.
- **Archive extraction hardening**: Plugin ZIP extraction validates resolved paths and rejects symlinks before extracting members.
- **Chat history replacement hardening**: `PUT /api/chat/history/{session_id}` validates message lists and limits both message count and content length.
- **Provider error leakage**: Image generation, transcription benchmark, and dataviz routes now return generic user-facing errors while logging internal details.

## [1.3.4] – 2026-05-05

### Fixed

- **Licium Wiki initialization on Kubernetes**: Licium's API returns and accepts camelCase fields (`parentId`, `contentMarkdown`). Ninko now reads both snake_case and camelCase fields and sends both variants for compatibility, so `_meta`, `sources`, `wiki`, `queries`, `_index`, and `_log` are created under `Ninko Wiki` instead of at root level.
- **Evidence escalation for explicit module routing**: explicit candidate module names such as `licium` no longer become unresolved semantic terms.
- **User-facing EvidenceTrace noise**: normal module answers no longer append an empty `Evidence Trace` unless there are real validation details, contradictions, or escalation reasons.

## [1.3.3] – 2026-05-04

### Added

- **Evidence Layer** (`core/evidence/`): semantic term resolution, module semantic indexing, field mapping confidence, rule-based constellation validation, and auditable `EvidenceTrace` schemas.
- **Tool completion validation middleware**: blocks false completion when required module tool calls did not actually run, with a deterministic guard for Licium existing-note imports.
- **Licium existing-note ingest tool**: `ingest_existing_licium_notes()` initializes the Ninko Wiki structure idempotently, imports existing Licium notes into `sources/`, updates the index, and writes an operations log entry.
- **Focused Evidence and ToolCompletion tests** covering semantic resolver behavior, contradictory evidence handling, trace readiness, and missing-tool blocking.

### Changed

- Orchestrator integrates semantic evidence resolution after TaskSketch and passes confidence/escalation details into planner and pipeline paths.
- Prestructure routing now treats simple answers and investigations as read-only, routes explicit workflow intent more conservatively, and marks ambiguous investigations with missing targets.
- Image generation and Codelab script execution imports are lazy to avoid module side effects during orchestrator import.

### Fixed

- Licium no longer stops after listing notes or checking wiki metadata when the user asks to ingest existing notes into the Ninko Wiki.
- Semantic glossary matching is stricter to prevent unrelated common words from being mapped to evidence fields.
- Tool execution detection now handles runtimes where `ToolMessage` has only `tool_call_id` and no `name`.

### Added

- **Typed Pipeline Engine** (`core/pipeline_engine.py`): Pydantic-validated `PipelineStep` / `StepResult` / `PipelineResult` schemas replace the ad-hoc string-stack in `run_pipeline()`. Per-step retry with exponential backoff (`RetryPolicy`), `asyncio.gather(return_exceptions=True)` for safe parallel groups, Redis checkpoints after each group, and a structured `PipelineEvent` system (9 event types: `routing_started` → `pipeline_completed`).
- **Deterministic Pipeline Planning**: `_plan_and_execute_pipeline()` now builds a base plan from `TaskSketch.scope.candidate_modules_ranked` without any LLM call. The LLM planner runs as an optional refinement pass with a 10 s timeout; on failure the deterministic plan is used — no ReAct fallback.
- **Persistent Session State** (`core/session_state.py`): `SessionState` tracks routing tier, detected modules, pipeline plan, per-step results, errors, and pending confirmations in Redis (`ninko:session_state:<id>`, 24 h TTL).
- **ToolSpec Registry**: `ToolSpec` frozen dataclass added to `core/tool_registry.py` with `input_schema`, `output_schema`, `requires_confirmation`, `timeout_s`, and `max_retries`. `get_or_infer_tool_spec()` dynamically infers a spec from the tool name using existing tier heuristics.
- **Pipeline Events** (`core/pipeline_events.py`): Global async listener registry (`on_pipeline_event` / `emit_pipeline_event`) for observability hooks and future UI progress streaming.
- **15 unit tests** (`tests/test_pipeline_engine.py`) covering single-step success, multi-step sequential execution, notification pipelines, per-step retry-on-failure, invalid JSON rejection, unknown module rejection, confirmation flow (skip vs. auto_confirm), utility module filtering, and the no-ReAct-fallback guarantee.

### Changed

- `run_pipeline()` now delegates entirely to `PipelineEngine` — the old ~200-line string-accumulation loop with `_err_prefixes` string-prefix error detection is removed.
- Multi-step failure now yields `PipelineResult.status == PARTIAL` (structured, typed) instead of unpredictable ReAct loop re-entry.
- `validate_steps_from_dicts()` is the single validation entry point used by both the Orchestrator and `run_pipeline()`.

## [1.3.2] – 2026-04-25

### Added

- **Context-aware welcome messages** across all shipped frontend languages with generic, time-of-day, and weekday-specific variants for the restored dashboard experience.
- **Qdrant knowledge management expansion** with bulk-add support, filter-based delete preview/confirm flow, and stronger route/schema coverage for destructive operations.
- **OPNsense tool classification and input validation**: explicit write/admin tool tiers plus hardened validation for ports, networks, virtual IPs, and interface operations.

### Changed

- **Dashboard restored to the production snapshot users expected**: the blue/violet glass dashboard from the known-good image is now the active frontend baseline again, including the matching login and chat surfaces.
- **Release image/tag alignment**: Kubernetes and Helm manifests now point to the versioned release image `natorus87/ninko-backend:v1.3.2` instead of ad-hoc tags.
- **Routing keyword tuning** for Codelab, Scripting, Email, Fritzbox, IONOS, Kubernetes, Pi-hole, and Proxmox to reduce false-positive module routing.
- **README and app metadata** updated to reflect the current release version.

### Fixed

- **Dashboard initialization regression**: fixed `this._dashboardGreeting is not a function`, which left the chat shell visible but prevented full dashboard initialization.
- **Proxmox dashboard and agent behavior**: improved status-first agent instructions, clearer VM/node cards, accessible connection selection, and more robust module settings toggles.
- **Marketplace/plugin runtime compatibility**: restored backward-compatible `register_tool()` handling for agents that append tools after instantiation.
- **Provider error handling**: better fallback text when the active LLM provider has no model loaded, plus lower-overhead outbound sanitizer handling.
- **HPE iLO and Qdrant agent wiring**: corrected agent initialization/tool registration issues and tightened destructive knowledge-delete safeguards.

## [1.3.1] – 2026-04-19

### Documentation

- **README.md Overhaul**: Complete update for v1.3.0+ with accurate module counts, version badges, and architecture diagram
- **Environment Variables**: Expanded table with 13 essential vars including security-critical `SESSION_SECRET`, `BOOTSTRAP_ADMIN_PASSWORD` 
- **5-Level Permission Tiers**: Corrected tier names (READONLY → COMMUNICATE → WRITE_DATA → WRITE_SYSTEM → ADMIN)
- **Module Registry**: Updated core modules (7) and catalog modules (40) counts

### Fixed

- **GitHub Releases**: Cleaned up 23 pre-stable releases, keeping only v1.x releases
- **Docker Hub**: Created proper v1.3.0 tag for production deployments

## [1.2.0] – 2026-04-08

### Added

- **Claude Code Inspired Improvements** (Phase 1-3 complete):
  - **Multi-Agent Parallelisierung**: Pipeline steps can now run in parallel with `depends_on` support. New `run_parallel_pipeline` tool for fan-out/fan-in execution.
  - **Safeguard Improvements**: Confidence scoring (0.0-1.0) in prefilter, latency tracking with `latency_ms` and `path_used` fields, new `/api/safeguard/metrics` endpoint.
  - **Skill-Marketplace**: Remote skill repositories with `catalog.json` support. 13 built-in skills available. Frontend marketplace panel with Installiert/Marketplace/Repos tabs.
- **Redmine User Administration**: 13 new administrative tools for complete user and group management:
  - User CRUD: create, update, delete, lock/unlock, password reset
  - Group management: create, delete, add/remove members
  - User details with groups and memberships
- **Code Review Documentation**: Comprehensive TODO.md update with status tracking (4 FIXED, 2 PARTIALLY_FIXED, 13 STILL_EXISTS, 1 NEW).

### Changed

- **Redmine module version** bumped to `1.1.0` for new admin tools.
- **PLAN.md** created with detailed implementation roadmap for all three phases.

---

## [1.1.0] – 2026-04-05

### Added

- **Module Update Detection**: New `/api/plugins/check-updates` endpoint fetches the latest version of each installed plugin from GitHub. The modules settings page now displays an "Update" button when a newer version is available, showing the version jump (e.g., `v1.0.0 → v1.2.0`).
- **Plugin Reinstall Endpoint**: `POST /api/plugins/reinstall/{name}` allows updating plugins directly from their original repository without manual reinstall.
- **Telegram Inline Keyboard Buttons**: Safeguard confirmation requests now use Telegram inline keyboard buttons instead of text prompts. Users can tap "✅ Yes" / "❌ No" instead of typing "ja"/"nein". Fully multilingual (10 languages supported).
- **Kubernetes Patch Tools**: Added new tools to the K8s module:
  - `create_deployment` – Full Deployment creation with image, replicas, ports, env vars, resources, labels
  - `patch_deployment` – Patch deployments (image, replicas, env vars, resources)
  - `create_configmap` / `patch_configmap` – ConfigMap management
- **MCP Server Multilingual**: All error messages, validation strings, and tool outputs in the MCP Server module are now multilingual (de, en, fr, es, it, nl, pl, pt, ja, zh).
- **Task Registry**: New `core/task_registry.py` for background task management in agents.
- **Tool Permissions**: New `core/tool_permissions.py` with CLI command validation and permission system.
- **MCP Registry**: New `core/mcp_registry.py` for MCP server connection and tool/resource management.

### Changed

- **Kubernetes module version** bumped to `1.2.0` for new patch tools.

### Fixed

- **Telegram callback query handling**: Added `callback_query` to allowed_updates in polling loop to handle button clicks.
- **Multilingual button text**: Telegram confirmation buttons now show correctly translated labels in all 10 supported languages.

## [1.0.1] – 2026-04-05

### Fixed

- **Rate limiter blocking module frontend files on page load**: `loadModules()` fires 2 requests per installed module (tab.html + tab.js) in rapid succession. With many catalog modules installed, this exceeded the burst limit of 30 and returned HTTP 429 for all subsequent modules, causing "Modul X hat kein Dashboard." for most plugins. Fix: `/api/modules/*/frontend/*` paths are now exempt from the in-memory rate limiter in `main.py` — these are static assets, not API endpoints, and the burst limit is not meaningful here.

- **On-the-fly `_pluginTabs` registration for legacy plugin installs**: Old plugin installations (pre-v1.0.0) in `backend/plugins/` may not have the `Ninko._pluginTabs['id'] = TabObject` line in their `tab.js`. `routes_modules.py` now auto-patches the served JS on-the-fly: detects the exported tab object via regex (`_detect_tab_object()`), then appends the registration snippet if missing. No reinstall required.

### Changed

- **Module versions bumped** after `tab.js` frontend changes: checkmk, discord → `1.1.0`; docker, email, fritzbox, glpi, homeassistant, ionos, kubernetes, linux_server, opnsense, pihole, proxmox, qdrant, tasmota, teams, telegram, wordpress → `1.1.1`.

## [1.0.0] – 2026-04-04

### Fixed

- **Plugin dashboard registration**: All 38 catalog modules now register themselves in `Ninko._pluginTabs` at the end of their `tab.js`. Previously, modules loaded as plugins from `backend/plugins/` (installed via Marketplace from GitHub) could not be initialized by `switchModuleTab()` because `getTabObject()` relied on a hardcoded map with global variable name checks. Modules using `const X = {}` (proxmox, wordpress, checkmk, docker, glpi, kubernetes, linux_server, opnsense, pihole, tasmota) had their global name inaccessible in some environments. IIFE-based modules (telegram, teams, qdrant, fritzbox, discord) did not register at all.
  - Added `Ninko._pluginTabs['id'] = TabObject` to all 19 affected modules.
  - Ionos module had no tab object at all — wrapped procedural auto-init in a minimal `IonosTab` with `init()`.
  - Email module replaced broken `setTimeout` auto-init with proper `_pluginTabs` registration.

### Changed

- **Sidebar cleanup**: Removed redundant logout button (top-right arrow icon) and "Einstellungen" nav item from the bottom sidebar nav — both are fully covered by the bottom user account menu dropdown.

## [0.9.9] – 2026-04-04

### Fixed

- **Kubernetes migration stability**:
  - Migrated runtime from namespace `kumio` to `ninko` with PVC data copy and secret carry-over.
  - Kept ingress host continuity (`kumio.conbro.local`) while enabling `ninko.conbro.local`.
  - Unified Traefik CRD usage to `traefik.containo.us/v1alpha1` for cluster compatibility.

- **Auth/session post-login lockout**:
  - Fixed first-login password change flow where sessions could remain in `password_change_required=true`.
  - `POST /api/auth/change-password` now re-issues a fresh session cookie immediately.
  - API middleware now explicitly allows `POST /api/auth/change-password` without API key fallback errors.

- **Connection storage compatibility (multi-tenant transition)**:
  - Added backward-compatible fallback from legacy `ninko:connections:<module>` keys to tenant-scoped `ninko:connections:default:<module>`.
  - Added automatic migration path to prevent missing default connections after upgrades/migrations.

- **SafeGuard false positive**:
  - Removed Dutch keyword stem `wissen` from destructive prefilter terms to avoid German false positives in read-only queries.

- **Image generation runtime robustness**:
  - Fixed write permission failures when storing generated images.
  - Image output directory now uses a writable fallback chain (`$NINKO_IMAGES_DIR` → `/app/data/images` → `data/images` → `/tmp/ninko-images`).
  - Re-enabled `image_gen` in Kubernetes deployment defaults.

### Changed

- **Security hardening in deployment manifests**:
  - Added explicit auth/session env config in k8s + Helm (`API_AUTH_ENABLED`, `ADMIN_USERNAME`, `SESSION_COOKIE_SECURE`).
  - Added required secret fields for `SESSION_SECRET` and `BOOTSTRAP_ADMIN_PASSWORD`.

## [0.9.8] – 2026-04-04

### Added

- **GitHub-Modul** (Catalog):
  - GitHub Actions: trigger, cancel, re-run workflows
  - Pull Requests: create, merge, review
  - Issues: list, create
  - Repository: repos, branches, commits, tags, releases
  - Variables, secrets, code search
  - 30 Tools total für vollständige GitHub-Steuerung

### Changed

- **i18n**: GitHub Übersetzungen für alle 10 Sprachen ergänzt
- **Tool-Labels**: GitHub Tool-Labels in base_agent.py

---

## [0.9.7] – 2026-04-04

### Added

- **GitLab-Modul** (Catalog):
  - Pipeline-Management: trigger, cancel, retry, schedules
  - MR-Management: create, accept, list, details
  - Repository: projects, branches, commits, tags, releases
  - CI/CD Variables: create, list, delete
  - 24 Tools total für vollständige CI/CD-Steuerung

### Changed

- **i18n**: GitLab Übersetzungen für alle 10 Sprachen ergänzt
- **Tool-Labels**: GitLab Tool-Labels in base_agent.py

---

## [0.9.6] – 2026-04-04

### Added

- **Zabbix-Modul** (Catalog):
  - `get_zabbix_status` — Server-Status und Version
  - `list_zabbix_hosts` — Host-Liste
  - `get_zabbix_host` — Host-Details
  - `list_zabbix_items` — Monitoring-Items
  - `list_zabbix_triggers` — Trigger-Liste
  - `get_zabbix_problems` — Aktuelle Probleme
  - `list_zabbix_graphs` — Graphen-Liste
  - `list_zabbix_actions` — Actions/Alerts
  - `get_zabbix_history` — Historische Daten
  - `get_zabbix_host_group` — Host-Gruppen
  - `list_zabbix_templates` — Templates
  - `create_zabbix_host` — Host erstellen
  - `delete_zabbix_host` — Host löschen

- **NetBox-Modul** (Catalog):
  - `get_netbox_status` — Server-Status und Version
  - `list_netbox_sites` — Site-Liste
  - `get_netbox_site` — Site-Details
  - `list_netbox_devices` — Device-Liste
  - `get_netbox_device` — Device-Details
  - `list_netbox_racks` — Rack-Liste
  - `get_netbox_rack` — Rack-Details
  - `list_netbox_vlans` — VLAN-Liste
  - `list_netbox_prefixes` — Prefix-Liste
  - `list_netbox_ip_addresses` — IP-Adressen
  - `list_netbox_circuits` — Circuits
  - `list_netbox_cables` — Kabel
  - `list_netbox_clusters` — Cluster
  - `get_netbox_device_interfaces` — Device-Interfaces

### Changed

- **i18n**: Zabbix und NetBox Übersetzungen für alle 10 Sprachen ergänzt
- **Tool-Labels**: Zabbix und NetBox Tool-Labels in base_agent.py

---

## [0.9.5] – 2026-04-04

### Added

- **Discord-Modul** (Catalog):
  - `get_guild_info` — Server-Informationen abrufen
  - `get_channels` — Kanal-Liste (Text/Voice/Category)
  - `get_members` — Mitglieder-Liste
  - `get_messages` — Nachrichten-History
  - `create_channel` — Text/Voice-Kanal erstellen
  - `delete_channel` — Kanal löschen
  - `send_message` — Nachricht senden
  - `search_messages` — Nachrichten durchsuchen

- **Operation Journal Erweiterungen**:
  - `GET /api/operations/transactions` — Transaktions-Liste
  - `GET /api/operations/transactions/{id}` — Transaktions-Details
  - Tenant-scoped Session-Management

### Changed

- **RBAC Multi-Tenancy**:
  - Tenant-Scoping für Chat-History und Workflow-Storage
  - Session-Token erweitert um `tenant_id`

---

## [0.9.4] – 2026-04-03

### Added

- **Neue Catalog-Module**:
  - `cisco` — Cisco Network Devices (Switches, Router, Nexus)
  - `mikrotik` — MikroTik RouterOS
  - `netgear` — Netgear Network Devices
  - `ubiquiti` — Ubiquiti UniFi
  - `nextcloud` — Files, Shares, Users
  - `openproject` — Projects, Tasks, Time Tracking

- **Redmine AlphaNodes-Erweiterung**:
  - HRM-Endpunkte (Attendances, Capacity, Holidays)
  - Reporting-Endpunkte (Budgets, Time Logs)
  - Neue modul-spezifische Tools + API-Routen für read/write Kommunikation

### Fixed

- **Exception handling hardening (broad except reduction)**:
  - Breite `except Exception`-Blöcke in Core/Agent-Pfaden gezielt reduziert
  - Präzisere Exception-Typen und sauberere Boundary-Fehlerbehandlung
- **Module stability fixes**:
  - Syntaxfehler in `modules_catalog/pihole/tools.py` behoben
  - Indentation-/Flow-Fehler in `modules_catalog/mikrotik/tools.py` behoben

### Changed

- **i18n rollout erweitert**:
  - Frontend-Übersetzungen für alle vorhandenen Module ergänzt
  - Mehrsprachige Texte für alle unterstützten 10 Sprachen konsolidiert

---

## [0.9.3] – 2026-04-03

### Added

- **Theme management system (end-to-end)**:
  - Backend:
    - `backend/schemas/theme.py` with `ThemeDefinition`, `ThemeSummary`, `ThemeListResponse`, `ThemeRepo`.
    - `backend/core/theme_manager.py` for built-in/custom theme loading, token sanitization, active-theme persistence (`ninko:settings:theme_active`).
    - `backend/api/routes_themes.py` with CRUD for custom themes, active theme switching, theme repository management, and install-from-repo support.
    - New built-in themes: `backend/themes/default/theme.json`, `backend/themes/arctic/theme.json`.
  - Frontend:
    - New Settings sub-tab **Themes** with preset activation, custom theme editor (dark/light token JSON), repository integration, and install flow.
    - Runtime CSS token application on startup and on light/dark mode toggle.

### Fixed

- **CodeLab chat integration bug**: "Verbessern/Erklären/Review" buttons in the CodeLab tab now correctly send prompts via `Ninko.sendMessage()` (previously referenced non-existent `app.sendMessage()`).
- **Web Search XSS hardening**: escaped engine names/reasons and error messages before rendering in `innerHTML`.
- **Web Search networking robustness**: removed hardcoded `Host: localhost` header from SearXNG tool requests.
- **Error leak reduction**:
  - `codelab` routes now return generic 500 error messages instead of raw internal exception strings.
  - `web_search` routes/tools no longer expose raw exception text to end users.

### Changed

- **CodeLab execution hardening**:
  - Added input/output size limits.
  - Switched Python execution to isolated mode (`python3 -I -B -u`).
  - Added constrained subprocess environment (`PATH`, `HOME`, `TMPDIR`, locale vars only).
  - Enforced POSIX resource limits (CPU, memory, file size, open files, process count, core dumps).
  - Improved timeout cleanup by terminating full process groups on POSIX.

---

## [0.9.2] – 2026-04-02

### Added

- **LiteLLM Proxy backend** — new `litellm` backend type for self-hosted [LiteLLM](https://github.com/BerriAI/litellm) proxy instances:
  - Unlike `lmstudio` (no-key local), LiteLLM always requires an API key — even if it is just a placeholder like `sk-1234`.
  - Uses `_NormalizingChatOpenAI` (standard OpenAI tool handling, no LM Studio Jinja workarounds needed).
  - Config keys: `LITELLM_BASE_URL` (default `http://litellm:4000/v1`), `LITELLM_MODEL`, `LITELLM_API_KEY`.
  - Provider form in Settings → LLM shows the API key field when `litellm` backend is selected (same as `openai_compatible`).
  - Provider connection test sends `Authorization: Bearer <key>` header for `litellm` (same as `openai_compatible`).
  - `get_safeguard_openai_client()` and `get_model_context_window()` both handle the `litellm` backend case.
  - Provider card in the UI displays `LiteLLM` as the backend label.

---

## [0.9.1] – 2026-04-02

### Fixed

- **Safeguard SSL bypass** — `get_safeguard_openai_client()` in `llm_factory.py` created an `AsyncOpenAI` client without a custom httpx instance, so the safeguard classifier always used Python's default SSL verification — ignoring the provider's `verify_ssl` setting. On every chat message, the safeguard would fail with `CERTIFICATE_VERIFY_FAILED` when the LLM backend has a self-signed certificate. Fixed by passing `http_client=httpx.AsyncClient(verify=settings.LLM_VERIFY_SSL)` to the `AsyncOpenAI` constructor.

- **Provider test URL corruption (`rstrip` bug)** — `base_url.rstrip("/v1")` stripped individual characters (`/`, `v`, `1`) instead of the substring `/v1`. This corrupted port numbers ending in `1` (e.g. `:8001` → `:800`). Replaced with an explicit `endswith("/v1")` check + slice, correctly normalizing the base URL before appending `/v1/models`.

- **`AttributeError: cache_clear` on provider save with `verify_ssl=False`** — `_apply_default_provider()` called `.cache_clear()` on `get_settings`, which uses a plain module-level singleton, not `@lru_cache`. Caused a 500 error whenever a provider with `verify_ssl=False` was saved or set as default. Removed the invalid call; `core.config._settings = None` in `_reconfigure_llm()` is the correct invalidation pattern.

### Changed

- Provider connection test (`POST /api/settings/llm/providers/{id}/test`) now logs `verify_ssl_raw` and `verify_ssl_bool` at `INFO` level for easier SSL diagnosis.

---

## [0.9.0] – 2026-04-02

### Added

- **Workflow Builder** — Ninko now has expert knowledge to build perfect workflows:
  - **`backend/skills/workflow-builder/SKILL.md`** — Auto-injected skill that gives Ninko a comprehensive 10-step guide for building workflows. Covers all node types, condition syntax, variable interpolation, prompt design, error handling, tool selection, and anti-patterns. Triggers on any workflow-related request (Workflow erstellen, Automatisierung, Workflow mit Bedingung, Workflow mit Loop, etc.).
  - **`create_dag_workflow` tool** (`backend/agents/core_tools.py`) — New LangChain tool that lets Ninko build arbitrary DAG workflows with branches, conditions, and loops via chat. Accepts `name`, `description`, `nodes` (with short user-friendly IDs), and `edges`. Auto-calculates Y positions, maps short IDs to UUIDs, saves to Redis, and returns a confirmation with node/edge counts. Registered in `_TOOL_READONLY` in `safeguard.py`.
  - **Orchestrator SYSTEM_PROMPT update** — now explicitly routes to `create_dag_workflow` for complex workflows (conditions/loops/branching) and to `create_linear_workflow` for simple linear flows.

- **Loop-Node fully implemented** (`backend/core/workflow_engine.py`):
  - **`foreach` mode** — iterates over a list variable, executes a prompt template per item with `{loop_item}` and `{loop_index}` substitution, collects results in `{loop_results}`. Supports lists, JSON strings, and comma-separated values.
  - **`while` mode** — repeats until a condition expression evaluates to `False`, with configurable `max_iterations` (capped at 50).

- **Extended Condition expressions** (`backend/core/workflow_engine.py`):
  - New `_evaluate_condition()` method with 9 supported expression types: `output.contains("x")`, `output.startswith("x")`, `output.endswith("x")`, `output.matches("regex")`, `variable.NAME == "value"`, `variable.NAME != "value"`, `variable.NAME > N`, `variable.NAME < N`, `len(output) > N`.

- **Frontend Loop Inspector** (`frontend/app.js`):
  - Loop nodes now show a `mode` dropdown (foreach / while) and a `prompt` textarea in the Workflow Inspector panel instead of a plain text input.

- **Context Window Ring Indicator** (`frontend/`) — live context usage visualization in the chat input bar:
  - SVG donut-ring next to the SafeGuard shield, fills from 0% to 100% as conversation history grows toward the compaction threshold.
  - Color-coded: green (0–40%) → yellow (40–65%) → orange (65–85%) → red (85–100%).
  - Percentage label next to the ring (same color); shows `!` when compaction will fire on the next message.
  - Hover tooltip: `Kontext: X / Y Tokens · Komprimierung in ~Z Tokens`.
  - Brief flash animation when a compaction event occurs.
  - Initializes at page load by calling `GET /api/settings/llm/context-window` — ring appears immediately, not only after the first message.

- **Manual Context-Window override per LLM Provider**:
  - New `context_window` field (integer, `0 = auto`) in the LLM provider form (Settings → LLM).
  - When set to a value > 0, the `llm_factory` cache is populated directly without an API call to `/v1/models` — solves incorrect values from providers that omit `context_length` in their model metadata (e.g. LM Studio with certain models).
  - New `GET /api/settings/llm/context-window` endpoint returns the effective value (manual override > cached API value > fallback 32768) with a `source` field (`"manual"` or `"api"`).
  - Schema fields `context_window: int = 0` added to `LLMProvider` and `LLMProviderCreate` in `backend/schemas/settings.py`.
  - Provider card in the UI shows the configured context window size (e.g. `32k ctx`) next to the model name.
  - `invalidate_context_window_cache(override: int = 0)` — extended signature; passing `override > 0` writes the value directly into the cache.
  - i18n keys `settings.providerContextWindow`, `settings.providerContextWindowPlaceholder`, `settings.providerContextWindowHint` added for all 10 supported languages (DE, EN, FR, ES, IT, NL, PT, PL, JA, ZH).

### Fixed

- **SearXNG pod crash** — `enableServiceLinks: false` added to the SearXNG deployment spec in all three manifest locations (`k8s/searxng/deployment.yaml`, `k8s-conbro/searxng/deployment.yaml`, `charts/ninko/templates/searxng/deployment.yaml`). Prevents Kubernetes from injecting hundreds of `SERVICE_*` env vars that caused "arg list too long" pod crashes.
- **`k8s-conbro/searxng/deployment.yaml` namespace** — corrected `namespace: ninko` → `namespace: kumio` (cluster still uses `kumio` namespace pending migration).
- **Context Window Ring alignment** — SafeGuard icon and context-ring indicator are now wrapped in a shared `.chat-bottom-left` flex-container, ensuring both elements sit on exactly the same baseline regardless of margin/padding offsets.

### Changed

- `frontend/style.css` — new `.chat-bottom-left` wrapper replaces individual `position: absolute` on `.btn-safeguard` and `.ctx-indicator`. Textarea `padding-left` adjusted to `7rem` to accommodate both icons without text overlap.
- `backend/core/workflow_engine.py` — loop handler replaced (was a non-functional stub); condition evaluation replaced inline string match with the new 9-pattern `_evaluate_condition()` + `_compare()` helper.

---

## [0.8.0] – 2026-04-01

### Added

- **Agent Builder** — complete overhaul of the dynamic agent creation system:
  - **`backend/skills/agent-builder/SKILL.md`** — Ninko now has built-in expertise for building high-quality agents. The skill auto-triggers when agent creation is requested and guides Ninko through a 5-question interview (purpose, trigger, modules, output, criticality), provides system-prompt quality standards, 6 category patterns (IT-Ops, Monitoring, Security, Helpdesk, CI/CD, Home Automation), tool-selection logic, anti-patterns table, and a pre-creation quality checklist.
  - **`backend/core/agent_templates.py`** — 6 built-in agent templates: `it_ops` (IT-Operations Agent), `k8s_specialist` (Kubernetes Specialist), `security_scanner` (Security Scanner), `monitor_reporter` (Monitoring & Reporting), `helpdesk` (Helpdesk Assistant), `home_automation` (Smart Home Agent). Each template includes icon, category, description, tags, suggested modules, and a production-ready system prompt.
  - **`GET /api/agents/templates`** — returns the full template catalog for the frontend gallery.
  - **`POST /api/agents/generate`** — LLM-powered agent spec generation: takes a free-text `use_case` description, queries the active LLM, and returns a structured `{name, description, system_prompt, suggested_modules}` JSON. Used by the frontend "✨ Generieren" button.
  - **`update_custom_agent` tool** — new LangChain tool in `core_tools.py` that allows Ninko to update existing dynamic agents (system_prompt, description) without deleting and recreating them. Registered in `_TOOL_READONLY` so SafeGuard does not block it.
  - **`DynamicAgentPool.update_agent()`** — new async method in `agent_pool.py` for in-place agent updates: patches Redis, re-instantiates the live agent, and regenerates the Soul MD when name/description change.
  - **`DynamicAgentPool.list_agents()`** — convenience method returning all agent metadata as a list.
  - **Custom Agent routing via `force_module`** — `orchestrator.route()` now falls back to `DynamicAgentPool.get_agent_by_id()` when `force_module` does not match any registered module. Enables direct routing to custom agents from the chat toolbar.
  - **Improved `create_custom_agent` docstring** — the tool's docstring now includes explicit quality requirements that the orchestrator LLM reads during reasoning, ensuring every generated system prompt contains Aufgaben / Arbeitsweise / Kritische Aktionen / Eskalation sections.
  - **`update_custom_agent` in Orchestrator `SYSTEM_PROMPT`** — the orchestrator now knows it can improve existing agents without recreating them.

- **Frontend Agent Builder UI** (complete redesign of the Agents tab):
  - **Tab header renamed** to "Agent Builder" with new "⚡ Vorlagen" button alongside the existing "+ Neuer Agent" button.
  - **Template Gallery panel** (`agenten-templates`) — card grid showing all 6 built-in templates with icon, label, description, and tag chips. Clicking a template opens the editor pre-filled with name, description, system prompt, and pre-checked suggested modules. Keyboard accessible (Enter/Space).
  - **KI-Assistent section** in the agent editor — a highlighted textarea at the top of the editor form where the user can describe a use case in plain language. The "✨ Generieren" button calls `/api/agents/generate` and auto-fills name, description, system prompt, and module checkboxes. The section has a distinct gradient background to visually separate it from the manual fields.
  - **"⚡ Vorlage" button** in the editor header — quickly jumps to the template gallery without leaving the editor context.
  - **Agent type badges** in the agent list — `✨ KI` (blue, for `dynamic: true` agents) and `Manuell` (grey) badges next to each agent name.
  - **Improved empty state** — shows instructions for both the template gallery and the manual editor.
  - **`_showOnlyPanel(panelId)`** — new centralized helper that replaces all scattered `classList.add/remove('hidden')` calls across `openSkillsPanel`, `closeSkillsPanel`, `openAgentEditor`, `closeAgentEditor`, `openSkillEditorFromAgent`, `_showSkillEditorPanel`, `closeSkillEditor`. All panel transitions now go through a single function.
  - **`_customAgentsCache`** — updated on every `loadAgents()` call; feeds the module picker with custom agents.
  - **Module picker shows custom agents** — under a "Meine Agenten" section separator, all enabled custom agents appear in the chat toolbar dropdown with a 🤖 prefix. Selecting one sets `force_module = agent_id`, which the backend now resolves via `DynamicAgentPool`.

### Changed

- `orchestrator.py` SYSTEM_PROMPT — added Agent Builder guidance: clarifies when to use `create_custom_agent` vs `update_custom_agent`, requires structured system prompts with four sections.
- `safeguard.py` `_TOOL_READONLY` — added `update_custom_agent` so SafeGuard does not block agent update operations.
- `style.css` — new CSS classes: `.agent-type-badge`, `.agent-type-dynamic`, `.agent-type-manual`, `.agent-builder-ai-section`, `.template-card`, `.template-card-header`, `.template-card-icon`, `.template-card-name`, `.template-card-desc`, `.template-card-tags`, `.template-tag`. All transitions enumerate only paint-safe properties (no `transition: all`). Touch targets for template cards meet the 44px guideline via padding.

---

## [0.7.2] – 2026-03-29

### Added

- **SafeGuard Profile System** — replaces the binary on/off toggle with a full profile-based configuration engine:
  - **5 built-in profiles**: `strict` (user + LLM + injection detection), `moderate` (default, user + LLM), `user_only` (user messages only), `llm_only` (tool calls only), `disabled` (no checks)
  - **`SafeguardProfile` dataclass** — configurable fields: `check_user_messages`, `check_tool_calls`, `confirm_categories`, `detect_prompt_injection`, `fail_open`
  - **`SafeguardProfileStore`** (`backend/core/safeguard_profiles.py`) — Redis-backed CRUD for custom profiles; built-ins seeded on every startup (idempotent); legacy `"true"`/`"false"` values in `ninko:settings:safeguard` auto-migrated to `"moderate"`/`"disabled"` on first boot
  - **Profile resolution priority** (first match wins): per-chat session (TTL 24h) → per-agent override → global profile → fallback `moderate`
  - **`ActionCategory.PROMPT_INJECTION`** — new category that detects attempts to override system prompts or jailbreak the LLM. Detected by a fast keyword prefilter (`_INJECTION_PATTERNS`) and optionally by the LLM classifier when `detect_prompt_injection=True` on the active profile
  - **`fail_open` mode** — when `True`, requests pass through if the LLM classifier is unreachable; when `False` (default), the fail-safe blocks as before
  - **New REST API** under `/api/safeguard/`:
    - `GET/POST /api/safeguard/active` — read/set global active profile
    - `GET/POST/DELETE /api/safeguard/chats/{session_id}/profile` — per-chat profile override (24h TTL)
    - `GET/POST/DELETE /api/safeguard/agents/{agent_id}/profile` — per-agent profile override
    - `GET/POST/PUT/DELETE /api/safeguard/profiles[/{id}]` — full CRUD for custom profiles (builtin profiles protected)
  - **Settings → SafeGuard tab** — new panel in the settings sidebar with: global profile selector with detail badges, custom profile list (create/edit/delete), built-in profile reference
  - **Chat toolbar profile picker** — shield button now opens a popover with all profiles; clicking a profile sets it as the active global profile for the session
  - **Agent editor profile select** — replaced the safeguard toggle checkbox with a `<select>` dropdown; "Use global profile" resets to global, any other selection sets a per-agent override via `DELETE/POST /api/safeguard/agents/{id}/profile`
  - **`confirm_categories` filter** — the profile's `confirm_categories` list now controls which `ActionCategory` values require confirmation. Example: `["DESTRUCTIVE"]` lets `STATE_CHANGING` actions through without a prompt
  - **`SafeguardResult.profile_id`** field — the resolved profile ID is included in every result and propagated to the frontend via `to_dict()`

### Changed

- `SafeguardMiddleware.__init__()` — added `profile_store: SafeguardProfileStore | None` parameter; `enabled` bool kept for backward compatibility (maps to `moderate`/`disabled` profile)
- `SafeguardMiddleware.check()` — now accepts `session_id` optional parameter for per-chat profile resolution; `check_tool_call()` accepts both `agent_id` and `session_id`
- `SafeguardMiddleware.enable()` / `disable()` — now switch the active profile to `moderate` / `disabled` instead of flipping a boolean
- `routes_chat.py` — passes `session_id=body.session_id` to `safeguard.check()`
- `base_agent.py` `_sg_loop` — passes `agent_id=self.name, session_id=session_id` to `check_tool_call()`
- `agent_config_store.py` — added `get_profile()`, `set_profile()`, `clear_profile()` convenience methods alongside existing `get_safeguard()`/`set_safeguard()`
- `routes_safeguard.py` — existing toggle endpoints are now thin wrappers that set profile to `moderate`/`disabled`; `GET /api/safeguard/status` now also returns `profile_id`
- `safeguard.py` `_parse()` — enforces `violation=1` for `PROMPT_INJECTION` category (same as `DESTRUCTIVE` and `STATE_CHANGING`)
- Frontend `style.css` — added `.sg-prompt-injection` / `.sg-prompt_injection` badge style (purple), `.sg-cat-badge` system for category pills, safeguard picker popover styles, profile card styles, `.btn-xs` / `.btn-danger` utilities
- `i18n/*.json` (de + en) — 30+ new `safeguard.*` keys for profile names, scope labels, editor fields, confirmation messages

### Fixed

- Safeguard injection pre-filter: `sg-state_changing` CSS class now also covered by `sg-state-changing` alias to match the new kebab-case convention used in the dynamic badge renderer

---

## [0.7.0] – 2026-03-29

### Added

- **Tier-4 re-introduced and hardened** — the multi-module pipeline planner is back, now with robust false-positive protection:
  - **`_get_module_scores(text)`** extracted as a standalone method, reused by both `_detect_module_fast()` and `_has_multistep_indicators()`
  - **`_has_multistep_indicators(message, current_scores)`** — new method detecting explicit sequential multi-module intent via `_MULTISTEP_PATTERNS` (14 patterns: `und dann`, `danach`, `anschließend`, `as nächstes`, `zuerst…dann`, `then`, `followed by`, etc.). **Single-module guard**: returns `False` if fewer than 2 modules have score ≥ 2 in the *current* message — "logs anzeigen und dann neustart" stays Tier 2
  - **`_plan_and_execute_pipeline()`** — hardened LLM planner with validation:
    - Max 4 steps enforced post-parse
    - Each step validated against live registry — unknown modules discarded
    - Utility modules (`web_search`, `image_gen`, `telegram`, `email`, `teams`) stripped unless explicitly mentioned by name in the user message
    - Thinking-block stripping (`<think>…</think>`) before JSON parsing
    - Timeout 10s with Tier-1 ReAct fallback on failure
    - Fallback to Tier 1 if 0 valid steps remain after filtering
  - **`_detect_module_fast()`** refactored to return `tuple[str | None, bool]` (module, is_compound)
  - **Compound detection hardened**: both top modules need score ≥ 3 AND second ≥ 40% of first (was: second ≥ 1). Utility modules excluded from compound scoring unless explicitly named. History fallback never triggers compound — only single-module detection from history
  - **`_UTILITY_MODULES` frozenset**: `{"web_search", "image_gen", "telegram", "email", "teams"}` — these modules are disqualified from compound scoring and pipeline steps unless the user explicitly names them
  - **`tier4_enabled: bool = True`** added to `RoutingConfig`; `fast` and `module-only` presets now set `tier4_enabled: False`
  - **`configure_routing`** tool: new `tier4_enabled` parameter
  - **`get_routing_info`** tool: cleaned up stale field references, shows Tier 4 status
  - **`_classify_tier()` updated to 3-tier order**: Tier 4 → Tier 2 → Tier 1

### Changed

- `orchestrator.py`: module-level docstring updated from "4-stufige Routing-Logik" to reflect current architecture
- `SYSTEM_PROMPT`: clarification that Tier-4 auto-detects explicit multi-module requests — avoids manual `run_pipeline` duplication from the ReAct loop

---

## [0.6.9] – 2026-03-28

### Fixed

- **Image display regression after v0.6.8**: Images no longer appeared inline in chat — they showed as "📷 Link: Klick hier" instead of rendered `<img>` tags. Three-part fix:
  1. **`frontend/app.js`** — Extended `[KUMIO_IMAGE:]` regex from `/api/images/...`-only to any URL (`[^\]]+`). External providers (Together AI, DALL-E, Google Imagen) return `https://` URLs, not local `/api/images/` paths — these were silently ignored by the old pattern.
  2. **`backend/modules/image_gen/agent.py`** — System prompt now explicitly instructs the LLM to preserve the `[KUMIO_IMAGE:url]` tag verbatim in its response. The previous instruction "Zeige dem User die Bild-URL" caused the LLM to reformat the tag into a markdown link.
  3. **`backend/agents/orchestrator.py`** — Added `BILD-TAGS` rule to the orchestrator system prompt: `[KUMIO_IMAGE:url]` from tool results must be passed through unchanged. Prevents the orchestrator LLM from reformatting the tag when handling image generation in its ReAct loop (Tier 1).

---

## [0.6.8] – 2026-03-28

### Changed

- **Routing simplified to 2 tiers** — removed all intermediate LLM routing calls and the hardcoded pipeline planner:
  - **Tier 2 (keyword fast-path)**: Single unambiguous keyword match → direct to module agent. No LLM overhead.
  - **Tier 1 (orchestrator ReAct loop)**: Everything else → `self.invoke()`. The LLM decides via `call_module_agent`, `run_pipeline`, `create_custom_agent`, or direct answer.
  - Removed: `_llm_classify_module()`, `_plan_and_execute_pipeline()`, `_route_tier3()`, `_has_multistep_indicators()`, `_has_workflow_intent()`, `_is_simple_query()`, `_build_module_descriptions()`, `_MULTISTEP_PATTERNS`, `_ACTION_VERBS`, LLM routing cache
  - `orchestrator.py`: 1066 → 575 lines (−491 lines)
- **`RoutingConfig` simplified**: Removed `tier3_enabled`, `tier4_enabled`, `llm_routing_enabled`, `llm_routing_timeout`, `llm_routing_cache_ttl`, `multistep_detection_enabled`, `simple_query_max_chars`. Only `tier1_enabled`, `tier2_enabled`, `preset` remain.
- **`SYSTEM_PROMPT` rewritten**: Replaced "4 Verarbeitungsstufen" framing with clear decision logic: when to use `call_module_agent` vs `run_pipeline` vs `create_custom_agent` vs direct answer.
- **`configure_routing` tool simplified**: Only `preset`, `tier1_enabled`, `tier2_enabled` parameters. Removed irrelevant LLM routing controls.

---

## [0.6.7] – 2026-03-28

### Fixed

- **Kubernetes log queries no longer misrouted to Tier 4 pipeline**: Three-part fix:
  1. Added `"logs"`, `"log"`, `"node"`, `"nodes"`, `"configmap"`, `"secret"`, `"volume"`, `"pvc"`, `"helm"`, `"kube-system"`, `"statefulset"` to kubernetes `routing_keywords` — `kubectl logs <pod>` queries now match directly in Stage 1 without history fallback
  2. Tightened compound detection threshold: second module now requires score ≥ 2 AND ≥ 40% of first module's score (was: ≥ 1). Prevents Tier 4 activation when one module clearly dominates (e.g. kubernetes:10, linux_server:1 from history)
  3. Improved pipeline planner prompt: constrains to minimum steps, max 3, and explicitly excludes web_search/image_gen/telegram/teams unless requested — eliminates hallucinated irrelevant module steps

---

## [0.6.6] – 2026-03-28

### Changed

- **Session-scoped routing config**: Routing adaptations are now session-scoped only — changes via `configure_routing` or proactive heuristics apply only for the current session and reset to defaults automatically afterward. No Redis persistence.
- **Proactive routing heuristics**: Three built-in synchronous heuristics (no LLM call) adapt routing automatically:
  - Speed signals (`schnell`, `quick`, `fast`, `brief`, etc.) in the message → auto-apply `fast` preset for the session
  - Reset signals (`default`, `normal`, `reset`, `zurück`, etc.) → restore default routing
  - Module focus (last 5+ consecutive Tier-2 requests to the same module) → disable LLM routing for the session
- **`_update_session_stats()`**: Tracks last 20 tier/module entries per session for heuristic analysis
- **`get_routing_info` tool**: Now reads from session-scoped config instead of Redis, shows `Source: Session | Default`
- Fixed `words` variable scope bug in `_proactive_routing_adjust()` — `words` is now computed before all heuristic checks

---

## [0.6.5] – 2026-03-28

### Added

- **Self-adaptive routing**: The orchestrator can now dynamically adjust its own routing logic at runtime via two new tools:
  - `configure_routing(preset, tier1_enabled, tier2_enabled, tier3_enabled, tier4_enabled, simple_query_max_chars, llm_routing_enabled, llm_routing_timeout, multistep_detection_enabled)` — the LLM reasons when to call this and which flags to change
  - `get_routing_info()` — read-only: returns current config + last tier used (registered as safe in `_TOOL_READONLY`)
- **`RoutingConfig` dataclass** in `orchestrator.py` with all routing parameters as typed fields and `from_dict`/`to_dict` helpers
- **`ROUTING_PRESETS`** dict: `default` (all tiers, LLM routing on), `fast` (no LLM routing, no Tier 3/4), `module-only` (no Tier 1, no Tier 3/4)
- **In-process 10s cache** for routing config — no Redis round-trip per message; `_invalidate_routing_cache()` forces immediate reload after tool call
- Orchestrator `SYSTEM_PROMPT` extended with guidance on when and how to adapt routing
- `_classify_tier()` now respects all config flags; Tier 3 disabled → fallback to Tier 1

---

## [0.6.4] – 2026-03-28

### Changed

- **Sub-navigation relocated to sidebar**: The sub-navigation menus for Automatisierung (Tasks/Agents/Workflows), Modules, and Settings are now displayed inside the sidebar (where the chat history was) instead of as a second column within the main content area. The sidebar dynamically switches between showing chat history (in the chat tab) and showing the contextual sub-navigation (in the other tabs). All three content areas (auto-content, modules-content, settings-main) now fill the full width of the main panel.

---

## [0.6.3] – 2026-03-28

### Changed

- **Typography: Manrope replaces Lora as the UI typeface** (`frontend/style.css`, `frontend/index.html`) — Manrope (Google Fonts, geometric sans-serif, weights 300–800) is loaded as the global body font. Better fit for a technical dashboard than the serif Lora.
- **Logo: Reiko font** (`frontend/style.css`) — The "Ninko" wordmark uses Reiko, a futuristic geometric typeface. Loaded via `@font-face` from `frontend/fonts/Reiko.woff2`. Place the font file there after downloading from https://fontesk.com/reiko-font/ (free for commercial use). Until the file is present, falls back to Georgia/serif.

---

## [0.6.2] – 2026-03-28

### Added

- **Helm Chart** (`charts/ninko/`) — Full Helm chart for the complete Ninko stack, published to `https://natorus87.github.io/ninko/`:
  - Backend (FastAPI): Deployment, Service, PVC (2 Gi), ServiceAccount, ClusterRole + ClusterRoleBinding
  - Redis 7-alpine: Deployment, Service, PVC (1 Gi)
  - ChromaDB 0.4.24 (pinned): Deployment, Service, PVC (5 Gi)
  - SearXNG (optional): Deployment, Service, ConfigMap with settings.yml
  - Standard Kubernetes Ingress and Traefik IngressRoute — both optional, both off by default
  - All resource names are Helm-release-scoped for multi-release coexistence
  - `secrets.sqliteSecretsKey` is required and validated at install time with a helpful error message
- **GitHub Actions workflow** (`.github/workflows/helm-release.yml`) — `chart-releaser-action` v1.6.0 auto-packages and publishes the chart on every push to `main` that touches `charts/**`. Updates `index.yaml` on the `gh-pages` branch automatically.
- **Helm repository** live at `https://natorus87.github.io/ninko/`:
  ```bash
  helm repo add ninko https://natorus87.github.io/ninko
  helm repo update
  helm install ninko ninko/ninko \
    --set secrets.sqliteSecretsKey=$(python3 -c "import secrets; print(secrets.token_hex(32))") \
    --set backend.llm.baseUrl=http://YOUR_LMSTUDIO_HOST:1234 \
    --set backend.llm.model=YOUR_MODEL \
    --set ingressRoute.enabled=true \
    --set ingressRoute.host=ninko.your-domain.local
  ```

### Changed

- **UI: Base font size increased from 14px to 16px** (`frontend/style.css`) — The previous 14px base caused all rem-based measurements to render too small, especially in submenu panels (Automatisierung, Einstellungen, Workflows), settings forms, and task cards. Increasing to the industry-standard 16px scales all rem values proportionally (~14% increase) without breaking any absolute-pixel layout values (sidebar width 250px, header height 60px, etc.).
- **Buttons: larger padding and font size** — `.btn` padding increased from `0.5rem 1.125rem` to `0.6rem 1.35rem`, font-size from `0.875rem` to `0.9rem`. `.btn-sm` padding from `0.25rem 0.5rem` to `0.35rem 0.75rem`.
- **Form inputs/selects: taller hit area** — `.form-input`/`.form-select` padding increased to `0.55rem 0.875rem` (previously `0.5rem 0.75rem`).
- **Form labels: more readable** — `.form-label` font-size from `0.8rem` to `0.85rem`, bottom margin from `0.25rem` to `0.3rem`.
- **Settings tabs: better touch target** — `.settings-tab` vertical padding from `0.75rem` to `0.85rem`.
- **Task cards: more breathing room** — `.task-card-header` and `.task-card-body` padding from `0.75rem 1rem` to `0.9rem 1.1rem`. `.task-prompt` font-size `0.875rem`, `.task-meta` `0.8rem`, `.task-badge` font-size `0.75rem` and padding `0.2rem 0.55rem`.

---

## [0.6.1] – 2026-03-28

### Fixed

- **Marketplace: GitHub API rate limit during installation** (`backend/api/routes_plugins.py`) — Three separate GitHub API calls were exhausting the 60 req/h unauthenticated limit:
  1. Module existence check: replaced `GET /repos/.../contents/{path}` with a `raw.githubusercontent.com` fetch of `__init__.py` (no rate limit).
  2. File tree listing: replaced `GET /repos/.../git/trees/{branch}?recursive=1` (Git Trees API, still rate-limited) with a full repo tarball download from `https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.tar.gz` — no API at all, no authentication required. Only the relevant module subdirectory is extracted from the tarball.
  3. Result: the entire install flow now makes **zero** `api.github.com` calls.

- **Installed plugins with `enabled_by_default=False` not loading** (`backend/core/module_registry.py`) — `_load_module()` checked `manifest.enabled_by_default` for plugins too. Modules like `fritzbox`, `homeassistant`, `opnsense`, `wordpress` have `enabled_by_default=False` (since they require explicit configuration before use). When installed via the Marketplace, they were silently blocked at startup. Fix: when `is_plugin=True`, default to `enabled=True` regardless of `enabled_by_default`; an explicit `NINKO_MODULE_<NAME>=false` env var still overrides.

- **Hot-loaded plugin routes shadowed by StaticFiles catch-all** (`backend/core/module_registry.py`) — FastAPI registers a `Mount("/", StaticFiles(...))` at the end of startup. Routes added at startup by `register_routes()` are inserted before this mount. Routes added later by `hot_load_plugin()` via `app.include_router()` were appended after the mount, so Starlette's route iteration hit the `StaticFiles` handler first — returning 404 for every `/api/{plugin}/*` endpoint. Fix: after calling `app.include_router()`, the newly appended routes are detected, removed from the end of `app.router.routes`, and re-inserted immediately before the `StaticFiles` mount.

---

## [0.6.0] – 2026-03-28

### Added

- **Module Marketplace** (`backend/api/routes_plugins.py`, `frontend/app.js`, `frontend/index.html`) — Install and update catalog modules at runtime without rebuilding the Docker image:
  - Multi-repo support: `GET/POST/PUT/DELETE /api/plugins/marketplace/repos` manage a list of GitHub repos stored in Redis (`ninko:settings:marketplace_repos`).
  - Official repo (`https://github.com/natorus87/ninko`, branch `main`, path `backend/modules_catalog`) is pre-configured and cannot be deleted.
  - Community repos can be added with name, URL, branch, modules path, and optional GitHub token.
  - `GET /api/plugins/marketplace/repos/{id}/modules` — fetches module metadata from GitHub Contents API (5-min cache per repo). Returns two lists: `modules` (available to install) and `updates` (already-installed plugins with a newer version in the repo).
  - `POST /api/plugins/install-from-repo/{module_name}?repo_id={id}` — downloads module directory recursively into an in-memory ZIP, extracts to `backend/plugins/`, runs `pip install requirements.txt` if present, and hot-loads via `ModuleRegistry.hot_load_plugin()`.
  - Tokens never returned by the API (`_mask_repo()` replaces with `github_token_set: bool`).
  - Version comparison via `_version_tuple()` — only installed plugins (not core modules) show an "Update" button.
  - All marketplace UI text uses the i18n system (45 new `marketplace.*` keys in all 10 language files).

- **`backend/modules_catalog/`** — New directory for all non-core modules. Excluded from the Docker image via `.dockerignore`. Tracked in git as the official marketplace source.

- **Checkmk module** (`backend/modules_catalog/checkmk/`) — Monitoring integration:
  - `get_checkmk_hosts`, `list_checkmk_services`, `get_checkmk_service_status`, `get_checkmk_alerts`, `acknowledge_checkmk_alert`, `get_checkmk_host_details`, `schedule_checkmk_downtime`, `get_checkmk_site_status`, `run_checkmk_service_discovery` — 9 tools (read-only tools registered in `_TOOL_READONLY`).
  - Basic auth via connection manager (`CHECKMK_URL`, `CHECKMK_USERNAME`, `CHECKMK_PASSWORD`).

### Changed

- **Core/Catalog split** — Only `web_search`, `image_gen`, and `codelab` remain as core modules in `backend/modules/` (baked into the image). All 17 other modules moved to `backend/modules_catalog/`: `kubernetes`, `proxmox`, `glpi`, `ionos`, `fritzbox`, `homeassistant`, `pihole`, `telegram`, `email`, `wordpress`, `opnsense`, `tasmota`, `docker`, `linux_server`, `qdrant`, `teams`.
- **`docker-compose.yml` and `k8s/backend/deployment.yaml`** — Removed all `NINKO_MODULE_*` env vars except the three core modules (`WEB_SEARCH`, `CODELAB`, `IMAGE_GEN`). Catalog modules are enabled automatically when installed via the marketplace.

---

## [0.5.12] – 2026-03-28

### Fixed

- **OPNsense `tools.py`: API key never retrieved from Vault** — `_get_opnsense_auth()` only loaded `OPNSENSE_API_SECRET` from Vault; `api_key` (stored via `isSecret: true` in the connection form) was silently ignored, so all API calls were unauthenticated. Added Vault lookup for `api_key` via `conn.vault_keys.get("api_key")`.
- **OPNsense `get_opnsense_system_status`: wrong endpoint** — `/api/core/system/status` returns only plugin metadata (`{"metadata": {...}}`), not system metrics. Replaced with `asyncio.gather` of four correct endpoints: `systemTime` (uptime, loadavg), `firmware/info` (version), `systemResources` (memory used/total), `systemDisk` (disk usage %). Return value now contains `uptime` as a human-readable string and `cpu` as a float (1-minute load average, not %).
- **OPNsense `tab.js`: uptime rendered as raw seconds** — `formatUptime(status.uptime)` converted an integer seconds value that no longer exists; `status.uptime` is now a string like `"6 days, 14:38:16"`. Fixed to `${status.uptime || '-'}`. Removed the now-unused `formatUptime` helper.
- **OPNsense `tab.js`: CPU label and format** — Label was `CPU` and value was `${status.cpu || 0}%`. Since the backend now returns a 1-minute load average float, the label is changed to `Load (1m)` and the value uses `.toFixed(2)` instead of appending `%`.
- **OPNsense `tab.js`: services always showing "Inaktiv"** — Template used `svc.enabled` but `tools.py` was changed (v0.5.11) to return `svc.running` (bool). Updated to `svc.running`.
- **`app.js`: "Lade Verbindungen..." stuck for OPNsense, Qdrant, Tasmota** — Missing `ACTION_FIELDS` entries caused the connection settings panel to spin forever. Added form field definitions for all three modules.
- **`k8s-conbro/backend/deployment.yaml`: wrong deployment name** — `metadata.name` was `ninko-backend` instead of `kumio-backend`, causing `kubectl apply` to create a second spurious deployment rather than updating the live one. Corrected name and added explicit `namespace: kumio`. Spurious `ninko-backend` deployment removed from cluster.
- **`k8s-conbro/backend/deployment.yaml`: Qdrant module enabled** — Added `NINKO_MODULE_QDRANT: "true"` env var.

---

## [0.5.11] – 2026-03-28

### Fixed

- **OPNsense module: all six API endpoints corrected** (`backend/modules/opnsense/tools.py`) — Verified live against OPNsense 24.x; all original endpoints returned 404:
  - `get_opnsense_interfaces`: `GET /api/interfaces/overview/get` → `POST /api/interfaces/overview/interfacesInfo`; field mapping updated (`device`, `description`, `addr4`, `macaddr`)
  - `get_opnsense_firewall_rules`: `/api/filter/rule/searchRule` → `/api/firewall/filter/searchRule`
  - `get_opnsense_nat_rules`: `/api/nat/rule/searchRule` → `/api/firewall/filter/searchRule?type=nat`
  - `get_opnsense_services`: `/api/service/searchService` → `/api/core/service/search`; field mapping updated (`running` int instead of `enabled` string)
  - `get_opnsense_logs`: `/api/filter/log/filter/{n}` → `/api/diagnostics/firewall/log`; response is a direct JSON array (not a dict); return type changed from `List[str]` to `List[Dict]`
  - `restart_opnsense_service`: `/api/service/service/restart/{n}` → `/api/core/service/restart/{n}`
  - `_opnsense_request` return type changed from `Dict` to `Any` to correctly handle list responses
- **OPNsense `tab.js`: garbage text in innerHTML template** (`frontend/tab.js`) — Tool description text was accidentally embedded inside the System card template literal, rendering as visible plaintext in the browser
- **OPNsense `tab.js`: auto-refresh never started** — `startPolling()` was defined but never called in `init()`; added call after first `refresh()`
- **OPNsense `tools.py`: mixed f-string + `%s` logging** — `logger.error(f"...: %s", e)` in `restart_opnsense_service` left the `%s` unreplaced; corrected to `logger.error("...: %s", e)`
- **OPNsense `tools.py`: mutable default argument** — `json_data: dict = None` → `json_data: dict | None = None`
- **OPNsense `tools.py`: redundant host check** — `if not host: raise` after `_get_opnsense_auth()` was dead code (helper already raises); removed
- **OPNsense `manifest.py`: duplicated auth logic in health check** — `check_opnsense_health()` now calls `_get_opnsense_auth()` from `tools.py` instead of re-implementing Vault secret loading
- **OPNsense `manifest.py`: routing keyword conflicts** — Removed short generic keywords (`pf`, `wan`, `lan`, `opt`, `routing`, `dhcp`, `dns`, `vpn`, `blockieren`, `erlauben`, `regel`, `rules`, `filter`) that conflicted with FritzBox/HomeAssistant modules; replaced with specific multi-word phrases (`firewall regel`, `opnsense dhcp`, `nat regel`, etc.)
- **OPNsense `routes.py`: untyped dict responses** — All three route handlers now return a typed `ApiResponse` Pydantic model with `response_model` annotations

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
