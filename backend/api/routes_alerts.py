"""
REST API für Alert-Management.

Bietet Endpoints für das Frontend um aktive Alerts anzuzeigen und zu verwalten.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from core.alert_state import get_alert_manager
from core.schemas import ApiResponse

logger = logging.getLogger("ninko.api.alerts")

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=ApiResponse)
async def list_alerts(module: str | None = None) -> ApiResponse:
    """
    Liste aller aktiven Alerts (optional gefiltert nach Modul).

    Args:
        module: Optionales Modul-Filter

    Returns:
        ApiResponse mit Liste von Alerts
    """
    try:
        mgr = get_alert_manager()
        alerts = await mgr.list_active(module=module)

        return ApiResponse(
            success=True,
            data={
                "alerts": alerts,
                "total": len(alerts),
                "filter": module,
            },
        )
    except Exception as exc:
        logger.error("Fehler beim Laden der Alerts: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Laden der Alerts: {exc}",
        )


@router.get("/{alert_id}", response_model=ApiResponse)
async def get_alert(alert_id: str) -> ApiResponse:
    """
    Details eines einzelnen Alerts abrufen.

    Args:
        alert_id: Die Alert-ID

    Returns:
        ApiResponse mit Alert-Details oder 404 wenn nicht aktiv
    """
    try:
        mgr = get_alert_manager()
        state = await mgr.get_state(alert_id)

        if not state:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert {alert_id} nicht gefunden",
            )

        return ApiResponse(
            success=True,
            data=state,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Fehler beim Abrufen des Alerts %s: %s", alert_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Abrufen des Alerts: {exc}",
        )


@router.post("/{alert_id}/resolve", response_model=ApiResponse)
async def resolve_alert_endpoint(alert_id: str) -> ApiResponse:
    """
    Markiert einen Alert als gelöst (manuelles Resolven).

    Args:
        alert_id: Die zu resolvende Alert-ID

    Returns:
        ApiResponse mit Erfolgsstatus
    """
    try:
        mgr = get_alert_manager()
        resolved = await mgr.resolve(
            alert_id,
            resolution="Manually resolved via Dashboard",
        )

        if not resolved:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert {alert_id} war nicht aktiv",
            )

        return ApiResponse(
            success=True,
            data={
                "alert_id": alert_id,
                "resolved": True,
                "message": f"Alert {alert_id} wurde als gelöst markiert",
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Fehler beim Resolven des Alerts %s: %s", alert_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fehler beim Resolven des Alerts: {exc}",
        )
