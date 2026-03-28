# Ninko Module: FritzBox (📶)

Dieses Modul fügt Support für AVM FRITZ!Box Router hinzu. Es nutzt das TR-064 Protokoll, um Einstellungen abzufragen und das Heim-/Firmennetzwerk zu steuern.

## Konfiguration (Connections)

Über das Ninko Backend (`⚙ Einstellungen -> FritzBox`) können Verbindungen zu deinem Router verwaltet werden.

### Benötigte Felder
- **Host**: Die IP-Adresse oder der Hostname deiner FRITZ!Box (z.B. `192.168.178.1`, `fritz.box`).
- **User**: (Optional, aber empfohlen) Der in der FritzBox angelegte Systembenutzer (z.B. `admin`). Falls es auf der Box keinen Usernamen, sondern nur ein Passwort gibt, kann dieses Feld leer bleiben oder der Platzhalter der Fritzbox (meist `dslf-config`) verwendet werden.

### Geheimnisse (Vault)
- **Password** (`FRITZBOX_PASSWORD`): Das Login-Passwort für die Web-Oberfläche bzw. den User.

*Hinweis*: Für das Modul muss in der FRITZ!Box die Option "Zugriff für Anwendungen zulassen" aktiviert sein (Heimnetz -> Netzwerk -> Netzwerkeinstellungen).

## Features & Tools

Der AI Orchestrator nutzt folgende intelligente Tools (basierend auf `fritzconnection`):
- `get_fritz_wan_status`: Prüft die bestehende Internetverbindung, Uptime und ermittelt die **öffentliche, externe IP-Adresse**.
- `get_fritz_bandwidth`: Ruft die aktuelle Up- and Downloadgeschwindigkeit der Verbindung ab.
- `get_fritz_wlan_status` / `set_fritz_guest_wlan`: Prüft den WLAN-Zustand und aktiviert/deaktiviert das Gästenetz (inkl. Option zur sofortigen Neu-Vergabe eines Gast-WLAN-Passworts).
- `get_fritz_devices`: Listet im LAN/WLAN angemeldete Geräte auf (MAC, IP, aktiv/inaktiv).
- Smart Home (DECT) Steuerung: `get_smart_home_devices`, `set_smart_socket`.

## Routing Erkennung
Das System ist "fehlertolerant" und erkennt Anfragen auch an alternative Schreibweisen wie "Fritz!Box", "ipadresse" oder "fritz-box".

## Beispiel-Prompt (Chat)

- *"Wie ist meine externe IP-Adresse?"*
- *"Schalte das Gast-WLAN der FritzBox für meine Besucher ein."*
- *"Ist die Smart-Steckdose im Wohnzimmer noch an?"*
- *"Welche Geräte sind gerade online gemeldet?"*
