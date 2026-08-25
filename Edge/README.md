# Edge device (Jetson)

MQTT client + VLM inference. Subscribes to `edge/<hostname>/control` and `edge/control`.

## Quick start (after `git pull`)

```bash
cd ~/LAS-VICA/Edge
chmod +x start_client.sh

# One-time: install Python deps (pick the env you use)
source ~/cosmos/bin/activate          # thor1, if present
# OR: source .venv/bin/activate       # thor2

python3 -m pip install -r requirements.txt
# If torch fails on Jetson, skip it and use existing conda torch:
# python3 -m pip install paho-mqtt psutil opencv-python pillow "numpy>=1.24,<2" scipy

./start_client.sh
```

Confirm in the log:

```text
Device identity for targeting: 'isl-jetson-thor1'   # or thor2
Subscribed to topic 'edge/isl-jetson-thor1/control'
MODEL_READY
```

## Identity (usually no manual `export`)

`edge_device_name()` in `handler.py` uses, in order:

1. `VICA_DEVICE_NAME`
2. `VICA_EDGE_NAME`
3. `HOSTNAME`
4. `platform.node()` (Jetson hostname, e.g. `isl-jetson-thor1`)

Host discovery chip name must match this string exactly for **targeted** queries.

## Optional environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `VICA_MQTT_BROKER` | `10.148.1.35` | Lab MQTT broker (Vector `eno1`; was NUC `.64`) |
| `VICA_MQTT_PORT` | `1883` | Broker port (use `1884` if `1883` is localhost-only) |
| `AUTO_START_CONTAINER` | `0` | Set `1` to try Docker `nano-vlm` |
| `VICA_INFERENCE_TIMEOUT_SEC` | `60` | Query inference wait |
| `CAMERA_INDEX` | `0` | OpenCV index when not using GStreamer |
| `CAMERA_GSTREAMER` | (empty) | Jetson CSI pipeline (preferred on Orin/Thor) |
| `MODEL_ID` | `nvidia/Cosmos-Reason1-7B` | Hugging Face model |

## NUC down / Vector failover

If the NUC broker is unavailable, run Mosquitto + `Network/server.py` on Vector and point Edge at Vector’s `10.148.x` IP:

```bash
# On Vector (broker + relay). Prefer a listener on 0.0.0.0:1883.
# If system Mosquitto is localhost-only, use port 1884 instead.
VICA_MQTT_BROKER=127.0.0.1 VICA_MQTT_PORT=1884 python3 Network/server.py

# Host on Vector
VICA_MQTT_BROKER=127.0.0.1 VICA_MQTT_PORT=1884 python3 Host_Team/Host/gui/s1_start_app.py

# On Jetson
VICA_MQTT_BROKER=10.148.1.35 VICA_MQTT_PORT=1884 ./start_client.sh
```

Mosquitto must listen on `0.0.0.0` (not only `127.0.0.1`) or remote edges get `Connection refused`.

## Deploy from Git (Windows → Jetsons)

On **Windows** (source of truth): commit and push Edge changes on branch `Feature/TargetedEdgeRoutingClean`.

On **each Jetson**:

```bash
cd ~/LAS-VICA
git fetch origin Feature/TargetedEdgeRoutingClean
git checkout Feature/TargetedEdgeRoutingClean
git pull origin Feature/TargetedEdgeRoutingClean

pkill -f 'python.*client.py' || true
cd Edge
chmod +x start_client.sh
./start_client.sh
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Connection refused` to broker | Mosquitto localhost-only or wrong IP — use Vector `10.148.1.35`, open `0.0.0.0:1883` or `VICA_MQTT_PORT=1884` |
| `edge/EdgeDevice/control` in log | Old `client.py` — `git pull` or copy from repo |
| Targeted query timeout, broadcast OK | Wrong subscribe topic or second `client.py` process — `pkill -f client.py`, restart `./start_client.sh` |
| `no frame/results` / camera unavailable | Camera open failed — set `CAMERA_GSTREAMER` for CSI, or free `/dev/video*`; confirm `[camera] opened` in logs |
| MQTT drops during long queries | Fixed by running inference off the MQTT callback thread — update `client.py` |
| `ModuleNotFoundError: psutil` | `pip install -r requirements.txt` in the same env as `python3 client.py` |
| NumPy / SciPy `Inf` import error | `pip install "numpy>=1.24,<2" scipy` inside `.venv` (not system scipy + numpy 2.x) |
| `AutoModelForVision2Seq` missing | Use current `model_init.py` (ImageTextToText fallback) |
