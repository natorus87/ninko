# Ninko – Offene Tasks

**Datum**: 2026-05-07
**Letztes Review**: Security Audit + Network Analysis Modul (Mai 2026)

---

## 🔴 Offene Tasks

| # | Task | File | Problem | Aufwand |
|---|------|------|---------|---------|
| 2 | **Erledigt 2026-05-08:** CSP als HTTP-Header in `add_security_headers`-Middleware ([main.py](backend/main.py)). `<meta>`-CSP-Tag aus `index.html` entfernt. `frame-ancestors 'none'` (war `'self'`, aber `<meta>`-CSP ignoriert `frame-ancestors` im Browser → wirkte nie). `unsafe-inline` in `script-src` bleibt als technische Schuld (65+ `onclick`-Handler in app.js); Phase 2: onclick → addEventListener refactoren. | ✅ |
| 21 | **Erledigt 2026-05-08:** `replace_history` ([routes_chat.py](backend/api/routes_chat.py)) begrenzt auf 500 Messages und 32 768 Zeichen pro Content. Body-Typ-Validierung (messages muss Liste, Content muss String sein). | ✅ |

---

## 🟢 Network Analysis Modul (2026-05-07)

**Pfad**: `backend/modules/network_analysis/`
**Tools**: `dns_lookup`, `reverse_dns`, `traceroute`, `ping_host`, `get_network_info`
**Routing**: `netzwerkanalyse`, `dns lookup`, `traceroute`, `whois`, `ip-adresse`

### Safeguard Safe-Keywords
`netzwerkanalyse`, `traceroute`, `tracepath`, `dns lookup`, `ip-adresse`, `server-analyse`, `website-analyse`

### MicroK8s NET_RAW Gotcha
Ping/socket-Tools funktionieren via Socket-Fallback ohne ROOT-Capabilities.

---

## 🟢 Nice-to-have

- MOB-2: `<header role="banner">` für Screenreader
- MOB-3: 375px/480px Breakpoint für kleine Tablets
- MOB-4: Touch-Drag/Swipe für Sidebar
- 17 weitere FE-4/FE-5/Bild-URL-Escapes aus altem Plan

---

## Know-How: Pipeline Anti-Pattern

**Pipeline Parallel Execution funktioniert NICHT für Kontext-Weitergabe**:
- `_build_execution_groups()` gibt bei `[list(range(n))]` ALLE Steps in einer Gruppe parallel
- `step_results` wird aber erst NACH `asyncio.gather()` gefüllt
- Jeder Step sieht `prior_results = {}` → kein Step kommt an Ergebnisse anderer
- **Lösung**: `return [[i] for i in range(n)]` (sequentiell) wenn Kontext fließen muss

---

## 🟠 Core-Agent Routing-Audit (2026-05-08)

**Datei**: `backend/agents/orchestrator.py` (2575 Zeilen)
**Auslöser**: User-Beobachtung „Keyword-Logik fühlt sich unzuverlässig an"

### Die 7 Hauptprobleme

#### 1. Lexikalisches Matching ohne morphologische Toleranz
**Stelle**: [orchestrator.py:1447](backend/agents/orchestrator.py#L1447)
```python
matches = len(re.findall(r"\b" + re.escape(kw_lower) + r"\b", text_lower))
```
- Deutsche Flexion/Synonyme bleiben inkonsistent: `ausführen` matched **nicht** in „auszuführen" oder „Ausführung"
- Manche Flexionsfälle wirken nur zufällig, weil der spätere Substring-Fallback greift: `container` matched in „Containern"/„Containers", aber nicht wegen sauberer Morphologie
- Tippfehler-Toleranz = 0 (außer manuell als Keyword gepflegt, z. B. „promox" in [proxmox/manifest.py:88](backend/modules_catalog/proxmox/manifest.py#L88))
- Kein Stemming, keine Lemmatisierung, keine Fuzzy-Distanz

#### 2. Substring-Fallback (≥7 Zeichen) ist eine versteckte Bombe
**Stelle**: [orchestrator.py:1448-1449](backend/agents/orchestrator.py#L1448-L1449)
```python
if len(kw_compact) >= 7 and matches == 0 and kw_compact in text_compact:
    matches = 1
```
- `entwicklungsumgebung` (Proxmox-Keyword!) matched per Substring-Fallback in „Entwicklungsumgebungen" → falsche Tier-2-Delegation
- `monitoring` matched in „supermonitoringtool" → Zabbix gewinnt unabhängig vom Tool
- Asymmetrisch zur Word-Boundary-Logik: kurze Keywords strikt, lange lax → unintuitiv

#### 3. Compound-Trigger über `\bund\b` ist zu aggressiv
**Stelle**: [orchestrator.py:1488-1489](backend/agents/orchestrator.py#L1488-L1489)
```python
if re.search(r"\bund\b|\band\b", msg_lower):
    return True
```
- Es gibt bereits Guards: mindestens 2 qualifizierte Module und Score-Schwellen reduzieren reine Erklärfrage-False-Positives
- Das verbleibende Risiko liegt bei Anfragen mit zwei klar erkannten Modulen, aber ohne sequentielle Absicht: „Vergleiche Docker und Kubernetes" oder „Erkläre Proxmox und Docker"
- Deutsches „und" ist kein zuverlässiger Multi-Step-Indikator; besser nur explizite Sequenzmuster wie „und dann", „danach", „anschließend"

#### 4. Core-Overrides sind hardcodiert und überschießend
**Stelle**: [orchestrator.py:1512-1530](backend/agents/orchestrator.py#L1512-L1530)
```python
core_patterns = [..., r"\bping\b", r"\buptime\b", r"\bterminal\b", ...]
for pattern in core_patterns:
    if re.search(pattern, msg_lower):
        return None, False  # Komplett aus Modul-Routing raus
```
- „Ping den Proxmox-Server" → `\bping\b` matched → Modul-Routing **übersprungen**
- „Zeig die Docker-Container-Uptime" → `\buptime\b` → Docker-Modul ignoriert
- Liste nicht konfigurierbar, nicht testbar, Blacklist statt Scoring

#### 5. Module-Name-Gewichtung ist ein impliziter Vertrag
**Stelle**: [orchestrator.py:1450-1452](backend/agents/orchestrator.py#L1450-L1452)
```python
weight = 5 if kw_lower in [module_name.lower(), ...] else 1
```
- 5×-Boost greift **nur**, wenn das Modul seinen eigenen Namen in `routing_keywords` listet
- Aktuelle Beispiele ohne Self-Keyword/Boost: `image_gen`, `network_analysis`, `linux_server`, `microsoft_entra`, `microsoft_intune`, `telegram`
- Lautloser Bug-Generator, Modul-Autoren wissen nichts vom Vertrag

#### 6. Keyword-Qualität schwankt extrem zwischen Modulen

| Modul | # Keywords | Auffälligkeit |
|---|---|---|
| codelab | 30+ | Sehr breit, Konfliktpotenzial |
| proxmox | 13 | „entwicklungsumgebung", „hängt", „aufgehangen" — generisch |
| zabbix | 6 | „alert", „trigger", „monitoring" — alle generisch |
| docker | 9 | „pull", „build", „image" — Konflikt mit Git, image_gen |
| web_search | 15 | „web", „news" — kollidiert mit jedem Web-Plugin |

Bei Konflikten warnt [module_registry.py:350-358](backend/core/module_registry.py#L350-L358) zwar, der Gewinner ist aber **arbiträr** (das erste registrierte Modul).
Aktuelle Duplikate u. a.: `image` (image_gen/docker), `graph` (dataviz/zabbix), `monitoring` (checkmk/zabbix), `ticket` (glpi/jira/openproject/redmine), `volume` (docker/kubernetes).

#### 7. History-Fallback ist gedächtnislos
**Stelle**: [orchestrator.py:1541-1553](backend/agents/orchestrator.py#L1541-L1553)
```python
history_text = " ".join([m.get("content", "") for m in chat_history[-3:]])
history_scores = self._get_module_scores(history_text)
```
- Keine Recency-Gewichtung (Turn -3 = Turn -1)
- Keine Rolle-Gewichtung (Assistant-Antwort = User-Eingabe)
- Themenwechsel werden nicht erkannt
- Bei Single-Match aus History: Delegation ohne weitere Validierung

### Strukturelle Mängel

- **2575 Zeilen in einer Datei**: Routing, Tier-4-Planning, Force-Routing, Tool-Execution vermischt
- **Keine Confidence-Propagation**: `_get_module_scores` liefert Integer, der nirgendwohin weitergereicht wird
- **Keine Abstain-Option**: Bei Mehrdeutigkeit kein „Frag den User"-Pfad
- **Tier-Ordnung kaum testbar**: [test_routing.py](backend/test_routing.py) existiert, aber keine Adversarial-Test-Suite

### Verbesserungsvorschläge (Impact / Aufwand)

#### 🔥 Sofort (1-2 Tage, hohes ROI)

| # | Task | Aufwand | Impact |
|---|------|---------|--------|
| R1 | **Erledigt 2026-05-08:** Substring-Fallback (≥7) abgeschafft ([orchestrator.py:1448](backend/agents/orchestrator.py#L1448)) | 30 min | Hoch — entfernt versteckte Mis-Matches |
| R2 | **Erledigt 2026-05-08:** `\bund\b`-Compound-Trigger nur noch bei expliziter Sequenzabsicht (`und dann`, `danach`, `anschließend`); ambige Multi-Modul-Treffer ohne Sequenzintent gehen in den ReAct-Pfad ([orchestrator.py:1488](backend/agents/orchestrator.py#L1488)) | 1 h | Mittel — reduziert Rest-False-Positives bei Vergleichs-/Erklärfragen |
| R3 | **Erledigt 2026-05-08:** Core-Overrides greifen nur noch ohne Modul-Treffer; `ping`, `uptime`, `terminal` sperren andere Modul-Treffer nicht ([orchestrator.py:1512](backend/agents/orchestrator.py#L1512)) | 2 h | Hoch — repariert „Ping Proxmox"/„Docker-Uptime"-Klasse |
| R4 | **Erledigt 2026-05-08:** Keyword-Linter im CI ergänzt; rejectet neue Kurz-Keywords ohne Allowlist, Stopwords und Duplicate-Keywords im selben Manifest | 2 h | Mittel — verhindert Regression |

#### 🟡 Mittelfristig (1 Woche, hohes ROI)

| # | Task | Aufwand | Impact |
|---|------|---------|--------|
| R5 | **Erledigt 2026-05-08:** Module-Name automatisch als Keyword/Alias mit Gewicht 5 in `module_registry.get_routing_map()` ergänzen | 30 min | Mittel — entfernt impliziten Vertrag |
| R6 | **Erledigt 2026-05-08:** Score-basierte Tier-Entscheidung mit Mindestscore und Margin; Multi-Modul-Treffer unterhalb der Confidence-Schwelle gehen in Tier 1/ReAct statt blind zum Top-Modul | 1-2 Tage | Hoch |
| R7 | **Erledigt 2026-05-08:** Projektlokaler Routing-Normalizer für einzelne Keywords ergänzt; deckt konservative Flexionen wie `Containern`/`Containers` und `auszuführen`/`Ausführung` ab, ohne den alten freien Substring-Fallback zurückzubringen | 1 Tag | Hoch — repariert Flexion systematisch |
| R8 | Confidence-Score persistieren + Frontend-Anzeige bei < 70 % | 1 Tag | Mittel |

#### 🔵 Strategisch (2-4 Wochen, transformativ)

| # | Task | Aufwand | Impact |
|---|------|---------|--------|
| R9 | **Erledigt 2026-05-08:** Adversarial-Test-Suite vollständig: Tippfehler, Synonyme, Duplicate-Konflikte, History-Fallback (22 Tests, 26 total). Grenzfall `kubernets`→`kubernetes` via Normalisierung dokumentiert. | 1 Woche | Hoch — verhindert Regression dauerhaft |
| R8 | **Erledigt 2026-05-08:** `_last_routing_confidence` in `KeywordRouter` + `OrchestratorAgent`. `ChatResponse.routing_confidence` (API). Frontend-Badge < 70 %. | 1 Tag | Mittel |
| R10 | **Phasen 1+2 erledigt 2026-05-08:** Routing-Logik in `core/router.py` (`KeywordRouter`-Klasse, 400 Zeilen). `orchestrator.py` von 2666 → 2288 Zeilen (−378). `classify_tier()` gibt `(tier, module, confidence)` zurück; `route()` hält Confidence lokal und setzt `_last_routing_confidence` erst am letzten `return` vor allen await-Punkten → asyncio-Race-Condition behoben. | 1 Woche | Hoch — Testbarkeit, Wartbarkeit |
| R11 | **Erledigt 2026-05-08:** Embedding-basierter Tie-Breaker (`EmbeddingRouter` in `core/embedding_router.py`). Nutzt konfigurierten Embedding-Endpoint (EMBED_MODEL/EMBED_BACKEND, OpenAI-kompatibel) mit TF-IDF-Fallback (keine neuen Abhängigkeiten). Trigger: Keyword-Tie (≥2 Kandidaten, kein klarer Gewinner). Konfigurierbarer Toggle: `ROUTING_EMBEDDING_ENABLED=true`. | 1-2 Wochen | Sehr hoch — Routing-Qualität bei Keyword-Konflikten deutlich besser |
| R12 | **Erledigt 2026-05-08:** A/B-Telemetrie via `RoutingTelemetry` (`core/routing_telemetry.py`). Erkennt Routing-Korrekturen (force_module ≠ letztes Auto-Routing), speichert in Redis (Log 500, Stats-Hash, 20 Korrektur-Beispiele/Modul). Soft-Learning: Korrektur-Beispiele fließen in EmbeddingRouter-TF-IDF ein. Admin-API: `GET/DELETE /api/routing/corrections`. | 1-2 Wochen | Mittel — Daten-getriebene Optimierung |

### Reihenfolge-Empfehlung

**Phase 1** (Quick-Wins, < 1 Tag): R1 ✅ → R5 ✅ → R3 ✅ → R2 ✅
**Phase 2** (Robustheit, < 1 Woche): R9 ✅ → R6 ✅ → R7 ✅ → R4 ✅ → R8 ✅ → R10 Phase 1 ✅ → R10 Phase 2 ✅
**Phase 3** (SOTA, ggf. Q3): R11 ✅ → R12 ✅

**Größter Quick-Win**: R1 + R5 + R3 (~ < 1 Tag, entfernt versteckte Mis-Matches, repariert impliziten Boost-Vertrag und beseitigt Core-Bypass-Probleme)
**Größter strategischer Hebel**: R9 vor R11 — erst messbare Routing-Regressionen definieren, dann Embedding-Routing gegen diese Suite bewerten
