"""
Regressionstest für generate_pdf_report in agents/core_tools.py:
Ohne output_path wurde der Default-Dateiname mit uuid gebaut, aber der
uuid-Import fehlte in der Funktion → NameError.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.core_tools import generate_pdf_report


@pytest.mark.asyncio
async def test_generate_pdf_report_without_output_path_does_not_crash():
    # Darf keinen NameError werfen (uuid-Import). Ergebnis ist entweder der
    # PDF-Pfad oder die "nicht verfügbar"-Meldung, falls weasyprint fehlt.
    result = await generate_pdf_report.ainvoke(
        {"title": "Regressionstest", "content_markdown": "# Hallo\nInhalt."}
    )
    assert isinstance(result, str)
    assert "NameError" not in result
