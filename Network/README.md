# Network (MQTT relay)

Minimal Host ↔ Edge relay + discovery cache. Normally runs on the NUC next to Mosquitto; can run on Vector when the NUC is down.

## Quick start

```bash
# Mosquitto must be reachable on BROKER:PORT (defaults below).
python3 Network/server.py
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `VICA_MQTT_BROKER` | `localhost` | Broker the relay connects to |
| `VICA_MQTT_PORT` | `1883` | Broker port |
| `VICA_NUC_VERBOSE` | `0` | Extra relay logs |

## NUC down / Vector failover

1. On Vector, ensure Mosquitto listens on **`0.0.0.0`** (not only `127.0.0.1`).  
   If port `1883` is stuck on localhost, run a second listener on **`1884`**.
2. Start the relay on Vector:
   ```bash
   VICA_MQTT_BROKER=127.0.0.1 VICA_MQTT_PORT=1884 python3 Network/server.py
   ```
3. Host on Vector: `VICA_MQTT_BROKER=127.0.0.1 VICA_MQTT_PORT=1884 ...`
4. Edge on Jetson: `VICA_MQTT_BROKER=10.148.1.35 VICA_MQTT_PORT=1884 ./start_client.sh`

Use Vector’s `10.148.x` address for Jetsons on that subnet (e.g. `10.148.1.35`), not `10.2.x`, unless the Jetson can route there.
