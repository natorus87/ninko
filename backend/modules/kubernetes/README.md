# Ninko Module: Kubernetes (☸)

Dieses Modul integriert Kubernetes-Cluster-Management in Ninko, bietet Health-Checks für Nodes und Pods sowie Funktionen für Skalierung und Rollouts.

## Architektur & Zugriff

Da Ninko primär *IN* einem Kubernetes-Cluster betrieben wird, verwendet das Modul standardmäßig die berechtigte **In-Cluster-Konfiguration** des Pods. Es sind in der Regel keine extra Anmeldedaten erforderlich, sofern der ServiceAccount von Ninko über ausreichende RBAC-Rechte verfügt (siehe `k8s/rbac.yaml`).

Läuft Ninko lokal, wird die lokale `~/.kube/config` verwendet.

## Konfiguration (Connections)

Über das Ninko Backend (`⚙ Einstellungen -> Kubernetes`) können Verbinden angelegt werden. Dies ist primär nützlich, um verschiedene *Kontexte* (z.B. verschiedene Umgebungen wie `prod` oder `staging`) zu definieren:

- **Namespace**: (Optional) Standard-Namespace, falls nicht im Chat genannt.

*Geheimnisse (Vault):* Keine (wird über RBAC/Kubeconfig gelöst).

## Features & Tools

Der AI Orchestrator nutzt folgende Funktionen:
- `get_cluster_status`: Node-Metriken (CPU, Memory, Ready-Status).
- `get_failed_pods`: Sucht nach Pods im Error, CrashLoopBackOff oder OOMKilled Status.
- `get_pod_logs`: Liest die Logs eines fehlerhaften Pods aus.
- `scale_deployment`: Skaliert Deployments (Replicas).
- `restart_deployment`: Führt einen geordneten Rollout-Restart durch.

## Beispiel-Prompt (Chat)

- *"Zeige mir den Status des Produktions-Clusters."*
- *"Gibt es Pods im Namespace `backend`, die crashen?"*
- *"Bitte skaliere das Deployment `frontend` auf 5 Replicas hoch."*
