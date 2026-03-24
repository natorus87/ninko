# Kumio Module: Proxmox (🖥)

Dieses Modul ermöglicht die Verwaltung von **Proxmox Virtual Environment (PVE)** Nodes, Virtuellen Maschinen (VMs) und LXC-Containern.

## Architektur & Zugriff

Das Modul greift über die offizielle Proxmox REST API auf deinen Cluster oder Node zu. Dafür wird ein dediziertes API-Token benötigt.

## Konfiguration (Connections)

Über das Kumio Backend (`⚙ Einstellungen -> Proxmox`) können Verbindungen zu verschiedenen Proxmox-Umgebungen (z.B. `homelab` oder `prod-cluster`) angelegt werden.

### Benötigte Felder
- **Host**: IP-Adresse oder FQDN deines Proxmox-Servers (ohne `https://` und Port, z.B. `192.168.1.100`).
- **User**: Der Proxmox-Benutzer inklusive Realm (z.B. `root@pam`).
- **Token ID**: Die ID des API-Tokens (z.B. `kumio` aus `root@pam!kumio`).

### Geheimnisse (Vault)
- **Token Secret** (`PROXMOX_TOKEN_SECRET`): Das generierte API-Token Secret. Dieses wird sicher in HashiCorp Vault (oder der verschlüsselten lokalen SQLite-DB) gespeichert und ist nach dem Speichern nicht mehr im Klartext abrufbar.

## API-Token in Proxmox erstellen
1. Logge dich in die Proxmox Web-GUI ein.
2. Navigiere zu **Datacenter -> Permissions -> API Tokens**.
3. Klicke auf **Add** und wähle den User aus (z.B. `root@pam`). Trage als Token ID `kumio` ein.
4. Hebe den Haken bei "Privilege Separation" auf (für volle Rechte) oder weise dem Token stattdessen explizite Rollen wie `PVEVMAdmin` zu.
5. Kopiere das angezeigte "Secret" sicher heraus. Es wird nur ein Mal angezeigt.

## Features & Tools

Der AI Orchestrator nutzt folgende Funktionen:
- `get_cluster_status`: Zusammenfassung aller Nodes und deren Ressourcen.
- `list_vms`: Listet alle VMs und Container eines spezifischen Nodes auf.
- `get_vm_status`: Detaillierter Status (CPU, RAM, Uptime) einer spezifischen VM.
- `start_vm` / `stop_vm` / `reset_vm`: Power-Management-Aktionen.
- `get_recent_tasks`: Zeigt die letzten PVE-Aufgaben und Logs an.

## Beispiel-Prompt (Chat)

- *"Zeige mir alle VMs auf dem Node `pve-01`."*
- *"Starte die VM 105."*
- *"Die VM 200 hängt – kannst du sie hart neustarten (reset)?"*
