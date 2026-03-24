# Contributing to Kumio

## Neues Modul beitragen

Die einfachste Form des Beitrags ist ein neues Modul. Jedes Modul ist vollständig eigenständig unter `backend/modules/<name>/` — der Core-Code wird nicht angefasst.

Aufbau: `manifest.py`, `agent.py`, `tools.py`, `routes.py`, `frontend/tab.html`, `frontend/tab.js`, `__init__.py`.

Details und Beispiel: [README.md → Eigenes Modul entwickeln](README.md#eigenes-modul-entwickeln)

## Bugs melden

Bitte ein [Issue](../../issues/new) öffnen mit:
- Kumio-Version (`/health` oder `VERSION`-Datei)
- LLM-Backend und Modell
- Reproduktionsschritte
- Erwartetes vs. tatsächliches Verhalten
- Relevante Logs (Einstellungen → Logs im Dashboard)

## Pull Requests

1. Fork erstellen
2. Feature-Branch anlegen: `git checkout -b feature/mein-feature`
3. Änderungen committen
4. Tests ausführen: `python backend/test_services.py`
5. PR öffnen mit Beschreibung der Änderung

## Entwicklungsumgebung

```bash
cp .env.example .env
# SQLITE_SECRETS_KEY setzen
docker compose up -d
```

Backend-Logs live: `docker logs -f kumio-backend`

## Stil-Regeln

- Python: PEP 8, Typ-Annotationen für neue Funktionen
- `@tool`-Docstrings akkurat halten — der Orchestrator-LLM liest sie
- Keine Modul-Namen im Core (`module_registry.py`, `orchestrator.py`) hardcodieren
- Frontend: kein ES-Module-Syntax (`export`/`import`) in Tab-JS-Dateien
