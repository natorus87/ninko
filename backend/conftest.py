"""
Root-conftest für alle Ninko-Tests (backend/).

Zieht die Test-Isolation eine Ebene höher als tests/conftest.py, damit auch
die Test-Dateien im backend-Root (test_alert_state.py, test_monitor.py, …)
die sicheren Settings-Defaults bekommen. pytest lädt conftest-Dateien
hierarchisch: diese hier greift für den gesamten backend/-Baum.

WICHTIG: Diese Env-Vars MÜSSEN auf Modul-Ebene gesetzt werden, bevor das erste
`core.*`-Modul geladen wird — viele Test-Module importieren transitiv
`core.config`, das lazy `CoreSettings()` instantiiert. Ohne diese Vars wirft
der Security-Validator ein ValueError. conftest.py wird beim Collect zuerst
geladen, daher ist dies der richtige Ort.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SESSION_SECRET", "x" * 32)
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "test-admin-password-for-unit-tests")
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password-for-unit-tests")
os.environ.setdefault("DEPLOYMENT_ENV", "development")
os.environ.setdefault("API_AUTH_ENABLED", "false")
os.environ.setdefault("CHROMADB_HOST", "localhost")
os.environ.setdefault("CHROMADB_PORT", "8000")

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
