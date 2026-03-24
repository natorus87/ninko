"""
Ninko – Pydantic-Modelle für Agenten-Definitionen.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field
import uuid


# ── Agent Step ───────────────────────────────────────

class AgentStep(BaseModel):
    """Ein einzelner Schritt im Agenten-Ausführungsablauf."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    order: int = 0
    type: Literal["module_action", "llm_call", "condition", "set_variable"] = "llm_call"
    label: str = ""
    config: dict = Field(default_factory=dict)
    # config examples:
    #   module_action: {"module": "kubernetes", "action": "get_pod_status"}
    #   llm_call:      {"prompt_template": "Summarize: {previous_output}"}
    #   condition:     {"expression": "output.contains('error')", "on_true": "abort", "on_false": "continue"}
    #   set_variable:  {"name": "result", "value": "{output}"}
    error_handling: Literal["retry", "skip", "abort"] = "abort"
    retry_count: int = 3


# ── Agent Definition ─────────────────────────────────

class AgentDefinition(BaseModel):
    """Vollständige Agenten-Definition."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    system_prompt: str = ""
    llm_provider_id: Optional[str] = None   # None = globaler Standard
    module_names: list[str] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
    enabled: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AgentCreate(BaseModel):
    """Payload zum Erstellen/Aktualisieren eines Agenten."""
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    system_prompt: str = ""
    llm_provider_id: Optional[str] = None
    module_names: list[str] = Field(default_factory=list)
    steps: list[AgentStep] = Field(default_factory=list)
    enabled: bool = True


class AgentListResponse(BaseModel):
    """Liste aller konfigurierten Agenten."""
    agents: list[AgentDefinition] = Field(default_factory=list)
    total: int = 0
