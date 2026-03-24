---
name: glpi-ticket-workflow
description: GLPI Ticket erstellen Incident Service Request Priorität SLA Kategorie Zuweisung Status Helpdesk
modules: [glpi]
---

## Ticket-Klassifizierung

### Incident vs. Service Request
| Typ | Wann | Priorität-Bereich |
|---|---|---|
| **Incident** | Ausfall, Störung, etwas funktioniert nicht | 3–5 (mittel–sehr hoch) |
| **Service Request** | Neue Anforderung, Information, Zugang | 1–3 (niedrig–mittel) |

### Prioritäts-Matrix (Impact × Urgency)
| | Niedrig | Mittel | Hoch |
|---|---|---|---|
| **Niedrig** | 1 | 2 | 3 |
| **Mittel** | 2 | 3 | 4 |
| **Hoch** | 3 | 4 | 5 |

Werte: 1=Sehr niedrig, 2=Niedrig, 3=Mittel, 4=Hoch, 5=Sehr hoch

### Ticket erstellen
```
create_ticket(title, description, type, priority, category)
  type: 1=Incident, 2=Service Request
  Immer title UND description angeben
```

### Status-Workflow
```
1 = Neu → 2 = In Bearbeitung (Zuweisung) → 3 = In Bearbeitung (Geplant)
→ 4 = Wartend → 5 = Gelöst → 6 = Geschlossen
```

### Tickets suchen & aktualisieren
```
search_tickets(status, priority, category)   → gefilterte Liste
get_ticket(ticket_id)                         → Details
update_ticket(ticket_id, status, solution)    → Status ändern + Lösung hinterlegen
```

### Beste Praxis
- Bei Lösung immer `solution` mit konkreten Schritten angeben
- Kategorie möglichst spezifisch wählen (Hardware > Laptop, Software > Office)
- Bei mehreren betroffenen Nutzern: 1 Ticket für alle (nicht X separate)
- SLA läuft ab Ticket-Erstellung: Priorität 5 = 1h Reaktionszeit
