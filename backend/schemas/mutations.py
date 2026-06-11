"""
Ninko – Einheitliche Mutation-Response-Schemas.

Alle Mutations-Endpoints (POST/PUT/DELETE) geben eine ``MutationResponse`` mit
einheitlichem Schema zurück. Vorher gab es drei inkonsistente Patterns:

* ``{"status": "created|updated|deleted|saved|ok|reset|active|revoked|rolled_back"}``
* ``{"deleted": True, "id": ...}``
* ``{"success": True, "data": {...}}``

PLAN.md Item 2.4 vereinheitlicht diese zu einer ``MutationResponse`` mit
optionalem ``id`` und freitextlichem ``message``. Domain-spezifische
Zusatzfelder (``session_id``, ``count``, ``tx_id``, ``token_id`` etc.) bleiben
als optionale Felder erhalten, sind aber typisiert.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ── Canonical status values ──────────────────────────────────────────────


MutationStatus = Literal[
    "created",
    "updated",
    "deleted",
    "saved",
    "reset",
    "revoked",
    "rolled_back",
    "active",
    "noop",
    "ok",
    "error",
]


# ── Core model ────────────────────────────────────────────────────────────


class MutationResponse(BaseModel):
    """Standard-Antwort für alle Mutations-Endpoints (POST/PUT/DELETE).

    ``id`` ist optional, weil nicht jede Mutation eine erzeugte ID zurückgibt
    (z. B. Bulk-Reset, LLM-Provider-Test, Status-Toggle).

    ``message`` ist optional, weil viele Endpoints nur ``status`` + ``id``
    zurückgeben und das sprechende Feld nicht brauchen.

    ``data`` ist eine generische Tasche für domain-spezifische Zusatzfelder
    (``count``, ``session_id``, ``filename`` etc.). Vermeiden — lieber
    dedizierte Felder hinzufügen, wenn die Domain stabil ist.
    """

    status: MutationStatus
    id: Optional[str] = None
    message: Optional[str] = None
    data: Optional[dict[str, Any]] = Field(
        default=None,
        description=(
            "Optionaler generischer Daten-Tasche. Domain-spezifische Endpoints "
            "sollten dedizierte Felder bevorzugen."
        ),
    )
