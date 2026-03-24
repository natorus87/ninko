"""
Kumio WebSocket API – Log-Streaming und Alert-Benachrichtigungen.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.redis_client import get_redis

logger = logging.getLogger("kumio.api.ws")
router = APIRouter(tags=["WebSocket"])


class ConnectionManager:
    """Verwaltet aktive WebSocket-Verbindungen."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        logger.info(
            "WebSocket verbunden. Aktive Verbindungen: %d",
            len(self._connections),
        )

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)
        logger.info(
            "WebSocket getrennt. Aktive Verbindungen: %d",
            len(self._connections),
        )

    async def broadcast(self, message: dict) -> None:
        """Sendet eine Nachricht an alle verbundenen Clients."""
        disconnected: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(ws)

    @property
    def active_count(self) -> int:
        return len(self._connections)


# Globaler ConnectionManager
ws_manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket-Endpunkt für:
    - Alert-Benachrichtigungen vom Monitor-Agent
    - Log-Streaming
    - Echtzeit-Updates
    """
    await ws_manager.connect(websocket)

    # Redis PubSub Listener starten
    redis = get_redis()
    pubsub = await redis.subscribe_events()

    try:
        # Willkommensnachricht
        await websocket.send_json(
            {
                "type": "connected",
                "message": "Kumio WebSocket verbunden.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Zwei parallele Tasks: Redis Events lesen + WebSocket Messages empfangen
        results = await asyncio.gather(
            _listen_redis_events(pubsub, websocket),
            _listen_websocket_messages(websocket),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, WebSocketDisconnect):
                raise result
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                logger.debug("WebSocket subtask beendet mit: %s", type(result).__name__)

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as exc:
        logger.error("WebSocket Fehler: %s", exc)
        ws_manager.disconnect(websocket)
    finally:
        await pubsub.unsubscribe()


async def _listen_redis_events(
    pubsub, websocket: WebSocket
) -> None:
    """Leitet Redis PubSub Events an den WebSocket weiter."""
    while True:
        message = await pubsub.get_message(
            ignore_subscribe_messages=True, timeout=1.0
        )
        if message and message.get("type") == "message":
            try:
                data = json.loads(message["data"])
                await websocket.send_json(data)
            except (json.JSONDecodeError, Exception) as exc:
                logger.debug("Redis-Event Parse-Fehler: %s", exc)

        await asyncio.sleep(0.1)


async def _listen_websocket_messages(websocket: WebSocket) -> None:
    """Empfängt Nachrichten vom WebSocket Client (z.B. Ping/Pong)."""
    while True:
        try:
            data = await websocket.receive_text()
            # Ping/Pong
            if data == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
        except WebSocketDisconnect:
            raise
        except Exception:
            await asyncio.sleep(1)
