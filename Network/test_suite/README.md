# Network Test Suite

This folder provides a real test harness for Network relay routing with and without GUI.

## Files

- `test_server_routing.py`: unit-style tests for `Network/server.py` routing behavior.
- `mock_edge_fleet.py`: spins up multiple fake edge devices using real MQTT topics.
- `run_gui_routing_test.py`: launches Host GUI against real MQTT relay path.
- `run_all_gui_routing_test.py`: one-command helper that starts relay + mock edges + GUI, then cleans up on exit.
- `network_targeting_demo_backend.py`: offline backend that simulates discovery + targeted query responses (no broker).
- `run_gui_targeting_offline.py`: launches GUI with offline targeting backend (Host-team style).
- `test_offline_targeting_backend.py`: pytest checks for offline targeted/broadcast behavior.

## What This Verifies

1. Targeted query requests route only to selected edge topics.
2. Broadcast behavior is preserved when `target_devices` is missing/empty.
3. Discovery/status/result relay paths still work.
4. GUI selection from discovery page can be tested against real relay topics.
5. GUI selection can also be tested offline without MQTT broker.

## Prerequisites

- MQTT broker running (default: `localhost:1883`)
- Python dependencies:
  - `paho-mqtt`
  - `pytest`
  - GUI deps already used by Host GUI (PyQt6 etc.)

Install test deps:

```bash
pip install pytest paho-mqtt
```

## Run Order (GUI + Real Relay)

1. Start MQTT broker.
2. Start Network relay:

```bash
python Network/server.py
```

3. Start mock edge fleet:

```bash
python Network/test_suite/mock_edge_fleet.py
```

4. Start GUI routing test app:

```bash
python Network/test_suite/run_gui_routing_test.py
```

5. In GUI:
- Click Discover
- Select one device
- Click Query and send text

Expected: only selected edge responds.

## One-Command GUI Flow

From repo root:

```bash
python Network/test_suite/run_all_gui_routing_test.py
```

Optional args:

```bash
python Network/test_suite/run_all_gui_routing_test.py --broker localhost --port 1883 --edge-count 3
```

## Offline GUI Flow (No Broker Required)

This is the Host-team style simulation path.

```bash
python Network/test_suite/run_gui_targeting_offline.py
```

In GUI:
- Discover devices
- Select one edge
- Send query

Expected: only selected edge responds.

If no target is selected, behavior is broadcast across all demo edges.

## Run Unit-Style Routing Tests

From repo root:

```bash
pytest -q Network/test_suite/test_server_routing.py
```

These tests call `Network/server.py:on_message` directly with fake MQTT message objects.

Run offline backend tests:

```bash
pytest -q Network/test_suite/test_offline_targeting_backend.py
```

## Environment Variables

- `VICA_MQTT_BROKER` (default `localhost`)
- `VICA_MQTT_PORT` (default `1883`)
- `VICA_TEST_EDGE_COUNT` (default `3`, for mock fleet)
