# Ninko API Documentation

This document describes the core API flows, authentication, and multi-tenant behavior of the Ninko platform.

## Base URL

```
http://localhost:8000/api
```

## Authentication

Ninko uses API Key authentication passed in the header:

```
X-API-Key: your-api-key-here
```

### Getting an API Key

API access can happen via configured API keys or signed API access tokens, depending on deployment and auth setup.

### Multi-Tenant Behavior

Ninko supports multi-tenancy through tenant isolation:

- **Tenant Identification**: The tenant is derived from the resolved auth context (for example API key, API token, or session)
- **Data Isolation**: Each tenant's data is stored separately in Redis with tenant-scoped keys
- **Default Tenant**: If no tenant is identified, operations fall back to the `default` tenant

Example tenant-scoped Redis keys:
```
ninko:agents:tenant1        # Agents for tenant1
ninko:workflows:tenant1   # Workflows for tenant1
ninko:agents:default       # Agents for default tenant
```

## Core API Flows

### 1. Agent Management

#### List all agents
```http
GET /api/agents/
```

**Response:**
```json
{
  "agents": [
    {
      "id": "agent-123",
      "name": "Kubernetes Helper",
      "description": "Helps with K8s tasks",
      "system_prompt": "You are a Kubernetes expert...",
      "enabled": true,
      "module_names": ["kubernetes"],
      "steps": [],
      "created_at": "2025-01-01T00:00:00Z",
      "updated_at": "2025-01-01T00:00:00Z"
    }
  ],
  "total": 1
}
```

#### Create an agent
```http
POST /api/agents/
Content-Type: application/json

{
  "name": "My Agent",
  "description": "Description here",
  "system_prompt": "You are a helpful assistant...",
  "module_names": ["web_search"],
  "enabled": true
}
```

#### Generate agent with AI
```http
POST /api/agents/generate
Content-Type: application/json

{
  "use_case": "Help me monitor my Kubernetes cluster",
  "allowed_modules": ["kubernetes", "checkmk"]
}
```

**Response (success):**
```json
{
  "name": "K8s Monitor",
  "description": "Monitors Kubernetes clusters and reports issues",
  "system_prompt": "You are a Kubernetes monitoring expert...",
  "suggested_modules": ["kubernetes", "checkmk"]
}
```

**Response (fallback):**
```json
{
  "name": "Custom Agent",
  "description": "Agent for: Help me monitor my Kubernetes cluster",
  "system_prompt": "...",
  "suggested_modules": ["kubernetes"],
  "_generation_info": {
    "fallback_used": true,
    "original_error": "No JSON found in LLM response"
  }
}
```

**Fallback Behavior:**
The generation endpoint includes robust error handling:
- **JSON Parsing**: Extracts JSON from Markdown code blocks, handles common formatting errors (trailing commas, nested braces)
- **Module Inference**: Automatically suggests modules based on keywords in the use case
- **Graceful Degradation**: If LLM generation fails, returns a minimal valid agent specification instead of an error
- **Generation Info**: Always includes `_generation_info` to indicate whether fallback was used

**Module Inference Keywords:**
| Keywords | Suggested Modules |
|----------|-------------------|
| kubernetes, k8s, pod, container | kubernetes, docker |
| linux, server, ssh | linux_server |
| proxmox, vm | proxmox |
| firewall | opnsense |
| dns, blocking | pihole |
| smart home, homeassistant | homeassistant |
| ticket, helpdesk | glpi |
| monitoring, alert | checkmk |
| github, gitlab, ci/cd, pipeline | github, gitlab |
| web_search, recherche, suchen, internet | web_search |
| bild, image, foto | image_gen |

### 2. Workflow Management

#### List all workflows
```http
GET /api/workflows/
```

#### Create a workflow
```http
POST /api/workflows/
Content-Type: application/json

{
  "name": "Daily Report",
  "description": "Generate daily system report",
  "nodes": [
    {
      "id": "node-1",
      "type": "trigger",
      "label": "Start",
      "config": {"mode": "manual"},
      "position": {"x": 100, "y": 100}
    },
    {
      "id": "node-2",
      "type": "agent",
      "label": "Generate Report",
      "config": {"agent_id": "", "prompt": "Generate system report"},
      "position": {"x": 400, "y": 100}
    },
    {
      "id": "node-3",
      "type": "end",
      "label": "Finish",
      "config": {"status": "succeeded"},
      "position": {"x": 700, "y": 100}
    }
  ],
  "edges": [
    {"id": "e1", "source_id": "node-1", "target_id": "node-2"},
    {"id": "e2", "source_id": "node-2", "target_id": "node-3"}
  ],
  "variables": [],
  "enabled": true
}
```

#### Run a workflow
```http
POST /api/workflows/{workflow_id}/run
```

**Response:**
```json
{
  "run_id": "run-456",
  "status": "running"
}
```

#### Get workflow runs
```http
GET /api/workflows/{workflow_id}/runs
```

**Response:**
```json
{
  "runs": [
    {
      "id": "run-456",
      "workflow_id": "wf-123",
      "status": "succeeded",
      "started_at": "2025-01-01T12:00:00Z",
      "finished_at": "2025-01-01T12:00:05Z",
      "duration_ms": 5000
    }
  ]
}
```

#### Get run status
```http
GET /api/workflows/runs/{run_id}
```

**Response:**
```json
{
  "run_id": "run-456",
  "status": "running",
  "started_at": "2025-01-01T12:00:00Z",
  "steps_completed": 2,
  "steps_total": 5
}
```

#### List workflow versions
```http
GET /api/workflows/{workflow_id}/versions
```

**Response:**
```json
{
  "versions": [
    {
      "version": 3,
      "created_at": "2025-01-15T10:00:00Z",
      "name": "Daily Report",
      "description": "Updated with parallel nodes"
    },
    {
      "version": 2,
      "created_at": "2025-01-10T08:00:00Z",
      "name": "Daily Report",
      "description": "Added notification step"
    },
    {
      "version": 1,
      "created_at": "2025-01-01T00:00:00Z",
      "name": "Daily Report",
      "description": "Initial version"
    }
  ]
}
```

#### Restore workflow version
```http
POST /api/workflows/{workflow_id}/versions/{version}/restore
```

**Response:**
```json
{
  "status": "restored",
  "version": 4,
  "restored_from": 2
}
```

**Versioning Behavior:**
- Each workflow update creates a new version automatically
- Version history is preserved (no limit on number of versions)
- Restoring a version creates a new version (current version number + 1) with the restored content
- Run history is associated with the version that was active at the time of execution

### 3. Script Management

#### List all scripts
```http
GET /api/scripting/scripts
```

#### Create a script
```http
POST /api/scripting/scripts
Content-Type: application/json

{
  "name": "disk-cleanup",
  "description": "Clean up old log files",
  "code": "#!/usr/bin/env python3\nimport shutil\nprint('Disk cleanup completed')",
  "language": "python",
  "timeout": 60,
  "tags": ["maintenance", "daily"]
}
```

#### Execute a script
```http
POST /api/scripting/scripts/{script_id}/execute
```

**Response:**
```json
{
  "id": "exec-789",
  "script_id": "script-123",
  "script_name": "disk-cleanup",
  "started_at": "2025-01-01T12:00:00Z",
  "finished_at": "2025-01-01T12:00:02Z",
  "status": "succeeded",
  "stdout": "Disk cleanup completed\n",
  "stderr": "",
  "exit_code": 0,
  "duration_ms": 2000,
  "executed_by": "",
  "triggered_by": "manual"
}
```

### 4. Module Management

#### List available modules
```http
GET /api/modules/
```

**Response:**
```json
[
  {
    "name": "kubernetes",
    "display_name": "Kubernetes",
    "description": "Kubernetes cluster management",
    "enabled": true,
    "version": "1.0.0"
  }
]
```

### 5. Skills Management

#### List all skills
```http
GET /api/skills/
```

**Response:**
```json
[
  {
    "name": "web_search",
    "description": "Search the web for information",
    "builtin": true,
    "modules": []
  }
]
```

## Error Handling

### Common HTTP Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| 200 | OK | Request successful |
| 201 | Created | Resource created successfully |
| 400 | Bad Request | Invalid request data |
| 401 | Unauthorized | Missing or invalid API key |
| 404 | Not Found | Resource does not exist |
| 409 | Conflict | Resource already exists (duplicate name) |
| 422 | Unprocessable Entity | Validation error |
| 500 | Internal Server Error | Server error |

### Error Response Format

```json
{
  "detail": "Error message here"
}
```

### Validation Errors

```json
{
  "detail": [
    {
      "loc": ["body", "name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

## Rate Limiting

Currently, Ninko does not implement rate limiting at the API gateway level. Rate limiting should be configured at the reverse proxy (nginx, traefik) level if needed.

## WebSocket

Real-time chat and notifications are available via WebSocket:

```
ws://localhost:8000/ws/{client_id}
```

See the WebSocket documentation for details on message formats.

## OpenAPI / Swagger UI

Interactive API documentation is available at:

```
http://localhost:8000/docs
```

ReDoc documentation:
```
http://localhost:8000/redoc
```

## Testing

### Smoke Tests
Verify basic API availability:

```bash
cd backend
pytest tests/test_api_smoke.py -v
```

### Integration Tests
Test critical API paths for Agents and Workflows:

```bash
# Agents API (CRUD + Generation)
pytest tests/test_agents_integration.py -v

# Workflows API (CRUD + Execution + Versions)
pytest tests/test_workflows_integration.py -v
```

### E2E Workflow Tests
Test complete workflow lifecycle:

```bash
# Requires running backend at localhost:8000
NINKO_BASE_URL=http://localhost:8000 python test_e2e_workflow_critical_path.py
```

### Test Organization

| Test File | Purpose | Type |
|-----------|---------|------|
| `test_api_smoke.py` | Basic endpoint availability | Smoke |
| `test_agents_integration.py` | Agent CRUD + Generation | Integration |
| `test_workflows_integration.py` | Workflow CRUD + Runs + Versions | Integration |
| `test_e2e_workflow_critical_path.py` | Full workflow lifecycle | E2E |

Run all tests:
```bash
pytest -v
```
