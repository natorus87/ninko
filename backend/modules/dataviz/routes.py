"""
FastAPI Routes für DataViz Modul.
"""

import base64
import io
import json
import logging
from html import escape

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from modules.dataviz.schemas import (
    ChartRequest,
    ChartResponse,
    MermaidRequest,
    MultiSeriesChartRequest,
)

router = APIRouter(prefix="/dataviz", tags=["dataviz"])
logger = logging.getLogger("ninko.modules.dataviz")


def _ensure_matplotlib() -> None:
    import matplotlib

    matplotlib.use("Agg")


@router.post("/chart", response_model=ChartResponse)
async def create_chart(request: ChartRequest):
    """Erstellt ein Diagramm aus Daten."""
    try:
        _ensure_matplotlib()
        import matplotlib.pyplot as plt

        labels = [d.label for d in request.data]
        values = [d.value for d in request.data]
        if not labels:
            raise HTTPException(status_code=400, detail="No chart data provided.")

        fig, ax = plt.subplots(figsize=(request.width / 100, request.height / 100))

        if request.chart_type == "line":
            ax.plot(labels, values, marker="o", linewidth=2)
        elif request.chart_type == "bar":
            ax.bar(labels, values, color="steelblue")
        elif request.chart_type == "pie":
            ax.pie(values, labels=labels, autopct="%1.1f%%")
        elif request.chart_type == "scatter":
            ax.scatter(range(len(values)), values)
        elif request.chart_type == "area":
            ax.fill_between(range(len(values)), values, alpha=0.5)

        ax.set_title(request.title)
        if request.x_label:
            ax.set_xlabel(request.x_label)
        if request.y_label:
            ax.set_ylabel(request.y_label)

        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()

        if request.format == "png":
            buffer = io.BytesIO()
            plt.savefig(buffer, format="png", dpi=100)
            buffer.seek(0)
            image_base64 = base64.b64encode(buffer.read()).decode()
            plt.close(fig)
            return ChartResponse(
                success=True,
                chart_type=request.chart_type,
                format="png",
                data=f"data:image/png;base64,{image_base64}",
            )
        elif request.format == "svg":
            buffer = io.BytesIO()
            plt.savefig(buffer, format="svg")
            buffer.seek(0)
            svg_data = buffer.read().decode()
            plt.close(fig)
            return ChartResponse(
                success=True, chart_type=request.chart_type, format="svg", data=svg_data
            )
        elif request.format == "html":
            try:
                import plotly.graph_objects as go
                import plotly.io as pio

                if request.chart_type == "pie":
                    fig = go.Figure(data=[go.Pie(labels=labels, values=values)])
                elif request.chart_type == "bar":
                    fig = go.Figure(data=[go.Bar(x=labels, y=values)])
                else:
                    fig = go.Figure(
                        data=[go.Scatter(x=labels, y=values, mode="lines+markers")]
                    )
                fig.update_layout(
                    title=request.title,
                    xaxis_title=request.x_label,
                    yaxis_title=request.y_label,
                    template="plotly_white",
                )
                html = pio.to_html(fig, full_html=True, include_plotlyjs="cdn")
                return ChartResponse(
                    success=True,
                    chart_type=request.chart_type,
                    format="html",
                    data=html,
                )
            except Exception as exc:
                logger.warning("Plotly HTML chart failed: %s", exc)
                raise HTTPException(status_code=500, detail="Chart rendering failed.")
        else:
            plt.close(fig)
            return ChartResponse(
                success=True,
                chart_type=request.chart_type,
                format="json",
                data=json.dumps({"labels": labels, "values": values}),
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Chart rendering failed: %s", exc)
        raise HTTPException(status_code=500, detail="Chart rendering failed.")


@router.post("/mermaid", response_class=HTMLResponse)
async def create_mermaid(request: MermaidRequest):
    """Rendert ein Mermaid-Diagramm."""
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: 'default',
            securityLevel: 'strict'
        }});
    </script>
    <style>
        body {{ margin: 20px; font-family: system-ui, sans-serif; }}
        .mermaid {{ display: flex; justify-content: center; }}
    </style>
</head>
<body>
    {f"<h2>{escape(request.title)}</h2>" if request.title else ""}
    <div class="mermaid">
{request.code}
    </div>
</body>
</html>"""
    return HTMLResponse(content=html_content)


@router.get("/chart/types")
async def get_chart_types():
    """Gibt verfügbare Chart-Typen zurück."""
    return {
        "chart_types": [
            {"id": "line", "name": "Liniendiagramm", "icon": "📈"},
            {"id": "bar", "name": "Balkendiagramm", "icon": "📊"},
            {"id": "pie", "name": "Kreisdiagramm", "icon": "🥧"},
            {"id": "scatter", "name": "Streudiagramm", "icon": "⚫"},
            {"id": "area", "name": "Flächendiagramm", "icon": "🗻"},
        ],
        "mermaid_types": [
            {"id": "flowchart", "name": "Flussdiagramm"},
            {"id": "sequence", "name": "Sequenzdiagramm"},
            {"id": "gantt", "name": "Gantt-Diagramm"},
            {"id": "pie", "name": "Kreisdiagramm (Mermaid)"},
            {"id": "class", "name": "Klassendiagramm"},
            {"id": "state", "name": "Zustandsdiagramm"},
        ],
    }


@router.post("/chart/interactive")
async def create_interactive_chart(request: ChartRequest):
    """Erstellt ein interaktives Plotly-Diagramm."""
    try:
        import plotly.graph_objects as go
        import plotly.io as pio

        labels = [d.label for d in request.data]
        values = [d.value for d in request.data]

        if request.chart_type == "pie":
            fig = go.Figure(data=[go.Pie(labels=labels, values=values)])
        elif request.chart_type == "bar":
            fig = go.Figure(data=[go.Bar(x=labels, y=values)])
        else:
            fig = go.Figure(data=[go.Scatter(x=labels, y=values, mode="lines+markers")])

        fig.update_layout(
            title=request.title,
            xaxis_title=request.x_label,
            yaxis_title=request.y_label,
            template="plotly_white",
        )

        html = pio.to_html(fig, full_html=True, include_plotlyjs="cdn")
        return HTMLResponse(content=html)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
