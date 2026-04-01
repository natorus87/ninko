---
name: agent-builder
description: Agenten erstellen, neuen Agenten bauen, agent erstellen, agent anlegen, spezialisierter agent, custom agent, agent für, agent builder, dynamischer agent, agent konfigurieren, agent optimieren, agent verbessern
modules: []
---

## Agent Builder – Vollständige Expertise

Dieses Skill gibt Ninko alle Werkzeuge und Kenntnisse, um hochwertige, spezialisierte Agenten zu bauen.

---

## Schritt 1 – Use-Case klären (Interview)

Bevor `create_custom_agent` aufgerufen wird, immer diese Fragen klären (sofern nicht bereits beantwortet):

1. **Zweck**: Was soll der Agent konkret tun? (1–2 Sätze)
2. **Auslöser**: Wann/wie wird er aktiviert? (Auf Anfrage, regelmäßig, ereignisgesteuert?)
3. **Module**: Welche Systeme/Module braucht er? (Kubernetes, Pi-hole, HomeAssistant, Telegram usw.)
4. **Output**: Was soll zurückgemeldet werden und in welchem Format?
5. **Kritikalität**: Darf er autonom handeln oder immer Bestätigung einholen?

Sind alle 5 Punkte klar → Agent bauen. Fehlt ein Punkt → kurz nachfragen.

---

## Schritt 2 – System-Prompt Qualitätsstandards

### Pflicht-Bausteine (immer einbauen)

```
Du bist [NAME] – [KURZE ROLLENBESCHREIBUNG].

## Aufgaben
- [Konkrete Aufgabe 1]
- [Konkrete Aufgabe 2]
- [Konkrete Aufgabe 3]

## Arbeitsweise
- Erst diagnostizieren, dann handeln
- Ergebnisse strukturiert zurückgeben (Markdown-Tabellen/Listen)
- Bei Unsicherheit Rückfrage stellen, nicht raten

## Kritische Aktionen
- [Destruktive Aktion X] immer bestätigen lassen
- Keine Massenoperationen ohne explizite Freigabe

## Eskalation
- Aufgabe außerhalb meines Scopes → an Ninko zurückgeben
- Fehler → Fehlerbeschreibung + Kontext melden
```

### Do's
- **Spezifisch**: "Analysiere Kubernetes-Pod-Logs auf OOMKilled und CrashLoopBackOff" statt "schaue dir Logs an"
- **Handlungsorientiert**: Beschreibt WAS der Agent TUT, nicht was er ist
- **Scope-begrenzt**: Explizit nennen was der Agent NICHT macht
- **Tool-aware**: Module/Tools die genutzt werden sollen namentlich erwähnen

### Don'ts
- Keine generischen Prompts ("Du bist ein hilfreicher Assistent")
- Kein unbegrenzter Scope ("Mache alles was der User will")
- Keine fehlende Eskalationsregel
- Kein fehlender Bestätigungsmechanismus für destruktive Aktionen

---

## Schritt 3 – Kategorien & Muster

### IT-Operations / Infrastruktur
```
Fokus: System-Health, Incidents, Ressourcen-Monitoring
Module: kubernetes, linux_server, docker, proxmox
Arbeitsweise: Diagnose-first, dann Aktion
Bestätigung: Neustarts, Skalierung, Config-Änderungen
```

### Monitoring & Alerting
```
Fokus: Schwellwert-Überwachung, Trend-Analyse, Anomalie-Erkennung
Module: checkmk, kubernetes, homeassistant
Arbeitsweise: Regelmäßige Checks, proaktive Meldungen
Output: Strukturierte Berichte mit Status-Symbolen (✅ ⚠️ ❌)
```

### Security & Compliance
```
Fokus: Port-Scans, Log-Analyse auf Angriffsmuster, Config-Audits
Module: opnsense, pihole, linux_server
Bestätigung: ALLE Änderungen an Firewall/ACLs
Keine autonomen Block-/Allow-Aktionen
```

### Helpdesk / Support
```
Fokus: Ticket-Verwaltung, Erstdiagnose, Eskalation
Module: glpi
Ton: Professionell, lösungsorientiert
Output: Immer mit Ticket-Nummer referenzieren
```

### Automation & CI/CD
```
Fokus: Deploy-Pipelines, Rollbacks, Build-Status
Module: kubernetes, docker
Bestätigung: Production-Deployments immer bestätigen
Rollback-Strategie immer mitdenken
```

### Kommunikation & Reporting
```
Fokus: Berichte erstellen, Benachrichtigungen senden
Module: telegram, email, teams
Format: Klare Struktur, kein technischer Jargon für Endnutzer
```

---

## Schritt 4 – Tool-Auswahl für Dynamic Agents

Dynamic Agents haben 4 Basis-Tools:
- `execute_cli_command` – Lokale Systembefehle
- `call_module_agent` – Module delegieren (z.B. `call_module_agent("kubernetes", "...")`)
- `recall_memory` – Langzeitgedächtnis abfragen
- `remember_fact` – Fakten persistent speichern

**Modul-Delegation im System-Prompt erklären:**
```
Für Kubernetes-Abfragen: call_module_agent("kubernetes", "<aufgabe>") aufrufen
Für Benachrichtigungen: call_module_agent("telegram", "Sende: <nachricht>")
```

---

## Schritt 5 – Anti-Patterns & häufige Fehler

| Anti-Pattern | Problem | Lösung |
|---|---|---|
| Zu weiter Scope | Agent versucht alles, ist in nichts gut | Scope auf 1–2 Kernaufgaben begrenzen |
| Fehlende Eskalation | Agent hängt bei unbekannten Fällen | Immer "→ an Ninko zurückgeben" hinzufügen |
| Kein Bestätigungs-Gate | Destruktive Aktionen ohne Rückfrage | "immer bestätigen lassen" für Delete/Reset |
| Generischer Name | "Mein Agent", "Agent 1" | Name = Funktion, z.B. "K8s-Log-Analyst" |
| Fehlende Tool-Hints | Agent weiß nicht welche Module existieren | Module explizit im System-Prompt nennen |
| Zu langer Prompt | >800 Zeichen, verschnörkelt | Kompakt, bullet-point orientiert |

---

## Schritt 6 – Qualitäts-Checkliste vor `create_custom_agent`

- [ ] Name: ≤5 Wörter, beschreibt Funktion eindeutig
- [ ] Description: 1 klarer Satz ("Was macht er konkret")
- [ ] System-Prompt: Enthält Aufgaben, Arbeitsweise, Eskalation
- [ ] Bestätigung: Destruktive Aktionen sind gegattet
- [ ] Module: Relevante Module im Prompt genannt
- [ ] Scope: Explizit begrenzt (was er NICHT macht)

Alle Punkte erfüllt → `create_custom_agent(name, system_prompt, description)` aufrufen.
