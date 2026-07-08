"""
Tests für den Frontend-Fallback in api/routes_modules.py.

Fehlt tab.html eines Moduls, liefert der Endpoint 200 mit dem Marker
"ninko:no-dashboard", damit das Frontend den lokalisierten Empty-State
rendert (Regression: vorher hartkodierter deutscher Text ohne Marker).
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.routes_modules import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_missing_tab_html_returns_marker(client):
    res = client.get("/api/modules/does_not_exist/frontend/tab.html")
    assert res.status_code == 200
    assert "ninko:no-dashboard" in res.text
    assert "empty-state" in res.text


def test_missing_tab_js_returns_registration_stub(client):
    res = client.get("/api/modules/does_not_exist/frontend/tab.js")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/javascript")
    assert "Ninko._pluginTabs" in res.text


def test_disallowed_filename_rejected(client):
    res = client.get("/api/modules/does_not_exist/frontend/evil.txt")
    assert res.status_code == 403
