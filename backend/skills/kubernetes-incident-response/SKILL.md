---
name: kubernetes-incident-response
description: Systematische Diagnose von Kubernetes Pod-Fehlern, CrashLoopBackOff, OOMKilled, ImagePullBackOff, Pending-Pods, Node-Probleme, Deployment-Fehler
modules: [kubernetes]
---

## Diagnose-Ablauf bei Pod-Fehlern

### Schritt 1 – Übersicht
`get_failing_pods` aufrufen → zeigt alle Pods mit Status != Running/Completed.

### Schritt 2 – Pod-Details
`kubectl describe pod <name> -n <namespace>` via CLI → Events-Sektion enthält den eigentlichen Fehlergrund.

### Schritt 3 – Logs
- Aktuelle Logs: `kubectl logs <pod> -n <namespace>`
- Letzte Logs (nach Crash): `kubectl logs <pod> -n <namespace> --previous`

---

## Fehler-Muster & Ursachen

| Status | Häufige Ursache | Erste Maßnahme |
|---|---|---|
| CrashLoopBackOff | App-Fehler, fehlendes ConfigMap/Secret, OOM | `--previous` Logs prüfen |
| OOMKilled | Memory-Limit zu niedrig | `kubectl top pod` → Limit erhöhen |
| ImagePullBackOff | Falscher Image-Tag, Registry nicht erreichbar | `describe` → Image-URL und Registry-Secrets prüfen |
| Pending | Kein Node mit ausreichend Ressourcen | `kubectl describe node` → Kapazität prüfen |
| CreateContainerError | Fehlendes Volume, Secret oder ConfigMap | `describe pod` → Events zeigen fehlendes Objekt |

---

## Schnell-Fixes

**Pod-Neustart (ohne Downtime):**
`rollout_restart` Tool für das betroffene Deployment verwenden.

**Deployment skalieren:**
`scale_deployment` Tool → vorübergehend auf 0, dann zurück auf Ursprungswert.

**Namespace-Events (Überblick):**
`get_recent_events` → zeigt alle Warning-Events der letzten Zeit.

---

## Eskalation
Wenn Problem nach 3 Diagnoseschritten unklar: vollständige Pod-Beschreibung + Logs sammeln und als GLPI-Ticket via `run_pipeline` weitergeben.
