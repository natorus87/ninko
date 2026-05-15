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

## Akzeptanzkriterien

- Ein Modul verhaelt sich unabhaengig von `LANGUAGE` gleich, abgesehen von der Antwortsprache.
- Formatregeln sind nicht mehr zwischen deutschen und englischen Prompt-Versionen dupliziert.
- Kubernetes-Statusfragen liefern bei Deutsch und Englisch jeweils Tabellen, keine rohen Listen.
- Neue Modul-Prompts werden nur noch als englische Canonical Prompts angelegt.
- Regressionstests decken mindestens Kubernetes und ein weiteres Infrastrukturmodul ab.

## Risiken

- Manche Modelle folgen englischen System-Prompts besser als deutschen, aber die Antwortsprache muss trotzdem sauber kontrolliert werden.
- Bestehende Skills oder Memories koennen noch deutschsprachige Instruktionen injizieren.
- Generische Tool-Fallbacks koennen zu breite Tabellen erzeugen, wenn Felder unklar sind.
- Zu aggressive Postprocessing-Regeln koennen explizit angefordertes JSON faelschlich umformatieren.

## Offene Entscheidungen

- Soll es eine zentrale Prompt-Konstante fuer gemeinsame Formatregeln geben?
- Soll jedes Modul eigene `preferred_table_columns` definieren?
- Soll explizites "gib mir JSON" den Markdown-Fallback immer deaktivieren?
- Soll die Migration alle Catalog-Module umfassen oder nur installierte/aktive Module zuerst?
