"""
Operation Journal API for rollback and transaction visibility.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from core.auth import auth_tenant_id, resolve_request_auth
from core.operation_journal import get_operation_journal
from schemas.operation import (
    OperationJournalEntry,
    OperationListResponse,
    OperationUpdateResponse,
)

router = APIRouter(prefix="/api/operations", tags=["Operations"])


class RollbackNoteRequest(BaseModel):
    note: str


@router.get("/transactions", response_model=OperationListResponse)
async def list_transactions(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    status: str = Query(""),
    session_id: str = Query(""),
    category: str = Query(""),
) -> OperationListResponse:
    journal = get_operation_journal()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    entries = await journal.list(
        limit=limit,
        status=status.strip(),
        session_id=session_id.strip(),
        tenant_id=tenant_id,
        category=category.strip().upper(),
    )
    return OperationListResponse(
        entries=[OperationJournalEntry(**e) for e in entries],
        count=len(entries),
    )


@router.get("/transactions/{tx_id}", response_model=OperationJournalEntry)
async def get_transaction(tx_id: str, request: Request) -> OperationJournalEntry:
    journal = get_operation_journal()
    item = await journal.get(tx_id)
    if not item:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    if item.get("tenant_id", "default") != tenant_id:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return OperationJournalEntry(**item)


@router.post(
    "/transactions/{tx_id}/rollback-note",
    response_model=OperationUpdateResponse,
)
async def add_rollback_note(
    tx_id: str, body: RollbackNoteRequest, request: Request
) -> OperationUpdateResponse:
    journal = get_operation_journal()
    item = await journal.get(tx_id)
    if not item:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    if item.get("tenant_id", "default") != tenant_id:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    await journal.add_rollback_note(tx_id, body.note)
    return OperationUpdateResponse(tx_id=tx_id, updated=True)


@router.post(
    "/transactions/{tx_id}/rollback-complete",
    response_model=OperationUpdateResponse,
)
async def rollback_complete(
    tx_id: str, body: RollbackNoteRequest, request: Request
) -> OperationUpdateResponse:
    journal = get_operation_journal()
    item = await journal.get(tx_id)
    if not item:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    if item.get("tenant_id", "default") != tenant_id:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    await journal.mark_rolled_back(tx_id, body.note)
    return OperationUpdateResponse(tx_id=tx_id, status="rolled_back")
