import sys
from pathlib import Path


def _add_paths() -> None:
    here = Path(__file__).resolve().parent
    root = here.parent.parent
    host_team = root / "Host_Team"
    host_gui = host_team / "Host" / "gui"

    for path in (root, host_team, host_gui, here):
        p = str(path)
        if p not in sys.path:
            sys.path.insert(0, p)


def main() -> int:
    _add_paths()

    from s1_start_app import run_app
    from network_targeting_demo_backend import NetworkTargetingDemoBackend

    backend = NetworkTargetingDemoBackend()
    return run_app(
        backend,
        banner="NETWORK OFFLINE TARGETING TEST (NO MQTT BROKER)",
        discovery_reply_topic="host/results",
    )


if __name__ == "__main__":
    raise SystemExit(main())
