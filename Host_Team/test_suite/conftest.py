"""
Test-only sys.path setup for the Host_Team package's test suite.

host_client.py lives directly in Host_Team/ and imports with bare names
the way it's run in production (``python host_client.py``); gui_handler.py
and demo_query.py live under Host_Team/Host/gui/. Both directories need to
be importable without modifying the production modules themselves.
"""

import sys
from pathlib import Path

HOST_TEAM_DIR = Path(__file__).resolve().parents[1]
GUI_DIR = HOST_TEAM_DIR / "Host" / "gui"

for path in (HOST_TEAM_DIR, GUI_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
