"""
Kumio Connection Schemas.
Verwaltet die Metadaten für Multi-Connection-Support (z. B. Prod-Cluster vs Staging-Cluster).
"""

from typing import Dict, Optional, Literal
from pydantic import BaseModel, Field


EnvironmentLabel = Literal["prod", "staging", "dev", "lab", "local", "unknown"]


class ConnectionCreate(BaseModel):
    name: str = Field(..., description="Anzeigename der Verbindung (z. B. 'Prod Cluster')")
    environment: EnvironmentLabel = Field("unknown", description="Umgebungskontext für KI-Awareness")
    description: Optional[str] = Field(None, description="Zusätzliche Infos")
    is_default: bool = Field(False, description="Ist dies die Standardverbindung für das Modul")
    
    config: Dict[str, str] = Field(
        default_factory=dict, 
        description="Nicht-geheime Parameter (Base URL, Options etc.)"
    )
    secrets: Dict[str, str] = Field(
        default_factory=dict, 
        description="Sensible Daten (Tokens, Passwörter), werden im Vault gespeichert und im Read-Modell nicht zurückgegeben"
    )


class ConnectionUpdate(BaseModel):
    name: Optional[str] = None
    environment: Optional[EnvironmentLabel] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None
    config: Optional[Dict[str, str]] = None
    secrets: Optional[Dict[str, str]] = None


class ConnectionRead(BaseModel):
    id: str = Field(..., description="Eindeutige ID der Verbindung")
    module_id: str = Field(..., description="Das Modul, zu dem diese Verbindung gehört (z.B. kubernetes)")
    name: str
    environment: EnvironmentLabel
    description: Optional[str] = None
    is_default: bool
    config: Dict[str, str]
    vault_keys: Dict[str, str] = Field(..., description="Welche Geheimnisse im Vault unter welchen Schlüsseln liegen")
    
    # Optional runtime status, e.g. for health checks
    status: Optional[str] = None


class ConnectionListResponse(BaseModel):
    module_id: str
    connections: list[ConnectionRead]
    total: int
