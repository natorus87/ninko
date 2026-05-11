"""
DataViz Core Module - Diagramme und Visualisierungen für Ninko.
"""

from core.module_registry import ModuleManifest


async def check_dataviz_health() -> dict:
    """Health check für DataViz Modul."""
    try:
        import matplotlib
        import plotly

        return {
            "status": "ok",
            "detail": f"matplotlib {matplotlib.__version__}, plotly {plotly.__version__}",
        }
    except ImportError as e:
        return {"status": "warning", "detail": f"Missing dependency: {e}"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="dataviz",
    display_name="DataViz Studio",
    description=(
        "Data visualization / dataviz: create professional charts and diagrams from data. "
        "Bar charts, line charts, pie charts, scatter plots, mermaid diagrams. "
        "Render via matplotlib or plotly."
    ),
    version="1.1.0",
    routing_keywords=[
        "diagramm",
        "diagram",
        "chart",
        "graph",
        "visualisierung",
        "plot",
        "matplotlib",
        "plotly",
        "mermaid",
        "dataviz",
        "balkendiagramm",
        "liniendiagramm",
        "kreisdiagramm",
        "pie chart",
        "bar chart",
        "line chart",
        "visualization",
        "render chart",
    ],
    api_prefix="/api/dataviz",
    dashboard_tab={"id": "dataviz", "label": "DataViz", "icon": "📊"},
    health_check=check_dataviz_health,
)
