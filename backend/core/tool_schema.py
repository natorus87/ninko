"""
Tool Schema System – Pydantic-basierte Parameter- und Response-Validierung.

Bietet einheitliche Basis-Klassen für alle Ninko-Tools:
  - ToolResponse  – strukturiertes Return-Format {success, data, error, meta}
  - ToolParams    – Basis-Parameter-Klasse mit connection_id
  - ToolError     – Exception für kontrollierte Tool-Fehler

Usage:
  from core.tool_schema import ToolResponse, ToolParams, ToolError

  class MyParams(ToolParams):
      item_id: int
      name: str = ""

  @tool
  async def my_tool(item_id: int, connection_id: str = "") -> str:
      try:
          ...
          return str(ToolResponse.ok({"id": item_id, "name": "foo"}))
      except ToolError as e:
          return str(ToolResponse.fail(str(e)))
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger("ninko.core.tool_schema")


class ToolError(Exception):
    """Raise this in tools for controlled failure (kein Stack-Trace-Logging)."""


class ToolResponse(BaseModel):
    """
    Einheitliches Return-Format für alle Ninko-Tools.

    Felder:
        success  – True wenn Tool erfolgreich ausgeführt wurde.
        data     – Nutzdaten (str, dict, list, int, …).
        error    – Fehlermeldung (nur wenn success=False).
        meta     – Optionale Metadaten (z.B. count, source, duration_ms).

    Der LLM bekommt immer __str__() — kein raw JSON wenn data ein str ist.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    success: bool
    data: Any = None
    error: str | None = None
    meta: dict[str, Any] | None = None

    def __str__(self) -> str:
        if not self.success:
            return f"Error: {self.error}"
        if isinstance(self.data, str):
            return self.data
        return json.dumps(self.data, ensure_ascii=False, default=str)

    @classmethod
    def ok(cls, data: Any = None, **meta: Any) -> "ToolResponse":
        """Erstelle eine erfolgreiche Response."""
        return cls(success=True, data=data, meta=meta or None)

    @classmethod
    def fail(cls, error: str, **meta: Any) -> "ToolResponse":
        """Erstelle eine Fehler-Response."""
        return cls(success=False, error=error, meta=meta or None)


class ToolParams(BaseModel):
    """
    Basis-Klasse für Tool-Parameter.

    Jede Tool-spezifische Params-Klasse erbt von hier und bekommt
    `connection_id` kostenlos sowie strict validation (no extra fields).

    Usage:
        class ListProjectsParams(ToolParams):
            status: str = "active"
            limit: int = 50
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    connection_id: str = ""
