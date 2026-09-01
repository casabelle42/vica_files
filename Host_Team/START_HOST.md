# Start Host (lab)

Pull this branch, install deps once, then run the Host GUI — no manual broker/port setup.

## Setup (once)

```powershell
git fetch origin
git checkout feature/host-lab-launcher
cd Host_Team
pip install -r requirements.txt
```

## Run

**Windows — double-click or terminal:**

```powershell
.\start_host.bat
```

Or:

```powershell
.\start_host.ps1
```

**Linux / macOS / Git Bash:**

```bash
chmod +x start_host.sh   # once
./start_host.sh
```

**Direct Python (same lab defaults on this branch):**

```powershell
python Host/gui/s1_start_app.py
```

## Defaults on this branch

| Setting | Value |
|---------|-------|
| Broker | `10.148.1.35` |
| Port | `1884` |

Override before running if needed:

```powershell
$env:VICA_MQTT_PORT = "1883"; .\start_host.ps1
```

```bash
VICA_MQTT_PORT=1883 ./start_host.sh
```

## Notes

- Git pull does **not** auto-open the GUI — run one of the commands above.
- Edge devices must also use port **1884** to reach the same lab broker.
- Relay server on Vector: `VICA_MQTT_PORT=1884 python Network/server.py`
