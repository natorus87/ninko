"""
Pydantic Schemas für DataViz Modul.
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict, Union


class ChartDataPoint(BaseModel):
    """Ein einzelner Datenpunkt für Charts."""

    label: str = Field(..., description="Beschriftung/X-Achse")
    value: Union[float, int] = Field(..., description="Wert/Y-Achse")
    category: Optional[str] = Field(None, description="Kategorie für gruppierte Daten")


class ChartRequest(BaseModel):
    """Basis-Request für Chart-Generierung."""

    chart_type: Literal["line", "bar", "pie", "scatter", "area"] = Field(
        ..., description="Typ des Diagramms"
    )
    title: str = Field(..., description="Titel des Diagramms")
    data: List[ChartDataPoint] = Field(..., description="Datenpunkte")
    x_label: Optional[str] = Field(None, description="Beschriftung X-Achse")
    y_label: Optional[str] = Field(None, description="Beschriftung Y-Achse")
    width: int = Field(800, description="Breite in Pixeln")
    height: int = Field(600, description="Höhe in Pixeln")
    format: Literal["png", "svg", "html", "json"] = Field(
        "png", description="Ausgabeformat"
    )
    theme: Optional[str] = Field(
        "default", description="Farbschema (default, dark, light)"
    )


class MermaidRequest(BaseModel):
    """Request für Mermaid-Diagramm."""

    diagram_type: Literal["flowchart", "sequence", "gantt", "pie", "class", "state"] = (
        Field(..., description="Typ des Mermaid-Diagramms")
    )
    code: str = Field(..., description="Mermaid-Diagramm-Code")
    title: Optional[str] = Field(None, description="Titel des Diagramms")
    width: int = Field(800, description="Breite in Pixeln")
    height: int = Field(600, description="Höhe in Pixeln")
    format: Literal["svg", "png", "html"] = Field("svg", description="Ausgabeformat")


class ChartResponse(BaseModel):
    """Response mit generiertem Chart."""

    success: bool
    chart_type: str
    format: str
    data: Optional[str] = Field(
        None, description="Base64-kodiertes Bild oder HTML/JSON"
    )
    url: Optional[str] = Field(None, description="URL zum Abrufen des Charts")
    error: Optional[str] = None


class MultiSeriesChartRequest(BaseModel):
    """Request für Multi-Series Charts (z.B. mehrere Linien)."""

    chart_type: Literal["line", "bar", "area"] = Field(
        ..., description="Typ des Diagramms"
    )
    title: str = Field(..., description="Titel des Diagramms")
    series: Dict[str, List[ChartDataPoint]] = Field(
        ..., description="Mehrere Datenreihen mit Namen als Key"
    )
    x_label: Optional[str] = Field(None, description="Beschriftung X-Achse")
    y_label: Optional[str] = Field(None, description="Beschriftung Y-Achse")
    width: int = Field(800, description="Breite in Pixeln")
    height: int = Field(600, description="Höhe in Pixeln")
    format: Literal["png", "svg", "html"] = Field("png", description="Ausgabeformat")


class WebSearchChartRequest(BaseModel):
    """Request für Chart basierend auf Websuche."""

    query: str = Field(..., description="Suchanfrage für Daten")
    chart_type: Literal["line", "bar", "pie"] = Field("line", description="Chart-Typ")
    title: Optional[str] = Field(
        None, description="Titel (optional, sonst aus Query generiert)"
    )
    time_range: Optional[str] = Field("1m", description="Zeitraum: 1d, 1w, 1m, 3m, 1y")
