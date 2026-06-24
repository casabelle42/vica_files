# LAS-VICA Team Member Lab Runbook

This guide is for team members setting up, integrating, and running LAS-VICA in the lab.

Use this when you need to:
- verify your laptop and lab network setup
- start all required services in the correct order
- run each script on the correct machine
- use the GUI to discover devices and query models

## 1. System Roles (What Runs Where)

- Host Laptop (analyst GUI):
  - Runs Host GUI and sends discovery/query requests.
  - Main script: `Host_Team/Host/gui/s1_start_app.py`

- NUC / Network Relay machine:
  - Runs MQTT relay/router and discovery cache.
  - Main script: `Network/server.py`
  - Must have an MQTT broker reachable on port `1883`.

- Edge Device(s) (Jetson or edge box):
  - Runs edge MQTT client + handler + model service.
  - Main script: `Edge/client.py`
  - `handler.py` and `model_init.py` are launched by `client.py`.

- Optional test/mock components:
  - Mock edge fleet: `Network/test_suite/mock_edge_fleet.py`
  - One-command integration harness: `Network/test_suite/run_all_gui_routing_test.py`
  - Offline GUI test (no broker): `Network/test_suite/run_gui_targeting_offline.py`

## 2. Lab Network Pre-Flight Checklist

Before running any scripts, complete this checklist on each machine.

1. Confirm all machines are on the lab network.
2. Confirm all machines can reach the broker machine.
3. Confirm no firewall rule is blocking TCP `1883`.
4. Confirm all machines are time-synced (for clean logs).
5. Confirm Python environments are activated.

### 2.1 Quick Connectivity Checks

Run on each machine (PowerShell or terminal):

```powershell
ipconfig
ping <BROKER_IP>
```

Optional port check from Windows:

```powershell
Test-NetConnection <BROKER_IP> -Port 1883
```

Expected:
- `ping` succeeds
- port `1883` is reachable from Host and Edge machines

## 3. Python Environment Setup

## 3.1 Host Laptop Setup

From repo root:

```powershell
cd Host_Team
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 3.2 Network/NUC Setup

From repo root:

```bash
cd Network
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3.3 Edge Setup

From repo root:

```bash
cd Edge
python -m venv .venv
source .venv/bin/activate
pip install paho-mqtt psutil opencv-python pillow numpy torch transformers
```

Note:
- The edge model path depends on Docker + GPU runtime + camera access.
- Jetson-specific model/container setup is documented in:
  - `Demo_Files/VILA Installation Guide/VILA_Jetson_Setup_Guide.md`

## 4. Environment Variables (Recommended)

Set these on Host and Edge before launch:

- `VICA_MQTT_BROKER=<BROKER_IP>`
- `VICA_MQTT_PORT=1883`

Optional on Edge:

- `VICA_EDGE_NAME=Edge-Cam-01` (or unique per edge machine)

Optional on Host:

- `VICA_HOST_ID=<host-name>`

Example (PowerShell):

```powershell
$env:VICA_MQTT_BROKER="10.148.0.95"
$env:VICA_MQTT_PORT="1883"
```

Example (bash):

```bash
export VICA_MQTT_BROKER=10.148.0.95
export VICA_MQTT_PORT=1883
export VICA_EDGE_NAME=Edge-Cam-01
```

## 5. Startup Order (Lab Integration)

Always start services in this order.

1. MQTT Broker
2. NUC Relay (`Network/server.py`)
3. Edge client(s) (`Edge/client.py`)
4. Host GUI (`Host_Team/Host/gui/s1_start_app.py`)

## 5.1 Start MQTT Broker

If your NUC already runs a broker service, just verify it is active.

If needed (example using Mosquitto):

```bash
mosquitto -v
```

## 5.2 Start NUC Relay

On NUC machine, from repo root:

```bash
python Network/server.py
```

Expected logs:
- connected to broker
- subscribed to `host/control`, `edge/results`, `edge/status`

## 5.3 Start Edge Client(s)

On each edge machine, from repo root:

```bash
python Edge/client.py
```

Expected logs:
- connected to broker
- subscribed to:
  - `edge/<DEVICE_NAME>/control`
  - `edge/control`
- periodic publishes to `edge/status`

## 5.4 Start Host GUI

On Host laptop, from repo root:

```powershell
python Host_Team/Host/gui/s1_start_app.py
```

Expected startup banner includes:
- broker and port
- control topic (`edge/control`)

## 6. First-Time GUI Workflow (Using the Model)

After GUI opens:

1. Click `Discover`.
2. Confirm edge devices appear in the Available Devices list.
3. Select target devices with checkboxes (or leave unselected for broadcast).
4. Open Query window.
5. Enter a natural language query and press Enter.
6. Confirm pending indicator appears.
7. Confirm query responses appear with:
  - image preview
  - response metadata
  - edge device source

Expected behavior:
- If targets are selected, only those edges respond.
- If no targets are selected, query broadcasts to all edges.

## 7. Quick Troubleshooting

## 7.1 No devices shown after Discover

Checks:
1. NUC relay is running.
2. Edge clients are running and publishing status.
3. Host and edge use same broker IP/port.
4. Broker is reachable from host and edges.

## 7.2 Query stuck on pending

Checks:
1. At least one edge is online.
2. Selected target devices are actually online.
3. Edge logs show query received.
4. NUC logs show routing to selected edge(s).

## 7.3 Edge fails on model startup

Checks:
1. Docker runtime is configured for NVIDIA.
2. Camera is accessible (`/dev/video0` or configured source).
3. Jetson memory/swap setup completed.
4. Follow Jetson guide in `Demo_Files/VILA Installation Guide/VILA_Jetson_Setup_Guide.md`.

## 8. Script Reference: What To Run vs What Not To Run

Run directly:
- `Network/server.py`
- `Edge/client.py`
- `Host_Team/Host/gui/s1_start_app.py`

Do not run directly for normal lab flow (imported by other scripts):
- `Edge/handler.py`
- `Edge/model_init.py`

Optional test scripts:
- `Network/test_suite/run_all_gui_routing_test.py`
- `Network/test_suite/mock_edge_fleet.py`
- `Network/test_suite/run_gui_routing_test.py`
- `Network/test_suite/run_gui_targeting_offline.py`

## 9. Standard Lab Bring-Up (Short Version)

Use this if you already know the system.

1. Export `VICA_MQTT_BROKER` and `VICA_MQTT_PORT` on Host/Edge.
2. Start broker.
3. Start `python Network/server.py`.
4. Start one or more `python Edge/client.py`.
5. Start `python Host_Team/Host/gui/s1_start_app.py`.
6. In GUI: Discover -> select targets -> send query.

If all six steps pass, the lab stack is operational.
