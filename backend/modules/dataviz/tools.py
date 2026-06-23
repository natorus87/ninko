"""
Tools für DataViz Modul - Chart-Generierung.
"""

import base64
import io
import json
from langchain.tools import tool

from agents.base_agent import _t


def _ensure_matplotlib() -> None:
    import matplotlib

    matplotlib.use("Agg")


@tool
def create_line_chart(
    data_json: str, title: str, x_label: str = "", y_label: str = ""
) -> str:
    """
    Erstellt ein Liniendiagramm aus JSON-Daten.

    Args:
        data_json: JSON-Array mit {"label": "...", "value": number}
        title: Titel des Diagramms
        x_label: Beschriftung X-Achse
        y_label: Beschriftung Y-Achse

    Returns:
        Base64-kodiertes PNG-Bild als Data-URL
    """
    try:
        _ensure_matplotlib()
        import matplotlib.pyplot as plt

        data = json.loads(data_json)
        labels = [d["label"] for d in data]
        values = [d["value"] for d in data]

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(labels, values, marker="o", linewidth=2, markersize=6)
        ax.set_title(title, fontsize=14, fontweight="bold")
        if x_label:
            ax.set_xlabel(x_label)
        if y_label:
            ax.set_ylabel(y_label)
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()

        buffer = io.BytesIO()
        plt.savefig(buffer, format="png", dpi=100, bbox_inches="tight")
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode()
        plt.close(fig)

        return f"data:image/png;base64,{image_base64}"
    except Exception as e:
        return _t(
            de=f"Fehler beim Erstellen des Liniendiagramms: {e}",
            en=f"Error creating line chart: {e}",
        )


@tool
def create_bar_chart(
    data_json: str, title: str, x_label: str = "", y_label: str = ""
) -> str:
    """
    Erstellt ein Balkendiagramm aus JSON-Daten.

    Args:
        data_json: JSON-Array mit {"label": "...", "value": number}
        title: Titel des Diagramms
        x_label: Beschriftung X-Achse
        y_label: Beschriftung Y-Achse

    Returns:
        Base64-kodiertes PNG-Bild als Data-URL
    """
    try:
        _ensure_matplotlib()
        import matplotlib.pyplot as plt

        data = json.loads(data_json)
        labels = [d["label"] for d in data]
        values = [d["value"] for d in data]

        fig, ax = plt.subplots(figsize=(10, 6))
        bars = ax.bar(labels, values, color="steelblue", edgecolor="navy")
        ax.set_title(title, fontsize=14, fontweight="bold")
        if x_label:
            ax.set_xlabel(x_label)
        if y_label:
            ax.set_ylabel(y_label)

        # Werte auf Balken anzeigen
        for bar in bars:
            height = bar.get_height()
            ax.annotate(
                f"{height:.1f}",
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=9,
            )

        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()

        buffer = io.BytesIO()
        plt.savefig(buffer, format="png", dpi=100, bbox_inches="tight")
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode()
        plt.close(fig)

        return f"data:image/png;base64,{image_base64}"
    except Exception as e:
        return _t(
            de=f"Fehler beim Erstellen des Balkendiagramms: {e}",
            en=f"Error creating bar chart: {e}",
        )


@tool
def create_pie_chart(data_json: str, title: str) -> str:
    """
    Erstellt ein Kreisdiagramm aus JSON-Daten.

    Args:
        data_json: JSON-Array mit {"label": "...", "value": number}
        title: Titel des Diagramms

    Returns:
        Base64-kodiertes PNG-Bild als Data-URL
    """
    try:
        _ensure_matplotlib()
        import matplotlib.pyplot as plt

        data = json.loads(data_json)
        labels = [d["label"] for d in data]
        values = [d["value"] for d in data]

        fig, ax = plt.subplots(figsize=(8, 8))
        colors = plt.cm.Set3(range(len(labels)))
        wedges, texts, autotexts = ax.pie(
            values, labels=labels, autopct="%1.1f%%", colors=colors, startangle=90
        )
        ax.set_title(title, fontsize=14, fontweight="bold")
        plt.tight_layout()

        buffer = io.BytesIO()
        plt.savefig(buffer, format="png", dpi=100, bbox_inches="tight")
        buffer.seek(0)
        image_base64 = base64.b64encode(buffer.read()).decode()
        plt.close(fig)

        return f"data:image/png;base64,{image_base64}"
    except Exception as e:
        return _t(
            de=f"Fehler beim Erstellen des Kreisdiagramms: {e}",
            en=f"Error creating pie chart: {e}",
        )


@tool
def create_mermaid_diagram(mermaid_code: str, title: str = "") -> str:
    """
    Rendert ein Mermaid-Diagramm als SVG.

    Args:
        mermaid_code: Gültiger Mermaid-Diagramm-Code
        title: Optionaler Titel

    Returns:
        SVG-Code oder HTML mit eingebettetem Diagramm
    """
    try:
        # Mermaid wird im Frontend gerendert, hier geben wir den Code zurück
        # Das Frontend hat Mermaid.js eingebunden
        html_template = f"""<!DOCTYPE html>
<html>
<head>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <script>mermaid.initialize({{startOnLoad:true}});</script>
    <style>body{{margin:20px;font-family:system-ui}}</style>
</head>
<body>
    {f"<h2>{title}</h2>" if title else ""}
    <div class="mermaid">
{mermaid_code}
    </div>
</body>
</html>"""
        return html_template
    except Exception as e:
        return _t(
            de=f"Fehler beim Erstellen des Mermaid-Diagramms: {e}",
            en=f"Error creating mermaid diagram: {e}",
        )


@tool
def create_interactive_chart_plotly(data_json: str, chart_type: str, title: str) -> str:
    """
    Erstellt ein interaktives Diagramm mit Plotly.

    Args:
        data_json: JSON-Array mit {"label": "...", "value": number, "category": "..."}
        chart_type: "line", "bar", "scatter", "pie", "area"
        title: Titel des Diagramms

    Returns:
        HTML-Code mit eingebettetem Plotly-Chart
    """
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
        import json

        data = json.loads(data_json)

        if chart_type == "pie":
            fig = go.Figure(
                data=[
                    go.Pie(
                        labels=[d["label"] for d in data],
                        values=[d["value"] for d in data],
                        title=title,
                    )
                ]
            )
        elif chart_type == "bar":
            fig = go.Figure(
                data=[
                    go.Bar(
                        x=[d["label"] for d in data],
                        y=[d["value"] for d in data],
                        marker_color="steelblue",
                    )
                ]
            )
            fig.update_layout(title=title, xaxis_title="Kategorie", yaxis_title="Wert")
        elif chart_type in ["line", "area"]:
            fig = go.Figure(
                data=[
                    go.Scatter(
                        x=[d["label"] for d in data],
                        y=[d["value"] for d in data],
                        mode="lines+markers",
                        fill="tozeroy" if chart_type == "area" else None,
                        line=dict(color="steelblue", width=2),
                    )
                ]
            )
            fig.update_layout(title=title, xaxis_title="Zeit", yaxis_title="Wert")
        else:
            fig = go.Figure(
                data=[
                    go.Scatter(
                        x=[d["label"] for d in data],
                        y=[d["value"] for d in data],
                        mode="markers",
                    )
                ]
            )
            fig.update_layout(title=title)

        html = pio.to_html(fig, full_html=True, include_plotlyjs="cdn")
        return html
    except Exception as e:
        return _t(
            de=f"Fehler beim Erstellen des Plotly-Charts: {e}",
            en=f"Error creating Plotly chart: {e}",
        )


@tool
def analyze_data_for_chart(text_data: str, suggested_type: str = "auto") -> str:
    """
    Analysiert Textdaten und schlägt einen Chart-Typ vor.

    Args:
        text_data: Rohe Textdaten (z.B. aus Websuche)
        suggested_type: "auto", "line", "bar", "pie"

    Returns:
        JSON mit analysierten Daten und Chart-Empfehlung
    """
    try:
        import re

        # Suche nach Zahlenwerten im Text
        numbers = re.findall(r"(\d+(?:\.\d+)?)", text_data)

        # Suche nach Daten/Zeitangaben
        dates = re.findall(
            r"(\d{4}-\d{2}-\d{2}|\d{2}\.\d{2}\.\d{4}|\w+ \d{4})", text_data
        )

        # Suche nach Kategorien (Wörter gefolgt von Zahlen)
        categories = re.findall(r"(\w+):?\s*(\d+(?:\.\d+)?)", text_data)

        result = {
            "numbers_found": len(numbers),
            "dates_found": len(dates),
            "categories_found": len(categories),
            "suggested_chart": "bar",
            "extracted_data": [],
        }

        if len(dates) > 3:
            result["suggested_chart"] = "line"
        elif len(categories) > 0 and len(categories) <= 10:
            result["suggested_chart"] = "pie"

        # Extrahiere Datenpunkte
        for cat, val in categories[:20]:
            result["extracted_data"].append({"label": cat, "value": float(val)})

        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
