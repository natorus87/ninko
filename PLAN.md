# Plan: Canonical English Prompts for Multilingual Ninko

## Ziel

Ninko soll intern stabile, einheitliche System-Prompts verwenden und trotzdem in der Sprache des Users antworten.
Dafuer werden Modul- und Agent-Prompts schrittweise auf englische Canonical Prompts umgestellt. Die Antwortsprache bleibt zentral ueber Middleware und Settings gesteuert.

## Problem

Aktuell enthalten viele Prompts sprachspezifische Varianten, z.B. via `_t(de=..., en=...)`. Dadurch laufen Regeln auseinander:

- Formatregeln koennen in einer Sprache fehlen.
- Modulverhalten haengt unbeabsichtigt von `LANGUAGE` ab.
- Aenderungen muessen mehrfach gepflegt werden.
- Tests gegen Prompt-Verhalten werden schwerer, weil mehrere Prompt-Versionen existieren.

Konkretes Beispiel: Beim Kubernetes-Modul stand die Tabellenregel im englischen Prompt, fehlte aber im deutschen Prompt. Dadurch kamen je nach Sprache knappe Antworten oder rohe JSON-/Python-Strukturen im Frontend an.

## Zielarchitektur

- System-, Agent- und Modul-Prompts sind intern Englisch.
- User-facing Antworten werden weiterhin in der konfigurierten Sprache erzeugt.
- Sprachsteuerung liegt zentral in `LanguageMiddleware` und nicht in jedem Modul-Prompt.
- Formatregeln sind sprachneutral und werden nur einmal definiert.
- Kritische Ausgabeformate werden mit Regressionstests abgesichert.

## Prompt-Prinzipien

Canonical Prompt:

```text
You are Ninko's Kubernetes specialist.

Rules:
- Always call tools for live cluster data.
- For status/detail/overview requests, answer with a short assessment followed by Markdown tables.
- Never return raw JSON or Python repr as the final answer.

Response language:
- Answer in the user's configured language.
```

Nicht mehr gewuenscht:

```python
_t(
    de="Du bist ...",
    en="You are ...",
)
```

Ausnahme: User-facing statische Fehlermeldungen, UI-Texte und API-Antworten duerfen weiterhin lokalisiert sein.

## Migrationsphasen

### Phase 1: Prompt-Inventar

- Alle Modul- und Agent-Prompts erfassen.
- Prompts nach Risiko priorisieren:
  - Hoch: Infrastrukturmodule wie Kubernetes, Proxmox, Docker, Linux Server, Checkmk.
  - Mittel: Kommunikations- und Produktivitaetsmodule.
  - Niedrig: einfache Utility-Module.
- Fuer jeden Prompt dokumentieren:
  - Datei
  - aktuell verwendete Sprachen
  - Formatregeln
  - Tool-Ausfuehrungsregeln
  - sicherheitsrelevante Regeln

### Phase 2: Zentrale Sprachregel haerten

- `LanguageMiddleware` als einzige Quelle fuer Antwortsprache definieren.
- Sicherstellen, dass jeder Agent-Prompt am Ende eine zentrale Regel erhaelt:
  - "Answer in the user's configured language."
  - Optional: "Keep technical identifiers, resource names, commands, and JSON keys unchanged."
- Tests ergaenzen, die bestaetigen, dass deutsche Userfragen weiterhin deutsche Antworten ausloesen.

### Phase 3: Hochrisiko-Module migrieren

Startreihenfolge:

1. Kubernetes
2. Proxmox
3. Docker
4. Linux Server
5. Checkmk / Zabbix

Pro Modul:

- `_t(de=..., en=...)` im System-Prompt durch einen englischen Canonical Prompt ersetzen.
- Regeln in klare Abschnitte trennen:
  - Role
  - Capabilities
  - Tool execution rules
  - Output format
  - Safety / confirmation rules
  - Error handling
- Keine User-facing Sprache hart im Prompt festlegen.
- Bestehende Modul-spezifische Gotchas unveraendert uebernehmen.

### Phase 4: Output-Format-Regressionen

Fuer jedes kritische Modul Tests ergaenzen:

- Listen duerfen nicht als rohes JSON/Python-Repr ausgegeben werden.
- Status-/Detailfragen liefern eine kurze Einschaetzung plus Markdown-Tabelle.
- Tool-Fallbacks werden lesbar formatiert.
- Fehlerantworten enthalten keine Secrets und keine Stacktraces.

Bereits vorhandenes Muster:

- `backend/tests/test_kubernetes_response_formatting.py`

Dieses Muster kann fuer weitere Module wiederverwendet werden.

### Phase 5: Generischer Tool-Fallback

Der aktuelle Kubernetes-spezifische Fallback ist bewusst eng geschnitten. Danach pruefen:

- Welche Module liefern strukturierte Listen/Dictionaries?
- Ob ein generischer Markdown-Table-Fallback fuer `list_*`/`get_*` Tools sinnvoll ist.
- Welche Module eigene Spaltenreihenfolgen brauchen.

Ziel: Rohes JSON nur noch dann anzeigen, wenn der User explizit JSON verlangt.

### Phase 6: Cleanup und Konvention

- Neue Regel in Projekt-Dokumentation aufnehmen:
  - "New agent/module system prompts must be written in English."
  - "Response language is controlled centrally."
- README/CLAUDE.md nur kurz verlinken, Details in `.claude/memory/` oder `.claude/rules/`.
- Prompt-Review in PR-/Review-Checkliste aufnehmen.

## Review-Findings vom 2026-05-15

### Findings zur aktuellen uncommitted Umsetzung

1. ✅ **Behoben (2026-05-15):** `backend/agents/middleware/postprocess.py`: `preferred_table_columns` sind jetzt modul-qualifiziert.
   - Fix: `_PREFERRED_COLUMNS_BY_TOOL` durch `_PREFERRED_COLUMNS_BY_AGENT_TOOL: dict[str, dict[str, list[str]]]` ersetzt (`{"kubernetes": {"list_services": [...]}}`).
   - Lookup ueber neuen Helper `_preferred_columns_for(agent_name, tool_name)`; `_format_structured_as_table` und `_format_tool_fallback` nehmen jetzt `agent_name` als Parameter entgegen.
   - Damit kollidieren `list_services` (Kubernetes vs. Linux Server) und `get_nodes` (Proxmox vs. eventuelle Kollisionen) nicht mehr.
   - Regression: `test_kubernetes_list_services_keeps_k8s_columns` und `test_linux_server_list_services_uses_systemd_columns` in `backend/tests/test_module_response_formatting.py`.

2. ✅ **Behoben (2026-05-15):** AI-Antwort-Augmentation fuer alle migrierten Hochrisiko-Module aktiv.
   - Fix: Neue Konstante `_TABLE_AUGMENT_MODULES` (`kubernetes, proxmox, docker, linux_server, checkmk, opnsense, zabbix`); die Bedingung in `ResponseExtractionMiddleware.post_process` prueft `ctx.agent_name in _TABLE_AUGMENT_MODULES` statt nur Kubernetes.
   - Neuer Helper `_build_table_details` waehlt fuer Kubernetes weiterhin die bespoke Summary-Card, fuer alle anderen den generischen `_format_structured_as_table`-Pfad.
   - Wird die AI-Antwort selbst schon Markdown-Tabellen enthalten, wird kein zweiter Block angehaengt (`_contains_markdown_table`-Guard).
   - Regression: `test_proxmox_short_ai_response_gets_tool_table_appended`, `test_docker_short_ai_response_gets_tool_table_appended`, `test_proxmox_ai_response_with_existing_table_is_not_doubled` sowie `test_non_migrated_module_does_not_get_table_appended` in `backend/tests/test_module_response_formatting.py`.

3. ✅ **Behoben (2026-05-15):** `backend/modules_catalog/zabbix/agent.py` kompatibel mit `BaseAgent`.
   - Fix: `super().__init__(name="zabbix", system_prompt=self.system_prompt, tools=[...])`; das nicht existente `self._register_tools(...)` wurde entfernt. Ungenutzter `from typing import Optional`-Import ebenfalls entfernt.
   - Damit kann Zabbix in Phase 3 sauber instanziiert werden.
   - Regression: `test_zabbix_agent_source_uses_baseagent_signature` (statische Quellpruefung, da der vollstaendige Modulimport `aiosqlite` benoetigt, das im Unit-Test-Env fehlt).

### Verifizierter Backlog

- `PLAN.md` selbst ist fachlich stimmig; die Risiken liegen in der aktuellen Umsetzung und den offenen Migrationsschritten.
- `.claude/knowledge/prompt-inventory.md` existiert und enthaelt das Prompt-Inventar.
- ✅ Es verbleiben aktuell **0 Catalog-Agent-Prompts mit `_t()`-Systemprompts**.
- Zuletzt migrierte Catalog-Agenten:
  - `discord`
  - `fritzbox`
  - `glpi`
  - `licium`
  - `qdrant`
  - `redmine`
  - `tasmota`
  - `wordpress`
- Zuvor migrierte Catalog-Agenten:
  - `confluence`
  - `email`
  - `homeassistant`
  - `ionos`
  - `jira`
  - `mcp_server`
  - `pihole`
  - `synology`
  - `teams`
  - `telegram`
- Zusaetzlich bereinigt:
  - `github`, `gitlab`, `netbox`: alte mehrsprachige `system_prompt = {...}`-Dicts ersetzt.
  - `cisco`, `hpe_ilo`, `lenovo_xclarity`, `microsoft_entra`, `microsoft_intune`,
    `mikrotik`, `netgear`, `nextcloud`, `openproject`, `slack`, `ubiquiti`:
    lokale Antwortsprach-Regeln entfernt und auf englische Canonical Prompts mit
    `BaseAgent(..., tools=[...])` konsolidiert.
- Das Modul-Template ist migriert:
  - `backend/modules_catalog/_template/agent.py` nutzt einen englischen Canonical Prompt.
  - `backend/modules_catalog/_template/README.md` dokumentiert keine `_t()`-Systemprompts mehr fuer neue Module.
- ✅ Die vier zuvor deutsch-only Core-Module sind migriert:
  - `backend/modules/codelab/agent.py`
  - `backend/modules/image_gen/agent.py`
  - `backend/modules/network_analysis/agent.py`
  - `backend/modules/web_search/agent.py`
- ✅ Prompt-Scan fuer Agent-Systemprompts ist sauber:
  - Keine `_t()`-Systemprompts in `backend/modules_catalog/*/agent.py`.
  - Keine mehrsprachigen `system_prompt = {...}`-Dicts in `backend/modules_catalog/*/agent.py`.
  - Keine lokalen "Always respond in the user's language"-Regeln in den geprueften Agenten.
- ✅ Intent-Detection fuer "gib mir JSON" ist umgesetzt.
  - `ResponseExtractionMiddleware` erkennt explizite JSON-Wuensche in `ctx.message`.
  - Bei Tool-only-Fallbacks werden strukturierte Tooldaten dann als JSON-Codeblock gerendert statt als Markdown-Tabelle.
  - Bei kurzen AI-Antworten wird keine Tool-Tabelle angehaengt, wenn der User JSON verlangt.

### Test-Findings

- Ausgefuehrter Review-Check:

```bash
.venv-test/bin/pytest backend/tests/test_language_middleware.py backend/tests/test_module_response_formatting.py backend/tests/test_kubernetes_response_formatting.py -q
```

- Aktueller Stand nach Fixes (2026-05-15): `75 passed`.
- Statische Checks nach Weiterarbeit:
  - `python3 -m py_compile` fuer alle geaenderten Agent- und Middleware-Dateien: bestanden.
  - Voller `ruff check` fuer alle geaenderten Agent- und Middleware-Dateien: bestanden.
- Abgedeckt durch neue Regressionstests:
  - ✅ Toolnamen-Kollisionen zwischen Modulen (`list_services` Kubernetes vs. Linux Server).
  - ✅ Kurze AI-Antworten bei Proxmox und Docker erhalten Markdown-Tabellen.
  - ✅ AI-Antworten mit bereits enthaltener Markdown-Tabelle werden nicht doppelt augmentiert.
  - ✅ Nicht-migrierte Module (z.B. `discord`) lassen kurze AI-Antworten unveraendert.
  - ✅ Zabbix-Agent-Initialisierung (statische Quellpruefung).
  - ✅ Expliziter JSON-Output-Wunsch deaktiviert den Markdown-Table-Fallback.

## Akzeptanzkriterien

- Ein Modul verhaelt sich unabhaengig von `LANGUAGE` gleich, abgesehen von der Antwortsprache.
- Formatregeln sind nicht mehr zwischen deutschen und englischen Prompt-Versionen dupliziert.
- Kubernetes-Statusfragen liefern bei Deutsch und Englisch jeweils Tabellen, keine rohen Listen.
- Neue Modul-Prompts werden nur noch als englische Canonical Prompts angelegt.
- Regressionstests decken mindestens Kubernetes und ein weiteres Infrastrukturmodul ab.
- Tabellen-Hints sind modulqualifiziert, sodass gleichnamige Tools keine falschen Spalten erhalten.
- Migrierte Hochrisiko-Module haengen strukturierte Tooldetails auch dann an, wenn die AI-Antwort zu knapp ist.
- Zabbix initialisiert mit `BaseAgent` korrekt oder bleibt explizit ausserhalb des Migrationsumfangs.
- Explizite JSON-Wuensche liefern strukturierte Tooldaten als JSON-Codeblock statt Markdown-Tabelle.

## Risiken

- Manche Modelle folgen englischen System-Prompts besser als deutschen, aber die Antwortsprache muss trotzdem sauber kontrolliert werden.
- Bestehende Skills oder Memories koennen noch deutschsprachige Instruktionen injizieren.
- Generische Tool-Fallbacks koennen zu breite Tabellen erzeugen, wenn Felder unklar sind.
- Global indizierte Tool-Hints koennen bei gleichnamigen Tools zwischen Modulen kollidieren.
- Tests koennen versehentlich das falsche Verhalten festschreiben, wenn sie kurze AI-Antworten fuer Nicht-Kubernetes-Module unveraendert erwarten.

## Entscheidungen und verbleibende Architekturfragen

- Soll es eine zentrale Prompt-Konstante fuer gemeinsame Formatregeln geben?
- Soll jedes Modul eigene `preferred_table_columns` definieren?
- ✅ Entschieden: Explizites "gib mir JSON" deaktiviert den Markdown-Table-Fallback.
- ✅ Entschieden: Die Catalog-Agent-Prompt-Migration wurde breit umgesetzt statt nur fuer installierte/aktive Module.
- ✅ Entschieden: Der generische Tool-Fallback bleibt auf explizit freigeschaltete Module begrenzt.
- ✅ Entschieden: Zabbix wurde in Phase 3 repariert und ist kein separater Modul-Bug mehr.
