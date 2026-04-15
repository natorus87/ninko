# Ninko Tests

This directory contains all tests for the Ninko backend.

## Test Structure

```
backend/tests/
├── conftest.py              # Shared fixtures and configuration
├── test_api_smoke.py        # API smoke tests (quick health checks)
└── README.md                # This file
```

Legacy test files in `backend/` (will be migrated):
- `test_*.py` files - Various component tests

## Running Tests

### Install test dependencies

```bash
cd backend
pip install pytest pytest-asyncio httpx
```

Or install all dev dependencies:
```bash
pip install -e ".[dev]"
```

### Run all tests

```bash
pytest
```

### Run specific test categories

```bash
# Unit tests only
pytest -m unit

# Integration tests (require services)
pytest -m integration

# E2E tests
pytest -m e2e

# Exclude slow tests
pytest -m "not slow"
```

### Run with verbose output

```bash
pytest -v
```

### Run with coverage

```bash
pytest --cov=backend --cov-report=html
```

## Test Markers

- `@pytest.mark.unit` - Fast, isolated unit tests
- `@pytest.mark.integration` - Integration tests (may use Redis, external APIs)
- `@pytest.mark.e2e` - End-to-end tests (full system tests)
- `@pytest.mark.slow` - Slow tests (can be skipped with `-m 'not slow'`)
- `@pytest.mark.redis` - Tests requiring Redis
- `@pytest.mark.llm` - Tests requiring LLM providers

## Writing Tests

### Basic Test Structure

```python
import pytest
from httpx import AsyncClient

@pytest.mark.unit
async def test_something():
    """Test description here."""
    async with AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.get("/api/agents/")
        assert response.status_code == 200
```

### Using Fixtures

```python
# conftest.py provides fixtures like mock_redis, sample_agent_data
async def test_with_fixture(mock_redis, sample_agent_data):
    # Use fixtures here
    pass
```

### Async Tests

All tests are async by default (configured in pytest.ini). Use `async def` for test functions.

## API Smoke Tests

Quick health checks for critical API endpoints:

```bash
pytest tests/test_api_smoke.py -v
```

This tests:
- `/api/health` - API availability
- `/api/agents/` - Agent management
- `/api/workflows/` - Workflow management
- `/api/modules/` - Module management
- `/api/skills/` - Skills management
- `/api/scripting/scripts` - Scripting module
- `/api/codelab/languages` - Code execution

## Configuration

Test configuration is in:
- `pytest.ini` - Pytest settings
- `pyproject.toml` - Tool configurations (pytest, black, ruff, mypy)

## Debugging

### Enable verbose logging

```bash
pytest -v --log-cli-level=DEBUG
```

### Stop on first failure

```bash
pytest -x
```

### Run specific test

```bash
pytest tests/test_api_smoke.py::test_api_agents_list -v
```

## CI Integration

Example GitHub Actions workflow:

```yaml
- name: Run tests
  run: pytest -v --tb=short
```

## Troubleshooting

### Redis connection errors

Tests requiring Redis will be marked as `redis`. Skip them if Redis is not available:
```bash
pytest -m "not redis"
```

### LLM provider errors

Tests requiring LLM providers are marked as `llm`. Skip them:
```bash
pytest -m "not llm"
```

### Port conflicts

Ensure no other service is running on port 8000 when running integration tests.
