import os
import sys
from pathlib import Path


def _add_paths():
    here = Path(__file__).resolve().parent
    root = here.parent.parent
    host_team = root / "Host_Team"
    host_gui = host_team / "Host" / "gui"

    for path in (root, host_team, host_gui):
        p = str(path)
        if p not in sys.path:
            sys.path.insert(0, p)


def main():
    _add_paths()

    from s1_start_app import run_app, MqttBackend

    broker = os.environ.get("VICA_MQTT_BROKER", "localhost")
    port = int(os.environ.get("VICA_MQTT_PORT", "1883"))

    backend = MqttBackend(
        mqtt_broker=broker,
        mqtt_port=port,
        control_topic="host/control",
        default_reply_topic="host/results",
        request_timeout_sec=10.0,
    )

    return run_app(
        backend,
        banner="NETWORK GUI ROUTING TEST",
        discovery_reply_topic="host/results",
    )


if __name__ == "__main__":
    raise SystemExit(main())
