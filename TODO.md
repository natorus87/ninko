# Kumio – Offene TODOs

Stand: 2026-03-23

---

## TTS & STT – Verbesserungen

### TTS im Web-Dashboard

- [x] **TTS-Tab in den Core-Einstellungen** ✅ *2026-03-14*
  - TTS aktivieren/deaktivieren (Toggle) ✅
  - Standard-Stimme als Dropdown (aus installierten Stimmen befüllt) ✅
  - Standard-Sprache + Sample Rate ✅
  - Felder: `TTS_ENABLED`, `PIPER_BINARY`, `VOICES_DIR`, `TTS_DEFAULT_LANG`, `TTS_DEFAULT_VOICE`, `TTS_SAMPLE_RATE` ✅
  - Gespeichert in Redis (`kumio:settings:tts`), sofort in ENV übernommen ✅
  - Live-Vorschau: Audio-Player + Abspielen-Button ✅
  - API: `GET /api/tts/voices` ✅ | `POST /api/tts/synthesize` ✅

- [x] **Stimmen-Download & -Verwaltung im Dashboard** ✅ *2026-03-14*
  - Installierte Stimmen als Tabelle mit Lösch-Button ✅
  - Preset-Buttons (thorsten-medium, kerstin-low, ramona-low, eva_k-x_low, lessac-medium, ryan-medium) ✅
  - Download-Formular → `POST /api/tts/voices/download` ✅
  - `DELETE /api/tts/voices/{lang}/{voice}` ✅
  - Hot-reload: kein Neustart nötig ✅

- [ ] **Stimmen-Katalog aus HuggingFace** (nice-to-have)
  - Alle bekannten Stimmen mit Status "Installiert / Nicht installiert" anzeigen
  - Gefiltert nach Sprache
  - Aktuell: Freitext-Download mit Preset-Buttons als Hilfe

### TTS für Modul-Verbindungen (Telegram / Teams)

- [x] **Voice-Reply-Config im Verbindungs-Dashboard** ✅ *2026-03-14*
  - Telegram: Checkbox `voice_reply` + `voice_reply_text_too` + `voice_lang/voice_name` ✅
  - Teams: Checkbox `voice_reply` + `voice_reply_text_too` + `voice_lang/voice_name` ✅
  - Backend: `GET/POST /api/telegram/voice-reply` + `GET/POST /api/teams/voice-reply` ✅
  - Stimme pro Verbindung überschreibt System-Default ✅

---

### STT – Robustheit & Qualitätssicherung

- [x] **Transkriptions-Confidence: Nachfrage bei Unsicherheit** ✅ *2026-03-14*
  - `transcribe_bytes_extended()` gibt `(text, avg_logprob, detected_lang)` zurück ✅
  - Telegram & Teams: Bei `avg_logprob < STT_CONFIDENCE_THRESHOLD` (Default: -1.0) → Rückfrage ✅
  - Config: `STT_CONFIDENCE_THRESHOLD: float = -1.0` in `core/config.py` ✅

- [x] **Rechtschreibkorrektur nach STT** ✅ *2026-03-14*
  - `_llm_spellcheck()` in `routes_transcription.py` — optionaler LLM-Pass ✅
  - Aktivierung via `STT_SPELLCHECK=true` (Env/Config) ✅

- [x] **Sprache auto-erkennen + an Agenten weitergeben** ✅ *2026-03-14*
  - Erkannte Sprache wird als `[Erkannte Sprache: xx]`-Präfix übergeben wenn `WHISPER_LANGUAGE=auto` ✅
  - Telegram + Teams Bot aktualisiert ✅

---

## TTS – Dynamische Erweiterbarkeit (Stimmen-Verwaltung)

- [x] **Stimmen-Verzeichnis hot-reload** ✅
- [x] **Sample Rate konfigurierbar** ✅ (`TTS_SAMPLE_RATE` in Settings + Frontend)

- [ ] **Piper-Binary auto-update**
  - Zukünftig: `GET /api/tts/piper/version` → zeigt installierte Version + neueste GitHub-Release

---

## Skills & Agenten (2026-03-20)

- [x] **Skills GUI** ✅ *2026-03-20*
  - Skills-Panel (Übersicht aller built-in + runtime Skills) ✅
  - Skill-Editor (erstellen/bearbeiten/löschen) ✅
  - Skills-Sektion im Agent-Editor-Sidebar ✅
  - `GET/POST/PUT/DELETE /api/skills/` via `routes_skills.py` ✅
  - Built-ins geschützt vor Löschen ✅

- [x] **6 neue built-in Skills** ✅ *2026-03-20*
  - `fritzbox-network-diagnostics`, `homeassistant-automation`, `glpi-ticket-workflow`
  - `email-alert-templates`, `web-search-strategy`, `wordpress-publishing`

## STT Provider-Auswahl (2026-03-20)

- [x] **STT Provider-Wahl in Einstellungen** ✅ *2026-03-20*
  - Provider: `whisper` (lokal) oder `openai_compatible` (extern) ✅
  - Redis-Persistenz + Startup-Restore ✅
  - Whisper-Cache-Invalidierung bei Modell-Wechsel ✅

## Bug Fixes (2026-03-20)

- [x] **LLM Provider-Wechsel wirkte nicht** ✅ *2026-03-20* — Generation-Counter in `llm_factory.py`, Re-Init in `base_agent.invoke()`
- [x] **index.html Browser-Cache** ✅ *2026-03-20* — `Cache-Control: no-cache` Route in `main.py`
- [x] **CodeLab JavaScript** ✅ *2026-03-20* — `nodejs` in Dockerfile
- [x] **LLM Settings erster Load** ✅ *2026-03-20* — `loadSettingsContent()` lädt Provider + EmbedModel

## Orchestrator-Routing: LLM-Klassifikation statt Keywords

> **Motivation:** Das keyword-basierte Routing ist spröde und wartungsintensiv. Kurze deutsche Wörter (`"licht"`, `"sensor"`) matchen fälschlicherweise in Komposita (`"durchschnittlich täglich"` → HA). Jedes neue Modul braucht handgepflegte Keywords. Semantisch ähnliche Anfragen ohne Keywords landen im falschen Tier.

### Plan

- [x] **Neuer LLM-Klassifikations-Call in `_classify_tier()` / `_detect_module()`** ✅ *2026-03-23*
  - Vor dem bisherigen Keyword-Matching (oder als Ersatz für Tier-2-Routing) einen kurzen strukturierten LLM-Call machen:
    ```
    System: "Du bist ein Router. Antworte NUR mit dem Modulnamen oder 'none'."
    User: "Nachricht: {message}\nVerfügbare Module: kubernetes (Pods, Deployments, Cluster),
           homeassistant (Smarthome, Licht, Heizung), proxmox (VMs, Backup), ..."
    ```
  - Antwort: `"kubernetes"` | `"homeassistant"` | `"none"` (kein JSON, kein Markup)
  - Timeout: 8s, Fallback: bei Fehler/Timeout → bisheriges Keyword-Matching

- [x] **Keyword-Matching als Schnellpfad behalten** ✅ *2026-03-23*
  - Bei eindeutig explizit genannten Modulnamen (`"kubernetes"`, `"proxmox"`, `"pihole"` etc.) kein LLM-Call nötig
  - Nur bei Keyword-Score = 0 oder Ambiguität (mehrere Module > 0) → LLM-Klassifikation

- [x] **Modulbeschreibungen für den Prompt aufbereiten** ✅ *2026-03-23*
  - Aus `ModuleManifest.description` + ein paar `routing_keywords` als Beispiele
  - Dynamisch aus Registry gebaut → kein Hardcoding (`_build_module_descriptions()`)

- [x] **Caching** ✅ *2026-03-23*
  - Gleiche Nachricht (hash) → gecachtes Ergebnis, TTL 60s
  - Verhindert doppelte Calls bei schnellen Folgenachrichten

- [x] **Logging & Evaluierung** ✅ *2026-03-23*
  - Im Log: welche Methode hat geroutet (keyword / llm / fallback)
  - Basis für spätere Auswertung ob LLM-Routing besser ist

---

## Sonstiges (aus anderen Bereichen)

- [ ] HTTPS für `kumio.conbro.local` via Traefik IngressRoute + selbstsigniertes Zertifikat → aktiviert `getUserMedia` + `crypto.randomUUID()` nativ ohne Chrome-Flag
- [ ] `test_tts.py` in CI-Pipeline einbinden
- [ ] Whisper-Modell-Upgrade: `base` → `small` testen (bessere DE-Qualität, ~300 MB statt 75 MB)
- [ ] Stimmen-Katalog aus HuggingFace (nice-to-have): alle Stimmen mit Status "Installiert / Nicht installiert"
