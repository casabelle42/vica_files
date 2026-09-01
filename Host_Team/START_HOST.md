# Start Host (lab)

One-command Host GUI launch after pull. Git pull does **not** auto-open the GUI.

## Setup (once)

```bash
git checkout feature/host-lab-launcher
cd Host_Team
pip install -r requirements.txt
```

## Run

**Windows (PowerShell):**

```powershell
.\start_host.ps1
```

**Linux / macOS / Git Bash:**

```bash
chmod +x start_host.sh   # once
./start_host.sh
```

## Broker defaults

The launchers set (only if unset):

| Variable           | Default      |
|--------------------|--------------|
| `VICA_MQTT_BROKER` | `10.148.1.35` |
| `VICA_MQTT_PORT`   | `1884`       |

Override before running, e.g.:

```powershell
$env:VICA_MQTT_PORT = "1883"; .\start_host.ps1
```

```bash
VICA_MQTT_PORT=1883 ./start_host.sh
```

Python defaults in `s1_start_app.py` / `host_client.py` remain unchanged (port **1883**). Edge may also need port **1884** to reach the same lab broker.
