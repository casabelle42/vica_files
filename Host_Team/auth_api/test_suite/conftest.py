"""
Test-only setup for the Auth API test suite.

app.py builds its SQLAlchemy engine at import time from DATABASE_URL (or a
SQLite file next to app.py if unset). To keep tests isolated and off the
developer's real auth_local.db, we point DATABASE_URL at a fresh temp file
*before* importing app.py, then reload the module between tests so each
test gets its own empty database instead of accumulating users across the
whole session.
"""

import importlib
import sys
from pathlib import Path

import pytest

AUTH_API_DIR = Path(__file__).resolve().parents[1]
if str(AUTH_API_DIR) not in sys.path:
    sys.path.insert(0, str(AUTH_API_DIR))


@pytest.fixture
def auth_app_module(tmp_path, monkeypatch):
    db_path = tmp_path / "test_auth.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    if "app" in sys.modules:
        module = importlib.reload(sys.modules["app"])
    else:
        module = importlib.import_module("app")
    yield module
