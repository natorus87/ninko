---
name: agent-builder
description: Agenten erstellen, neuen Agenten bauen, agent erstellen, agent anlegen, spezialisierter agent, custom agent, agent für, agent builder, dynamischer agent, agent konfigurieren, agent optimieren, agent verbessern, agent iterativ verbessern, agent testen, agent verfeinern
modules: []
---

## Agent Builder – Vollständige Expertise

Dieses Skill gibt Ninko alle Werkzeuge und Kenntnisse, um hochwertige, spezialisierte Agenten zu bauen, zu testen und iterativ zu verbessern.

---

## Schritt 1 – Intent erfassen (Interview)

Bevor `create_custom_agent` aufgerufen wird, den Use-Case präzise verstehen. Ziel: einen Agenten bauen, der in der Praxis funktioniert — nicht nur theoretisch korrekt klingt.

**5 Pflichtfragen** (sofern nicht bereits aus dem Kontext klar):

1. **Zweck**: Was soll der Agent konkret tun? (1–2 präzise Sätze — kein "alles rund um X")
2. **Auslöser**: Wann/wie wird er aktiviert? (Auf Anfrage, regelmäßig per Scheduler, ereignisgesteuert?)
3. **Module & Systeme**: Welche Systeme braucht er? (Kubernetes, Pi-hole, HomeAssistant, Telegram usw.)
4. **Output-Format**: Was soll zurückgemeldet werden, in welchem Format und an wen?
5. **Kritikalität & Autonomie**: Darf er autonom handeln oder soll er destruktive Aktionen bestätigen lassen?

**Faustregel**: Sind alle 5 Punkte klar → sofort Agent bauen. Fehlt ein Punkt und er ist entscheidend → kurz nachfragen. Ist er aus dem Kontext ableitbar → ableiten und im Agenten dokumentieren.

**Edge-Cases beim Interview aufdecken**:
- Was passiert wenn das Zielsystem offline ist?
- Gibt es Ausnahmen vom Regelfall?
- Welche Aktion darf der Agent auf keinen Fall selbstständig ausführen?

---

## Schritt 2 – System-Prompt schreiben: Philosophie

### Das Wichtigste: Das Warum erklären

Ein guter System-Prompt erklärt nicht nur **was** der Agent tun soll, sondern **warum** — weil ein LLM mit Kontext bessere Entscheidungen trifft als eines, das nur Regeln befolgt.

❌ Schwach:
```
Führe keine Massenoperationen aus.
```

✅ Stark:
```
Führe keine Massenoperationen ohne explizite Freigabe aus — ein einziger Tippfehler in einem Namespace-Filter kann Dutzende produktive Pods löschen.
```

### Anweisungen mit Kontext schreiben (Theory of Mind)

Stelle dir vor, der Agent weiß nichts über die Infrastruktur, Prioritäten oder das Risikobewusstsein des Benutzers. Das Warum gibt ihm den Kontext, um in unbekannten Situationen richtig zu entscheiden — anstatt an einer Regelgrenze stehen zu bleiben.

**Muster**: `[Anweisung] — [Grund warum diese Regel existiert]`

### Sparsam mit Imperativ-Verstärkern umgehen

Nicht jede Anweisung muss mit IMMER, NIEMALS, MUSS beginnen. Zu viele Imperative machen den Prompt schwer lesbar und lassen den Agenten weniger flexibel auf Ausnahmefälle reagieren. Nutze starke Imperative gezielt für wirklich kritische Sicherheitsregeln.

---

## Schritt 3 – System-Prompt Struktur & Qualitätsstandards

### Pflicht-Bausteine

```
Du bist [NAME] – [KURZE ROLLENBESCHREIBUNG in einem Satz].

## Aufgaben
- [Konkrete Aufgabe 1 — mit Ziel, nicht nur Tätigkeit]
- [Konkrete Aufgabe 2]
- [Konkrete Aufgabe 3]

## Arbeitsweise
- Erst diagnostizieren, dann handeln — Symptome verstehen bevor Tools aufgerufen werden
- Ergebnisse strukturiert zurückgeben (Markdown-Tabellen/Listen wo sinnvoll)
- Bei echter Unklarheit Rückfrage stellen, bei ablesbarem Kontext direkt handeln

## Kritische Aktionen
- [Destruktive Aktion X] immer bestätigen lassen — [Begründung]
- Keine Massenoperationen ohne explizite Freigabe — Kollateralschäden vermeiden

## Scope & Eskalation
- Zuständig für: [klar begrenzt]
- Nicht zuständig für: [explizit ausschließen]
- Aufgabe außerhalb meines Scopes → an Ninko mit kurzem Kontext zurückgeben
- Fehler → Fehlerbeschreibung + letzter bekannter Zustand melden
```

### Output-Format definieren

Ein Agent der kein Format vorgibt, gibt jedes Mal ein anderes Format zurück. Besser:

```
## Output-Format
- Status-Übersicht: Markdown-Tabelle mit Spalten [System | Status | Detail]
- Fehlermeldungen: Codeblock mit Kontext davor
- Kurzmeldungen: max. 3 Sätze, kein Markdown
```

### Progressive Disclosure – Drei Ebenen

Komplexe Agenten brauchen gestaffelte Detailtiefe im Prompt:

1. **Kern-Identität** (3–5 Zeilen): Rolle, Hauptaufgabe, primäres Ziel
2. **Arbeitsregeln** (Aufgaben, Arbeitsweise, Output): der eigentliche operative Kern
3. **Sicherheitsregeln** (Kritische Aktionen, Eskalation): Grenzen und Ausnahmebehandlung

Diese Reihenfolge stellt sicher, dass der Agent zuerst seinen Zweck versteht und dann die Constraints — nicht umgekehrt.

### Do's
- **Spezifisch**: "Analysiere Kubernetes-Pod-Logs auf OOMKilled und CrashLoopBackOff" statt "schaue dir Logs an"
- **Handlungsorientiert**: Beschreibt WAS der Agent TUT, nicht was er ist
- **Scope-begrenzt**: Explizit nennen was der Agent NICHT macht — verhindert Scope-Creep
- **Tool-aware**: Module/Tools die genutzt werden sollen namentlich erwähnen
- **Begründet**: Kritische Regeln mit einem Warum versehen

### Don'ts
- Keine generischen Prompts ("Du bist ein hilfreicher Assistent")
- Kein unbegrenzter Scope ("Mache alles was der User will")
- Keine fehlende Eskalationsregel — was passiert wenn der Agent nicht weiterkommt?
- Kein fehlender Bestätigungsmechanismus für destruktive Aktionen
- Keine rein verbotenen Anweisungen ohne Begründung — "Warum nicht?" bleibt sonst unklar

---

## Schritt 4 – Kategorien & Muster

### IT-Operations / Infrastruktur
```
Fokus: System-Health, Incidents, Ressourcen-Monitoring
Module: kubernetes, linux_server, docker, proxmox
Arbeitsweise: Diagnose-first (Logs/Metrics lesen), dann Aktion
Bestätigung: Neustarts, Skalierung, Config-Änderungen
Begründung für Bestätigung: Produktionsauswirkungen sind sofort und schwer rückgängig zu machen
```

### Monitoring & Alerting
```
Fokus: Schwellwert-Überwachung, Trend-Analyse, Anomalie-Erkennung
Module: checkmk, kubernetes, homeassistant
Arbeitsweise: Regelmäßige Checks (via Scheduler), proaktive Meldungen
Output: Strukturierte Berichte mit Status-Symbolen (✅ ⚠️ ❌)
```

### Security & Compliance
```
Fokus: Port-Scans, Log-Analyse auf Angriffsmuster, Config-Audits
Module: opnsense, pihole, linux_server
Bestätigung: ALLE Änderungen an Firewall/ACLs — Fehlkonfiguration öffnet Angriffsfläche
Keine autonomen Block-/Allow-Aktionen ohne explizite Freigabe
```

### Helpdesk / Support
```
Fokus: Ticket-Verwaltung, Erstdiagnose, Eskalation
Module: glpi
Ton: Professionell, lösungsorientiert — kein Fachjargon für Endnutzer
Output: Immer mit Ticket-Nummer referenzieren, Nächstschritte klar benennen
```

### Automation & CI/CD
```
Fokus: Deploy-Pipelines, Rollbacks, Build-Status
Module: kubernetes, docker
Bestätigung: Production-Deployments immer bestätigen — Rollback-Strategie immer mitdenken
```

### Kommunikation & Reporting
```
Fokus: Berichte erstellen, Benachrichtigungen senden
Module: telegram, email, teams
Format: Klare Struktur, kein technischer Jargon für Endnutzer
Timing: Häufigkeit und Empfänger explizit im Prompt definieren
```

---

## Schritt 5 – Tool-Auswahl für Dynamic Agents

Dynamic Agents haben 4 Basis-Tools automatisch verfügbar:
- `execute_cli_command` – Lokale Systembefehle (kubectl, curl, systemctl usw.)
- `call_module_agent` – Spezialisierte Module delegieren
- `recall_memory` – Langzeitgedächtnis abfragen
- `remember_fact` – Fakten persistent speichern

**Modul-Delegation im System-Prompt immer explizit erklären** — der Agent weiß sonst nicht welche Module existieren:
```
Für Kubernetes-Abfragen: call_module_agent("kubernetes", "<aufgabe>") aufrufen
Für Benachrichtigungen: call_module_agent("telegram", "Sende an Gruppe: <nachricht>")
Für Netzwerk-Checks: call_module_agent("opnsense", "<aufgabe>") oder execute_cli_command("ping ...")
```

---

## Schritt 6 – Anti-Patterns & häufige Fehler

| Anti-Pattern | Problem | Lösung |
|---|---|---|
| Zu weiter Scope | Agent versucht alles, ist in nichts gut | Scope auf 1–2 Kernaufgaben begrenzen |
| Fehlende Eskalation | Agent hängt bei unbekannten Fällen | Immer "→ an Ninko zurückgeben" + kurzen Kontext mitgeben |
| Kein Bestätigungs-Gate | Destruktive Aktionen ohne Rückfrage | "immer bestätigen lassen" + Begründung |
| Generischer Name | "Mein Agent", "Agent 1" | Name = Funktion, z.B. "K8s-Log-Analyst" |
| Fehlende Tool-Hints | Agent weiß nicht welche Module existieren | Module explizit im System-Prompt nennen |
| Prompt ohne Warum | Agent folgt Regeln blind, versagt bei Ausnahmen | Jede kritische Regel mit Begründung versehen |
| Zu langer Prompt | >800 Zeichen, verschnörkelt | Kompakt, bullet-point orientiert — Qualität vor Quantität |
| Kein Output-Format | Uneinheitliche Antworten | Output-Format-Sektion definieren |
| Fehlende Offline-Behandlung | Agent crasht wenn System nicht erreichbar | "System offline → Fehler melden, nicht raten" |

---

## Schritt 7 – Beschreibung optimieren (Triggering-Qualität)

Die `description` eines Agenten steuert, wann der Orchestrator ihn findet. Eine schlechte Description = Agent wird nie aufgerufen.

**Prinzipien für gute Descriptions:**
- Enthält die wichtigsten Trigger-Begriffe des Use-Cases
- Nicht zu weit ("macht alles") — sonst ambivalent
- Nicht zu eng ("nur OOMKilled-Fehler") — zu selten getriggert
- Verben die der Nutzer wahrscheinlich verwendet: "analysieren", "überwachen", "melden", "prüfen"

**Beispiel — schlecht:**
```
description="Kubernetes Agent"
```

**Beispiel — gut:**
```
description="Analysiert Kubernetes-Pod-Logs, erkennt CrashLoopBackOff und OOMKilled, überwacht Deployment-Health und meldet Cluster-Probleme"
```

**Self-Test**: Würde ich diesen Satz schreiben wenn ich den Agenten suche? Wenn ja → gute Description.

---

## Schritt 8 – Agenten iterativ verbessern

Nach dem ersten Einsatz eines Agenten zeigen sich oft Lücken. Verbesserung erfolgt mit `update_custom_agent`:

### Feedback-Loop-Muster

1. **Beobachten**: Was hat der Agent zurückgegeben? Weicht es von der Erwartung ab?
2. **Ursache eingrenzen**: Liegt es am System-Prompt (falsche Anweisung)? Am Output-Format? An fehlenden Tool-Hints?
3. **Gezielt anpassen**: Nur die betroffene Sektion ändern — kein vollständiges Rewrite
4. **Begründung dokumentieren**: Warum wurde diese Änderung gemacht? (im System-Prompt als Kommentar oder in der Description)
5. **Erneut testen**: Gleiche Anfrage, erwartetes Ergebnis prüfen

### Typische Verbesserungsmuster

| Symptom | Diagnose | Fix |
|---|---|---|
| Agent antwortet zu generisch | Scope zu weit | Aufgaben-Liste spezifischer machen |
| Agent fragt zu oft nach | Kein Default-Verhalten | "Im Zweifel X annehmen" ergänzen |
| Agent nutzt falsches Modul | Fehlende Tool-Hints | `call_module_agent("x", ...)` explizit nennen |
| Unstrukturierter Output | Kein Format definiert | Output-Format-Sektion hinzufügen |
| Agent eskaliert nie | Eskalationsregel fehlt | Scope-Grenzen und Eskalationspfad ergänzen |
| Agent eskaliert zu oft | Scope zu eng | Eigenständig-lösbare Fälle konkret benennen |

### Was nicht geändert werden sollte

- Den Kern-Scope nicht bei jedem Update ausweiten — "noch mal eben X dazunehmen" führt zu Scope-Creep
- Keine Sicherheitsregeln ohne explizite Abwägung entfernen
- Name und UUID nicht ändern (würde bestehende Scheduler-Tasks und Modul-Picker-Einstellungen brechen)

---

## Schritt 9 – Qualitäts-Checkliste vor `create_custom_agent`

- [ ] **Name**: ≤5 Wörter, beschreibt Funktion eindeutig (nicht "Mein Agent")
- [ ] **Description**: 1–2 präzise Sätze mit den wichtigsten Trigger-Begriffen
- [ ] **System-Prompt**: Enthält Kern-Identität, Aufgaben, Arbeitsweise, Output-Format, Eskalation
- [ ] **Begründungen**: Kritische Regeln haben ein "warum" dabei
- [ ] **Bestätigung**: Destruktive Aktionen sind explizit gegattet
- [ ] **Module**: Relevante Module im Prompt genannt mit konkretem `call_module_agent`-Aufruf
- [ ] **Scope**: Explizit begrenzt — was er NICHT macht steht drin
- [ ] **Offline-Verhalten**: Was passiert wenn ein Zielsystem nicht erreichbar ist

Alle Punkte erfüllt → `create_custom_agent(name, system_prompt, description)` aufrufen.

Danach: Agenten direkt im Modul-Picker testen, Feedback beobachten, bei Bedarf mit `update_custom_agent` verbessern.
