"""
Ninko – Persistenter Session State.

Speichert den vollständigen Zustand einer Routing-/Pipeline-Session
als Python-Objekt in Redis. Ermöglicht:
- Resume bei Unterbrechung
- Debugging vergangener Aufrufe
- Context für Folge-Anfragen
- Audit-Trail ohne Strings zu parsen

Der State ist kein Replacement für Chat-History – er ist der
Maschinenkontext der Routing-Engine.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("ninko.session_state")

_STATE_TTL = 86400  # 24h, matching Chat-History TTL


class DetectedModule(BaseModel):
    """Ein vom Routing erkanntes Modul mit Score."""

    name: str
    score: float = 0.0
    matched_keywords: list[str] = Field(default_factory=list)


class PipelineStepRecord(BaseModel):
    """Kompakter Record eines ausgeführten Pipeline-Steps (für State-Tracking)."""

    module: str
    task_preview: str
    status: str
    result_preview: str = ""
    error: str | None = None
    duration_ms: float = 0.0


class SessionState(BaseModel):
    """
    Vollständiger Routing-/Pipeline-State einer Session.

    Wird nach jeder wesentlichen Zustandsänderung persistiert.
    """

    session_id: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # Aktuelle Anfrage
    current_request: str = ""
    request_turn_id: str | None = None

    # Routing-Ergebnisse
    detected_intents: list[str] = Field(default_factory=list)
    detected_modules: list[DetectedModule] = Field(default_factory=list)
    routing_tier: int | None = None
    routing_target_module: str | None = None

    # Pipeline-State
    pipeline_id: str | None = None
    pipeline_status: str | None = None
    pipeline_steps: list[PipelineStepRecord] = Field(default_factory=list)

    # Fehler & Entscheidungen
    errors: list[str] = Field(default_factory=list)
    pending_confirmations: list[str] = Field(default_factory=list)

    # Tool-Outputs (für Context-Weitergabe zwischen Turns)
    last_tool_outputs: dict[str, str] = Field(default_factory=dict)

    # Flags
    was_compacted: bool = False
    last_task_sketch_summary: str = ""

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def record_error(self, error: str) -> None:
        self.errors.append(error)
        self.touch()

    def record_pipeline_step(
        self,
        module: str,
        task: str,
        status: str,
        result: str = "",
        error: str | None = None,
        duration_ms: float = 0.0,
    ) -> None:
        self.pipeline_steps.append(PipelineStepRecord(
            module=module,
            task_preview=task[:150],
            status=status,
            result_preview=result[:300],
            error=error,
            duration_ms=duration_ms,
        ))
        self.touch()


class SessionStateManager:
    """Verwaltet das Laden und Speichern von SessionState-Objekten in Redis."""

    @staticmethod
    def _key(session_id: str) -> str:
        return f"ninko:session_state:{session_id}"

    @classmethod
    async def load(cls, session_id: str) -> SessionState | None:
        """Lädt den State aus Redis. Gibt None zurück falls nicht vorhanden."""
        if not session_id:
            return None
        try:
            from core.redis_client import get_redis
            raw = await get_redis().connection.get(cls._key(session_id))
            if not raw:
                return None
            data = json.loads(raw)
            return SessionState.model_validate(data)
        except Exception as exc:
            logger.warning("SessionState laden fehlgeschlagen für '%s': %s", session_id, exc)
            return None

    @classmethod
    async def save(cls, state: SessionState) -> None:
        """Persistiert den State in Redis."""
        if not state.session_id:
            return
        try:
            from core.redis_client import get_redis
            state.touch()
            await get_redis().connection.set(
                cls._key(state.session_id),
                json.dumps(state.model_dump()),
                ex=_STATE_TTL,
            )
        except Exception as exc:
            logger.warning(
                "SessionState speichern fehlgeschlagen für '%s': %s",
                state.session_id,
                exc,
            )

    @classmethod
    async def get_or_create(cls, session_id: str) -> SessionState:
        """Lädt oder erstellt einen frischen State für die Session."""
        existing = await cls.load(session_id)
        return existing or SessionState(session_id=session_id)

    @classmethod
    async def delete(cls, session_id: str) -> None:
        """Löscht den State aus Redis."""
        if not session_id:
            return
        try:
            from core.redis_client import get_redis
            await get_redis().connection.delete(cls._key(session_id))
        except Exception as exc:
            logger.debug("SessionState löschen fehlgeschlagen für '%s': %s", session_id, exc)

    @classmethod
    async def update_routing(
        cls,
        session_id: str,
        *,
        request: str,
        intents: list[str],
        modules: list[dict[str, Any]],
        tier: int,
        target_module: str | None,
    ) -> SessionState:
        """Aktualisiert Routing-Informationen atomisch."""
        state = await cls.get_or_create(session_id)
        state.current_request = request[:500]
        state.detected_intents = intents[:10]
        state.detected_modules = [
            DetectedModule(
                name=m.get("module", m.get("name", "")),
                score=float(m.get("score", 0.0)),
                matched_keywords=m.get("reasons", m.get("matched_keywords", [])),
            )
            for m in modules
        ]
        state.routing_tier = tier
        state.routing_target_module = target_module
        await cls.save(state)
        return state

    @classmethod
    async def update_pipeline(
        cls,
        session_id: str,
        *,
        pipeline_id: str,
        status: str,
    ) -> None:
        """Aktualisiert Pipeline-Status."""
        state = await cls.get_or_create(session_id)
        state.pipeline_id = pipeline_id
        state.pipeline_status = status
        await cls.save(state)
