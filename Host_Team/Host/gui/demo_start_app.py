#!/usr/bin/env python3
"""
Host Demo Entrypoint (offline, no broker required)
--------------------------------------------------
Boots the same PyQt GUI as ``s1_start_app.py`` but routes every "edge / server"
interaction through ``DemoBackend`` instead of MQTT.

Usage
─────
    python demo_start_app.py

What you can demo without any network or broker:
    1. Click "Discover" — four fake edge devices appear in the list.
    2. Tick checkboxes on one or more devices to mark them as targets.
    3. Open the Query window, type any prompt, press Enter.
       • One staggered fake response per selected device arrives.
       • With nothing selected, a single broadcast response arrives.

Implementation note
───────────────────
This file deliberately contains *only* the wiring needed to boot demo mode.
All GUI behaviour lives in ``s1_start_app.run_app(backend)``; we just hand it
a different backend. Production code paths in ``s1_start_app.py`` are
completely untouched by demo mode.

To remove demo mode entirely from the project, delete:
    • Host_Team/Host/gui/demo_start_app.py   (this file)
    • Host_Team/Host/gui/demo_query.py
…and you're done — nothing in the production stack imports either of them.
"""

import os
import sys


# ---- Path bootstrap (same logic as s1_start_app.py so this script is runnable
# directly from any working directory) ----
current_dir   = os.path.dirname(os.path.abspath(__file__))
host_dir      = os.path.dirname(current_dir)        # Host/
host_team_dir = os.path.dirname(host_dir)           # Host_Team/
project_root  = os.path.dirname(host_team_dir)      # project root

for path in [current_dir, host_dir, host_team_dir, project_root]:
    if path not in sys.path:
        sys.path.insert(0, path)

from s1_start_app import run_app   # reuse the entire production GUI wiring  # noqa: E402
from demo_query import DemoBackend  # noqa: E402


def main() -> int:
    banner = "\n".join([
        "VICA Host — DEMO MODE (offline)",
        "Backend: DemoBackend (no MQTT broker, no edge devices required)",
        "Click 'Discover' to load fake devices, then send a query.",
    ])
    backend = DemoBackend()
    return run_app(backend, banner=banner)


if __name__ == "__main__":
    sys.exit(main())
