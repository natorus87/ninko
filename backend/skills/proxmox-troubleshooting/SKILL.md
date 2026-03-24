---
name: proxmox-troubleshooting
description: Proxmox VM-Diagnose, Container-Fehler, Storage-Probleme, Cluster-Status, Migration, Backup-Fehler, Node offline
modules: [proxmox]
---

## Proxmox – Diagnose-Ablauf

### VM startet nicht
1. Task-Log prüfen: Proxmox UI → Node → Task History (oder via API `/nodes/{node}/tasks`)
2. Storage verfügbar? → `get_storages` / `df -h` auf dem Node
3. Lock vorhanden? → `qm unlock <vmid>` falls VM locked ist
4. KVM-Log: `/var/log/pve/qemu-server/<vmid>.log`

### Container (LXC) Probleme
- Container startet nicht → AppArmor/cgroup-Konflikte prüfen
- Netzwerk fehlt → Bridge-Konfiguration auf dem Node prüfen (`ip a`)

### Cluster-Status
- `pvecm status` → zeigt Quorum und Node-Status
- Quorum verloren → KEIN Neustart, zuerst Cluster-Admin kontaktieren

### Storage
- Storage voll → VM-Snapshots löschen oder Disk erweitern
- `pvesm status` → Übersicht aller Storage-Pools

### Migration schlägt fehl
- Häufig: Storage nicht auf Ziel-Node verfügbar (shared Storage nötig für Live-Migration)
- Lösung: Offline-Migration nutzen oder Shared Storage einrichten

### Backup-Fehler
- Destination Storage voll → älteste Backups löschen
- Lock-Fehler → `vzdump` läuft noch im Hintergrund, abwarten
