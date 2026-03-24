# Changelog

Alle nennenswerten Änderungen an Kumio werden in dieser Datei dokumentiert.

Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/).

---

## [1.0.0] – 2026-03-24

Erster stabiler Release. Kumio ist eine modulare, KI-gestützte IT-Operations-Plattform auf Basis von FastAPI (Python 3.12) mit einem unveränderlichen Core und auto-discovering Modulen.

### Core-Architektur

- **Modulares Auto-Discovery-System** – `ModuleRegistry` scannt `backend/modules/` und `backend/plugins/` beim Start, registriert Agenten, Router und Keywords. Keine Modul-Namen im Core hardcodiert.
- **4-stufiges Orchestrator-Routing** (`orchestrator.py`):
  - Tier 1 – Direktantwort (einfache Fragen, < 120 Zeichen, keine Action-Verben)
  - Tier 2 – Modul-Agent-Delegation via zweistufigem Keyword + LLM-Routing
  - Tier 3 – Dynamischer Agent (Pool-Suche oder LLM-generierter Agenten-Spec)
  - Tier 4 – Deterministisches Pipeline-Routing für Multi-Modul-Aufgaben
- **LLM-basiertes Modul-Routing** – `_detect_module()` (async, zweistufig): Keyword-Schnellpfad + LLM-Klassifikation bei Score=0 oder Ambiguität. MD5-Cache (TTL 60s), 8s Timeout, vollständiger Fallback.
- **Dynamic Agent Pool** – `DynamicAgentPool` mit Redis-Persistenz, Jaccard-Scoring (Threshold 18%), 4 Basis-Tools für Tier-3-Agenten.
- **Workflow Engine** – Async DAG mit Trigger, Agent, Condition, Loop, Variable, End-Nodes. Zustand in Redis.
- **LLM-Factory** – Multi-Provider: `ollama`, `lmstudio`, `openai_compatible`. Auto-`/v1`-Anhang, Context-Window-Auto-Detection, `MAX_OUTPUT_TOKENS=16384`.

### KI-Fähigkeiten

- **Soul System** – Persistente Agenten-Identitäten (Soul MDs). Built-in: `backend/souls/`. Dynamisch: Redis `kumio:souls`. Injiziert vor RAG/Skills/Sprache in `final_system_prompt`.
- **Skills System** – SKILL.md-Format mit YAML-Frontmatter. Hot-Reload via `install_skill`-Tool. Max. 2 Skills/Request injiziert (threshold 12%). GUI: `GET/POST/PUT/DELETE /api/skills/`.
- **Langzeitgedächtnis** – ChromaDB-backed `SemanticMemory`. Tools: `remember_fact`, `recall_memory`, `forget_fact` (Vorschau-Flow), `confirm_forget`. Auto-Memorize mit Cooldown (60s) und Agenten-Ausschlüssen.
- **Kontext-Komprimierung** – LLM-Summary bei Überschreitung des Context-Window-Budgets (25% des Modell-Fensters). Compaction-Summary als SystemMessage erhalten. Frontend-Benachrichtigung `⟳`.
- **JIT Tool Injection** – Bei > 6 Tools: max. 8 kontextrelevante Tools per Request, Keyword-Match gegen Name + Docstring (min. 2 Zeichen).

### LM Studio / Thinking-Modell-Kompatibilität

- **`_NormalizingChatOpenAI`** – Normalisiert Listen-Content zu String (Jinja `is sequence`-Bug).
- **`_LMStudioChatOpenAI`** – Zusätzlich: `_inject_tools_into_system()` (Tool-Defs als Text), `_convert_tool_messages_to_text()` (XML `<tool_call>`/`<tool_response>`-Format für Qwen3.5).
- **`_strip_thinking()`** – Entfernt `<think>...</think>`-Blöcke aus Thinking-Modell-Antworten.
- Alle direkten LLM-Calls über `[HumanMessage(content=...)]` für strikte Jinja-Template-Kompatibilität.

### Mehrsprachigkeit (i18n)

- `_t(de, en)` + `_get_language()` in `base_agent.py`, importierbar in `orchestrator.py`.
- `_LANG_INSTRUCTIONS` für 10 Sprachen – automatisch ans Ende des System-Prompts injiziert.
- Auto-Memorize Stop-Wörter: 9 Sprachen (`NICHTS|NOTHING|RIEN|NADA|NULLA|NIETS|NIC|何もない|没有`).
- Frontend: Vanilla-JS `I18n`-Klasse mit `[data-i18n]`-Attributen, 10 Sprach-JSONs.

### Module (15 aktive)

| Modul | Beschreibung |
|---|---|
| `kubernetes` | Cluster-Management, Pods, Deployments, Services, Logs |
| `proxmox` | VMs, Container, Backups, Snapshots, Nodes |
| `glpi` | Helpdesk-Tickets, Assets, ITSM |
| `ionos` | DNS-Zonen und Record-Management via IONOS Hosting API |
| `fritzbox` | Netzwerkstatus, externe IP, WLAN, Verbundene Geräte |
| `homeassistant` | Smart-Home: Licht, Heizung, Sensoren, Automatisierungen |
| `pihole` | Pi-hole v6 Blocking, Statistiken, Query-Log, Custom DNS |
| `web_search` | SearXNG-basierte Websuche (Bing, Mojeek, Qwant) |
| `telegram` | Telegram Bot mit Voice-Transkription und TTS-Antworten |
| `email` | SMTP-Versand und IMAP-Abruf |
| `wordpress` | Posts, Medien, Seiten via WordPress REST API |
| `codelab` | Code-Ausführung und Debugging |
| `docker` | Container-Management |
| `linux_server` | Server-Administration via SSH/CLI |
| `image_gen` | KI-Bildgenerierung |

### TTS / STT

- **Piper TTS** – Lokal im Backend-Pod, Lazy-Load. `POST /api/tts/synthesize`. Voice-Katalog, `_clean_for_tts()` für Markdown/Emoji-Bereinigung.
- **Whisper STT** – `faster-whisper` im Backend. `POST /api/transcription/`. Unterstützt `base`/`small`-Modelle.
- **Telegram Voice** – Automatische Sprachantworten wenn User eine Voice-Nachricht sendet.

### Chat-UI

- **AI-Bubble**: `max-width: 90%` (User: 70%) – mehr Platz für lange Antworten.
- **Tabellen**: `display: block; overflow-x: auto` – horizontales Scrollen statt Clipping.
- **Textarea**: Scrollbar ausgeblendet (`scrollbar-width: none`), Auto-Resize via JS.
- **Step-Log**: Live-Statusanzeige mit CSS-Spinner (aktiv) und ✓-Häkchen (abgeschlossen) via SSE.
- **Theme**: Light/Dark mit FOUC-Prävention (inline `<script>` in `<head>`).
- **Komprimierungsbenachrichtigung**: `⟳ Gesprächsverlauf komprimiert`-Bubble bei Kontext-Reset.

### Infrastruktur & Deployment

- **Dev**: `docker-compose.yml` – Backend, Redis, ChromaDB, SearXNG, Vault-Fallback (SQLite).
- **Prod**: Kubernetes/MicroK8s, Namespace `kumio`, Image `natorus87/kumio-backend:latest`, Traefik IngressRoute `kumio.conbro.local`.
- **Plugin-System**: ZIP-installierbare Plugins mit Hot-Load zur Laufzeit. Namensvalidierung gegen Path-Traversal.
- **Secrets**: HashiCorp Vault mit SQLite-Fallback (`VAULT_FALLBACK=sqlite`).
- **ChromaDB**: Gepinnt auf `0.4.24`, `numpy<2.0.0`.

### Bekannte Fixes in dieser Version

- Orchestrator-Retry-Loop: Fehlermeldungen starten mit `"Fehler: ..."` – kein "Bitte versuche es erneut."
- Compact-Matching-Threshold `>= 7` (war `>= 4`) – verhindert Komposita-Fehlrouting.
- Telegram-Kontext-Präfix-Routing: `_strip_bot_context()` entfernt `[Telegram Chat-ID: ...]` vor Routing-Detection.
- LangGraph `recursion_limit=10000` + 1800s Timeout als echte Sicherheitsnetz.
- `invoke()` gibt `tuple[str, bool]` zurück – alle Aufrufer müssen entpacken.
- Compaction-Summary als `role=="system"` in History-Loop als `SystemMessage` erhalten.
- `crypto.randomUUID()` Fallback via `Math.random()` für non-secure HTTP-Contexts.

---

## Versionshistorie

| Version | Datum | Beschreibung |
|---|---|---|
| 1.0.0 | 2026-03-24 | Erster stabiler Release |
