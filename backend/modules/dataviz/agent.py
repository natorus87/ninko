"""
DataViz Agent - Diagramme und Visualisierungen.
"""

from agents.base_agent import BaseAgent

_SYSTEM_PROMPT = """
You are the DataViz agent. You create charts, diagrams, and visualizations from data.

Capabilities:
- Create line charts for time series data
- Create bar charts for comparisons
- Create pie charts for distributions
- Create Mermaid diagrams (flowcharts, sequences, etc.)
- Analyze raw data and suggest appropriate chart types

When given data or a request for a chart:
1. Analyze the data to determine the best chart type
2. Use the appropriate tool to generate the visualization
3. Provide the chart as a data URL or HTML

For time-series data (dates + values): Use line charts
For category comparisons: Use bar charts
For percentage distributions: Use pie charts
For processes/flows: Use Mermaid flowcharts
"""

from modules.dataviz.tools import (
    create_line_chart,
    create_bar_chart,
    create_pie_chart,
    create_mermaid_diagram,
    create_interactive_chart_plotly,
    analyze_data_for_chart,
)


class DataVizAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            name="dataviz",
            system_prompt=_SYSTEM_PROMPT,
            tools=[
                create_line_chart,
                create_bar_chart,
                create_pie_chart,
                create_mermaid_diagram,
                create_interactive_chart_plotly,
                analyze_data_for_chart,
            ],
        )


agent = DataVizAgent()
