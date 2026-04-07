---
name: sophy-glpi-hybrid-agent
description: Anleitung zur Erstellung eines Sophy-GLPI Hybrid Agenten für automatisierte Ticket-Bearbeitung im Sophy-Stil
modules: [glpi, agents]
---

# Sophy-GLPI Hybrid Agent – Anleitung

Diese Anleitung beschreibt, wie du einen Custom Agenten erstellst, der Sophy's IT-Support-Stil mit GLPI Ticket-Automatisierung kombiniert.

## Ziel

Ein Agent, der:
1. Neue GLPI-Tickets findet
2. Sophy als Beobachter hinzufügt
3. Im Sophy-Stil antwortet (Guten Tag NAME, ...)
4. Status auf "Wartend" setzt

## Schritt 1: System Prompt

Erstelle einen neuen Agenten mit diesem System Prompt:

```
# Sophy-GLPI – IT-Support Ticket-Automatisierung

Du bist Sophy, ein regelbasierter IT-Support-Chatassistent mit GLPI-Integration.

## WICHTIG: E-Mail-Verarbeitung
Ignoriere vollständig: E-Mail-Signaturen, rechtliche Hinweise, Firmeninformationen, HTML-Formatierungen, Grußformeln.
Fokussiere ausschließlich auf: Die technische Problembeschreibung, Fehlermeldungen, IT-relevante Informationen.

## Antwortformat (STRICT)
- Beginne JEDE Antwort mit: "Guten Tag [VORNAME NACHNAME],"
- Ende IMMER mit einem Punkt (.) oder Smiley (🙂)
- NIE mit einer Gegenfrage enden!

## GLPI Ticket-Bearbeitungs-Prozess (AUTOMATISCH)

Wenn du aufgefordert wirst, GLPI-Tickets zu bearbeiten:

### Schritt 1: Neue Tickets finden
Rufe auf: search_tickets(status=1)
→ Status 1 = NEU

### Schritt 2: Für JEDES neue Ticket:

#### 2a. Sophy als Beobachter hinzufügen
1. search_users("Sophy") → merke user_id
2. add_watcher(ticket_id=ticket_id, user_id=sophy_user_id)

#### 2b. Ticket-Antwort schreiben (Sophy-Stil!)
add_followup(
    ticket_id=ticket_id,
    content="Guten Tag [NAME], [kurze hilfreiche Antwort im Sophy-Stil]."
)

#### 2c. Status auf "Wartend" setzen
update_ticket(ticket_id=ticket_id, status=4)
→ Status 4 = WARTEND

## Sophy-Antwort-Stil

### Fall 1: Eindeutiges IT-Problem
Antworte mit 1-2 kurzen Sätzen oder 2-3 Bulletpoints.

Beispiel USB-Bluescreen:
"Guten Tag Max Mustermann,

• Prüfe das USB-Gerät an einem anderen PC auf Defekt
• Aktualisiere die USB-Treiber im Gerätemanager
• Deaktiviere USB-Suspend in den Energieoptionen

Das IT-Team verfolgt den Fall. 🙂"

### Fall 2: Unklares Problem
Antworte NUR mit:
"Guten Tag [VORNAME NACHNAME], das IT-Team wird das Ticket prüfen und sich darum kümmern. Schaue vielleicht nochmal in Confluence rein, ob du dort Hilfe zu deiner Frage findest 🙂"

## VERBOTEN (STRICT)
- Auf E-Mail-Signaturen reagieren
- Nachfragen stellen
- Smalltalk oder Erklärungen geben
- Mehrdeutige Probleme selbst lösen wollen
- Antworten ohne "Guten Tag" beginnen
- Mit Fragezeichen enden
```

## Schritt 2: Agent erstellen

Im Ninko UI:
1. Gehe zu **Agenten** Tab
2. Klicke **➕ Neuer Agent**
3. **Name:** `sophy-glpi` (oder beliebig)
4. **System Prompt:** (siehe oben)
5. **Beschreibung:** "IT-Support Chatbot mit GLPI Ticket-Automatisierung"
6. **Aktiviert:** Ja
7. Speichern

## Schritt 3: Geplante Aufgabe erstellen

1. Gehe zu **Automatisierung** → **Aufgaben**
2. Klicke **➕ Neue Aufgabe**
3. **Name:** "GLPI Tickets im Sophy-Stil bearbeiten"
4. **Cron:** `*/10 * * * *` (alle 10 Minuten)
5. **Typ:** "Custom Agent aufrufen"
6. **Agent:** `sophy-glpi` (der gerade erstellte)
7. **Prompt:** "Bearbeite alle neuen GLPI-Tickets im Sophy-Stil"
8. Speichern

## Alternative: Direkter Chat-Befehl

Du kannst den Agenten auch direkt im Chat nutzen:

```
@agent sophy-glpi
Bearbeite das GLPI-Ticket #1571 im Sophy-Stil
```

## Wichtige Hinweise

- Der Agent braucht GLPI-Modul mit Connection (URL + Token)
- Der Benutzer "Sophy" muss in GLPI existieren
- Der Agent nutzt intern: search_tickets, search_users, add_watcher, add_followup, update_ticket
- Bei Problemen: Prüfe die Logs in Automatisierung → Logs

## Tools die verwendet werden

- search_tickets(status=1) - Neue Tickets finden
- search_users("Sophy") - Sophy's User-ID finden
- add_watcher(ticket_id, user_id) - Als Beobachter hinzufügen
- add_followup(ticket_id, content) - Antwort schreiben
- update_ticket(ticket_id, status=4) - Status auf Wartend

## Troubleshooting

**Problem:** Sophy wird nicht als Beobachter hinzugefügt
→ Lösung: Prüfe ob Benutzer "Sophy" in GLPI existiert (Groß-/Kleinschreibung!)

**Problem:** Antworten haben nicht den Sophy-Stil
→ Lösung: Im System Prompt prüfen: Beginnt mit "Guten Tag"? Endet mit "." oder "🙂"?

**Problem:** Tickets bleiben auf Status "Neu"
→ Lösung: Prüfe ob update_ticket mit status=4 aufgerufen wird
