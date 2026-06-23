from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.config import CoreSettings


def test_production_rejects_insecure_auth_defaults() -> None:
    with pytest.raises(ValidationError):
        CoreSettings(
            DEPLOYMENT_ENV="production",
            API_AUTH_ENABLED=True,
            SESSION_SECRET="change-me-in-production",
            BOOTSTRAP_ADMIN_PASSWORD="admin",
            ADMIN_PASSWORD="",
            SESSION_COOKIE_SECURE=False,
        )


def test_development_warns_but_allows_defaults() -> None:
    settings = CoreSettings(
        DEPLOYMENT_ENV="development",
        API_AUTH_ENABLED=True,
        SESSION_SECRET="x" * 32,
        BOOTSTRAP_ADMIN_PASSWORD="admin",
        ADMIN_PASSWORD="",
        SESSION_COOKIE_SECURE=False,
    )

    assert settings.DEPLOYMENT_ENV == "development"
