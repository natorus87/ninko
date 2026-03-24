---
name: fritzbox-network-diagnostics
description: FritzBox Netzwerk-Diagnose, WLAN-Probleme, Portweiterleitung, Verbindungsabbrüche, DNS, Reconnect, IP-Adressen
modules: [fritzbox]
---

## Diagnose-Ablauf bei Netzwerkproblemen

### 1. Verbindungsstatus prüfen
- Zuerst `get_network_status()` aufrufen → liefert WAN-IP, Uptime, Verbindungstyp
- Bei Uptime < 5 Min: kürzlicher Reconnect → Logs prüfen

### 2. WLAN-Probleme
| Symptom | Tool | Maßnahme |
|---|---|---|
| Gerät nicht sichtbar | `get_wlan_devices()` | SSID/Passwort prüfen |
| Langsame Verbindung | `get_wlan_devices()` | Kanal/Frequenz in Fritz-UI prüfen |
| Gerät getrennt | `get_wlan_devices()` | MAC-Filter prüfen |

### 3. Portweiterleitung
- `list_port_forwardings()` → aktive Regeln anzeigen
- Neue Regel: `add_port_forwarding(internal_ip, internal_port, external_port, protocol)`
- Protokoll immer explizit angeben: `TCP`, `UDP`, oder beide separat

### 4. Reconnect / IP-Wechsel
- `reconnect()` erzwingt neuen IP-Handshake beim Provider
- Nach Reconnect ~30s warten bis neue WAN-IP stabil
- Dyn-DNS Dienste aktualisieren sich meist automatisch

### 5. Häufige Fehler
| Fehler | Ursache | Fix |
|---|---|---|
| `ConnectionError` | FritzBox nicht erreichbar | Host/Passwort prüfen |
| `401 Unauthorized` | Falsches Passwort | FRITZ!Box-UI → System → Kennwörter |
| Port bereits belegt | Doppelte Weiterleitung | Bestehende Regel löschen |
| `upnp disabled` | UPnP deaktiviert | FRITZ!Box-UI → Heimnetz → Netzwerk → UPnP |

### Reihenfolge bei Diagnose
1. `get_network_status()` → Grundstatus
2. `get_wlan_devices()` → verbundene Geräte
3. `list_port_forwardings()` → aktive Regeln
4. Erst dann gezielt handeln
