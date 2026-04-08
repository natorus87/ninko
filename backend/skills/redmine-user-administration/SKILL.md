---
name: redmine-user-administration
description: Redmine Benutzeradministration, User sperren, User entsperren, Benutzer deaktivieren, Benutzer aktivieren, Passwort zurücksetzen, User in Gruppe hinzufügen, Gruppenverwaltung
modules: [redmine]
---

# Redmine Benutzeradministration

Dieser Skill beschreibt die Verwaltung von Redmine-Benutzern und -Gruppen.

## Benutzer Status

Redmine-Benutzer haben einen Status:
- **Status 1** = Aktiv (Benutzer kann sich anmelden)
- **Status 3** = Gesperrt/Deaktiviert (Benutzer kann sich NICHT anmelden)

## Benutzer sperren (Deaktivieren)

Wenn ein Benutzer nicht mehr auf Redmine zugreifen soll:

1. Verwende `lock_redmine_user` mit der User-ID
2. Der Benutzer behält alle Daten, kann sich aber nicht mehr anmelden
3. Status wird auf 3 (gesperrt) gesetzt

Beispiel:
- User-ID: 42
- Aktion: lock_redmine_user(user_id="42")

## Benutzer entsperren (Aktivieren)

Wenn ein gesperrter Benutzer wieder Zugriff benötigt:

1. Verwende `unlock_redmine_user` mit der User-ID
2. Der Benutzer kann sich wieder normal anmelden
3. Status wird auf 1 (aktiv) gesetzt

Beispiel:
- User-ID: 42
- Aktion: unlock_redmine_user(user_id="42")

## Passwort zurücksetzen

Wenn ein Benutzer sein Passwort vergessen hat:

1. Verwende `reset_redmine_user_password`
2. Benötigt User-ID und neues Passwort
3. Passwort muss Redmine-Passwortrichtlinien entsprechen

Beispiel:
- reset_redmine_user_password(user_id="42", new_password="NeuesPasswort123!")

## Benutzer in Gruppen verwalten

### Gruppen auflisten
- Verwende `get_redmine_groups` um alle verfügbaren Gruppen zu sehen
- Speichere die Group-ID für spätere Operationen

### Benutzer zu Gruppe hinzufügen
- Verwende `add_redmine_user_to_group(user_id, group_id)`
- Benutzer erhält sofort alle Gruppenberechtigungen

### Benutzer aus Gruppe entfernen
- Verwende `remove_redmine_user_from_group(user_id, group_id)`
- Berechtigungen werden sofort entzogen

## Häufige Szenarien

### Mitarbeiter verlässt das Unternehmen
1. lock_redmine_user - Sofortiger Zugriffsstopp
2. Optional: Passwort zurücksetzen als Sicherheitsmaßnahme
3. Optional: Aus allen Gruppen entfernen

### Mitarbeiter in Urlaub / Karenz
1. lock_redmine_user - Temporäre Deaktivierung
2. Bei Rückkehr: unlock_redmine_user

### Neue Mitarbeiter
1. create_redmine_user - Konto erstellen
2. add_redmine_user_to_group - Zu relevanten Gruppen hinzufügen
3. Optional: Erstes Passwort setzen oder E-Mail-Activation verwenden

## Wichtige Hinweise

- Gesperrte Benutzer behalten alle Daten (Tickets, Time Entries)
- Löschen (delete_redmine_user) ist nur für irreversible Fälle
- Gruppenmitgliedschaften bleiben beim Sperren erhalten
- API-Keys gesperrter Benutzer funktionieren weiterhin (automatische Logins blockiert)
