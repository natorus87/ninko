---
name: smart-alerts
description: Alert-Deduplication für alle Module - Kubernetes Proxmox Linux Docker OPNsense Pi-hole Benachrichtigung Cooldown Remediation
modules: [kubernetes, proxmox, linux, docker, opnsense, pihole, email]
---

# Smart Alerts — Universelle Alert-Deduplication

Best-Practice Patterns für Alert-Deduplication in automatisierten Monitoring-Workflows — modul-agnostisch für Kubernetes, Proxmox, Linux, Docker, OPNsense, Pi-hole und mehr.

## Das Problem

Ohne Deduplication entstehen bei periodischen Health-Checks (z.B. alle 60 Sekunden) hunderte identischer Alerts pro Tag:
- 1440 Emails/Tag für denselben Pod-Failure, VM-Shutdown, oder Disk-Space-Fehler
- ChromaDB voller identischer Incidents
- Alert-Müdigkeit („schon wieder der gleiche Fehler?")

## Die Lösung: Alert-State-Tracking

Verwende die Core-Tools `check_alert_state`, `record_alert` und `resolve_alert` für deterministische Deduplication.

---

## Alert-ID Konvention — Universal-Format

**Format:** `{module}:{resource}:{reason}` (lowercase, normalized)

Generiert via `AlertStateManager.make_id(module, resource, reason)` — Sonderzeichen werden entfernt, alles zu Kleinbuchstaben.

### Module-spezifische Beispiele

#### Kubernetes Pod-Failure

Format: `kubernetes:{namespace}:{deployment}:{reason}`

⚠️ **WICHTIG: Deployment-Level, nicht Pod-Instanz verwenden!**

Pod-Namen enthalten einen ReplicaSet-Hash (`nginx-7d8f9b2c4-x9k3p`) der sich bei jedem Neustart ändert.

```
❌ Falsch: kubernetes:default:nginx-7d8f9b2c4-x9k3p:crashloopbackoff
   → Pod-Name mit Hash ändert sich → neue Alert-ID pro Neustart!

✅ Richtig: kubernetes:default:nginx-deployment:crashloopbackoff
   → Deployment-Name ist stabil → Deduplizierung funktioniert
```

Beispiele:
- `kubernetes:default:nginx-deployment:crashloopbackoff`
- `kubernetes:production:api-gateway:oomkilled`
- `kubernetes:monitoring:prometheus:imagepullbackoff`

#### Proxmox VM Management

Format: `proxmox:vm-{vmid}:{reason}`

Beispiele:
- `proxmox:vm-100:stopped` — VM ist gestoppt
- `proxmox:vm-105:high-cpu` — CPU-Auslastung > 90%
- `proxmox:vm-110:disk-offline` — Disk-Array offline

#### Linux Server Monitoring

Format: `linux:{hostname}:{metric}-{threshold}`

Beispiele:
- `linux:server-prod:disk-usage-90` — Partition >= 90% voll
- `linux:server-prod:memory-high` — RAM >= 85%
- `linux:server-db:cpu-load-high` — Load Average > 4 Kerne
- `linux:server-prod:reboot-required` — System benötigt Reboot

#### Docker Container Management

Format: `docker:{container_name}:{status}`

Beispiele:
- `docker:api-container:exited` — Container unerwartet beendet
- `docker:web-frontend:health-check-failed` — Health-Check failure
- `docker:db-postgres:out-of-memory` — OOM Kill

#### OPNsense Firewall

Format: `opnsense:service-{name}:{status}`

Beispiele:
- `opnsense:service-openvpn:stopped` — OpenVPN Service down
- `opnsense:service-unbound:stopped` — DNS Service down
- `opnsense:service-ntopng:crashed` — Monitoring Service crashed

#### Pi-hole DNS/Ad-Blocking

Format: `pihole:{feature}:{status}`

Beispiele:
- `pihole:gravity:update-failed` — Gravity (Blocklist) Update fehlgeschlagen
- `pihole:dns:not-responding` — DNS antwortet nicht
- `pihole:adblock:lists-invalid` — Blocklisten ungültig

---

## Workflow-Pattern — Universal

Alle Module folgen dem gleichen Pattern:

### 1. Problem-Erkennung → Prüfung → Remediation

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Fehler          │────▶│ check_alert_state│────▶│ Bereits aktiv?  │
│ entdeckt        │     │ (ID generieren)   │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                         │
                              ┌─────────┐                │ Nein
                              │   Ja    │                ▼
                              ▼         │        ┌─────────────────┐
                    ┌───────────────────┘        │ record_alert    │
                    │                           │ mit Cooldown    │
                    ▼                           └─────────────────┘
        ┌─────────────────────┐                          │
        │ Nur last_seen       │                          ▼
        │ aktualisieren       │                 ┌─────────────────┐
        │ (keine Email!)      │                 │ should_notify?  │
        └─────────────────────┘                 └─────────────────┘
                                                         │
                              ┌──────────┐              │
                              │   Ja     │              │ Nein
                              ▼          │              ▼
                    ┌───────────────────┘      ┌─────────────────────┐
                    │                          │ Skip Notification   │
                    ▼                          │ (bereits notifiziert)│
        ┌─────────────────────┐                └─────────────────────┘
        │ Email/Slack/Ticket  │
        │ senden              │
        └─────────────────────┘
        │
        ▼
    ┌─────────────────────┐
    │ Remediation-        │
    │ Versuch starten     │
    │ (optional)          │
    └─────────────────────┘
```

### 2. Recovery-Erkennung → Auto-Resolve

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Health-Check    │────▶│ System läuft      │────▶│ resolve_alert   │
│ wieder OK       │     │ wieder?          │     │                 │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

---

## Cooldown-Zeiten — Empfehlungen

| Severity | Empfohlener Cooldown | Beispiele |
|----------|---------------------|----------|
| **Critical** | 1-4 Stunden | Kubernetes Pod Down, VM Stopped, Disk 95%+ |
| **Warning** | 8-12 Stunden | High CPU/Memory, Service degraded |
| **Info** | 24-48 Stunden | Update available, Minor configuration issue |

---

## Praxis-Beispiele pro Modul

### Kubernetes — Pod Recovery

```python
# Pseudo-Code für einen Kubernetes-Monitoring-Workflow

alert_id = "kubernetes:default:nginx-deployment:crashloopbackoff"

# 1. Prüfe ob Alert bereits bekannt
state = await check_alert_state(alert_id)

if not state["exists"]:
    # Neuer Alert → Versuch Remediation
    await record_alert(alert_id, module="kubernetes", severity="critical",
                       summary="Pod nginx-deployment im CrashLoopBackOff")
    
    # 2. Prüfe ob Notification erlaubt
    result = await record_alert(..., check_cooldown=True, cooldown_hours=4)
    
    if result["should_notify"]:
        # 3. Sende Email/Ticket
        await email.send(to="ops@company.com", 
                        subject="[CRITICAL] Kubernetes Pod Failure",
                        body=f"Alert: {alert_id}")
    
    # 4. Starte Remediation (optional)
    await kubernetes.delete_pods(namespace="default", 
                                 labels={"app": "nginx"})
else:
    # Alert existiert bereits → nur last_seen aktualisieren
    await record_alert(alert_id, ..., check_cooldown=False)
```

### Proxmox — VM Restart

```python
alert_id = "proxmox:vm-100:stopped"

state = await check_alert_state(alert_id)

if not state["exists"]:
    await record_alert(alert_id, module="proxmox", severity="critical",
                       summary="VM 100 (prod-db) gestoppt")
    
    result = await record_alert(..., check_cooldown=True, cooldown_hours=2)
    
    if result["should_notify"]:
        await email.send(to="infra-team@company.com",
                        subject="[ALERT] VM stopped: prod-db")
    
    # Versuche VM neu zu starten
    await proxmox.start_vm(vmid=100)
```

### Linux — Disk Space Alert

```python
alert_id = "linux:server-prod:disk-usage-90"

state = await check_alert_state(alert_id)

if not state["exists"]:
    # Disk kritisch voll (>= 90%)
    await record_alert(alert_id, module="linux", severity="critical",
                       summary="Disk /var/data auf server-prod zu 95% voll")
    
    result = await record_alert(..., check_cooldown=True, cooldown_hours=6)
    
    if result["should_notify"]:
        # Benachrichtige Admin mit Cleanup-Anleitung
        await email.send(to="sysadmin@company.com",
                        subject="[CRITICAL] Disk space low")
    
    # Versuche automatisches Cleanup (optional)
    # await linux.cleanup_old_logs(server="server-prod", days=7)
```

### Docker — Container Health

```python
alert_id = "docker:api-container:exited"

state = await check_alert_state(alert_id)

if not state["exists"]:
    await record_alert(alert_id, module="docker", severity="critical",
                       summary="API-Container unerwartet beendet")
    
    result = await record_alert(..., check_cooldown=True, cooldown_hours=1)
    
    if result["should_notify"]:
        await slack.send(channel="#alerts", 
                        message=f"🚨 Container down: api-container")
    
    # Restart versuchen
    await docker.start_container("api-container")
```

---

## Integration mit Monitor-Agent

Der Monitor-Agent (`backend/agents/monitor_agent.py`) nutzt AlertStateManager **direkt**:

1. Für jedes Modul mit Fehler → generiere `alert_id`
2. Prüfe via `is_active(alert_id)` ob bereits bekannt
3. **Erste Meldung:** `publish_event()` + `store_incident()`
4. **Folge-Zyklen:** nur `last_seen` aktualisieren, kein Event
5. **Recovery:** `resolve_alert()` automatisch aufrufen

→ **Kein LLM-Call im Hot-Path** — nur Dedup-Logik

---

## Wichtige Entscheidungen

### Alert-ID Granularität

**Modul/Ressource-Level (Standard):**
- `kubernetes:default:nginx-deployment:crashloopbackoff`
- Ganzer Deployment/Service = ein Alert
- Alle Instanzen-Fehler derselbe Alert
- Ein Problem = eine Notification (keine Spam)

**Mit Failure-Reason Distinktion:**
- `kubernetes:default:nginx-deployment:crashloopbackoff` (separate Alert)
- `kubernetes:default:nginx-deployment:oomkilled` (separate Alert)
- Macht Sinn wenn unterschiedliche Gründe unterschiedliche Aktionen brauchen

### Cooldown vs. Remediation

**Cooldown** = Notification Throttling (max 1 Email pro 4h)
**Remediation** = Automatische Reparatur (läuft bei jedem Fehler)

Diese sind **unabhängig**:
- Remediation läuft bei jedem Fehler-Zyklus
- Nur die Benachrichtigung wird durch Cooldown begrenzt

---

## Best Practices

✅ **Tun:**
- Deterministische Alert-IDs (immer gleich für gleiches Problem)
- Angemessene Cooldowns (abhängig von Severity)
- Modul/Ressource-spezifische IDs für gutes Tracking
- Remediation parallel zu Notification

❌ **Nicht tun:**
- Alert-IDs mit Timestamps (verhindert Deduplication)
- Cooldown zu kurz (< 1 Stunde = Spam)
- Remediation blockieren durch Notification-Logik
- Pod-Namen / Instance-IDs in Alert-IDs (ändern sich!)

---

## Verwandte Skills

- **kubernetes-incident-response** – Kubernetes-spezifische Incident-Response
- **workflow-builder** – Erstellung komplexer Remediation-Pipelines
- **email-alert-templates** – Formatierung von Alert-Emails
