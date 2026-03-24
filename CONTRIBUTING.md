# Contributing to Kumio

## Adding a new module

The easiest way to contribute is a new module. Every module lives entirely under `backend/modules/<name>/` — the core code is never touched.

Structure: `manifest.py`, `agent.py`, `tools.py`, `routes.py`, `frontend/tab.html`, `frontend/tab.js`, `__init__.py`.

Details and example: [README.md → Building a Module](README.md#building-a-module)

## Reporting bugs

Please open an [issue](../../issues/new) including:
- Kumio version (from `VERSION` or `/health`)
- LLM backend and model
- Steps to reproduce
- Expected vs. actual behavior
- Relevant logs (Dashboard → Settings → Logs)

## Pull requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes
4. Run tests: `python backend/test_services.py`
5. Open a PR with a description of your changes

## Development setup

```bash
cp .env.example .env
# Set SQLITE_SECRETS_KEY
docker compose up -d
```

Live backend logs: `docker logs -f kumio-backend`

## Code style

- Python: PEP 8, type annotations for new functions
- Keep `@tool` docstrings accurate — the orchestrator LLM reads them for reasoning
- Never hardcode module names in core files (`module_registry.py`, `orchestrator.py`)
- Frontend: no ES module syntax (`export`/`import`) in tab JS files
