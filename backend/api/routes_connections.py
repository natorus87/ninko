"""
Ninko API Router für Multi-Connection Management.
"""

from fastapi import APIRouter, HTTPException, Request

from schemas.connection import ConnectionCreate, ConnectionRead, ConnectionUpdate, ConnectionListResponse
from core.auth import auth_tenant_id, resolve_request_auth
from core.connections import ConnectionManager

router = APIRouter(prefix="/api/connections", tags=["Connections"])


@router.get("/{module_id}", response_model=ConnectionListResponse)
async def list_connections(module_id: str, request: Request) -> ConnectionListResponse:
    """Holt alle konfigurierten Verbindungen für das spezifizierte Modul."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    connections = await ConnectionManager.list_connections(module_id, tenant_id=tenant_id)
    return ConnectionListResponse(module_id=module_id, connections=connections, total=len(connections))


@router.post("/{module_id}", response_model=ConnectionRead, status_code=201)
async def create_connection(module_id: str, data: ConnectionCreate, request: Request) -> ConnectionRead:
    """Fügt eine neue Verbindung für das Modul hinzu."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    return await ConnectionManager.create_connection(module_id, data, tenant_id=tenant_id)


@router.put("/{module_id}/{connection_id}", response_model=ConnectionRead)
async def update_connection(module_id: str, connection_id: str, data: ConnectionUpdate, request: Request) -> ConnectionRead:
    """Aktualisiert eine bestehende Verbindung."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    result = await ConnectionManager.update_connection(module_id, connection_id, data, tenant_id=tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Connection not found")
    return result


@router.delete("/{module_id}/{connection_id}", status_code=204)
async def delete_connection(module_id: str, connection_id: str, request: Request) -> None:
    """Löscht die Verbindung und ihre Vault Secrets."""
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    success = await ConnectionManager.delete_connection(module_id, connection_id, tenant_id=tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Connection not found")
