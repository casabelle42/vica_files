#!/usr/bin/env python3
"""
NUC MQTT Relay + Discovery (minimal)

- Host -> Edge forwarded (except discovery)
- Edge results -> Host forwarded
- Edge status -> cached
- Host discovery -> NUC replies with discovery_response from cache
"""

import json
import time
import paho.mqtt.client as mqtt

BROKER = "localhost"
PORT = 1883

HOST_TO_SERVER = "host/control"
SERVER_TO_EDGE = "edge/control"

EDGE_TO_SERVER = "edge/results"
SERVER_TO_HOST = "host/results"

EDGE_STATUS = "edge/status"   


device_cache = {}  


def safe_json(payload: bytes):
    try:
        return json.loads(payload.decode("utf-8"))
    except Exception:
        return None


def make_discovery_response(server_name: str = "NUC"):
    # Build the list in the format your Host expects
    devices = []
    now = time.time()

    for name, entry in device_cache.items():
        body = entry["body"]
        last_seen = entry["last_seen"]

        devices.append({
            "name": body.get("name", name),
            "status": "online" if (now - last_seen) < 10 else "offline",
            "cpu": body.get("cpu", 0.0),
            "ram": body.get("ram", 0.0),
            "gpu": body.get("gpu", 0.0),
            "network_strength": body.get("network_strength", -100),
            "isProcessing": body.get("isProcessing", False),
        })

    return {
        "header": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source_device": server_name,
            "message_type": "discovery_response"
        },
        "body": {"devices": devices}
    }


def on_connect(client, userdata, flags, rc):
    print("[NUC] Connected to broker")
    result = client.subscribe([
        (HOST_TO_SERVER, 0),
        (EDGE_TO_SERVER, 0),
        (EDGE_STATUS, 0),   
    ])
    print(f"[NUC] Subscribe result: {result}")

def on_message(client, userdata, msg):
    # 1) Host -> NUC
    print(f"[NUC] *** RAW MESSAGE *** topic={msg.topic} payload={msg.payload[:200]}")  # add this line 1
    
    if msg.topic == HOST_TO_SERVER:
        pkt = safe_json(msg.payload)
        print(f"[NUC] Parsed packet: {pkt}")  # add this
        print(f"[NUC] Message type: {pkt.get('header', {}).get('message_type') if pkt else 'PARSE FAILED'}")  # add this

        if isinstance(pkt, dict) and pkt.get("header", {}).get("message_type") == "discovery":
            resp = make_discovery_response(server_name="NUC")
            print(f"[NUC] Publishing discovery_response to {SERVER_TO_HOST}: {json.dumps(resp)[:200]}")  # add this
            result = client.publish(SERVER_TO_HOST, json.dumps(resp).encode("utf-8"))
            print(f"[NUC] Publish result: rc={result.rc}")  # add this
            print("[NUC] Host discovery → sent discovery_response")
            return

        client.publish(SERVER_TO_EDGE, msg.payload)
        print("[NUC] Host → Edge forwarded")
        return

    # 2) Edge results 
    if msg.topic == EDGE_TO_SERVER:
        client.publish(SERVER_TO_HOST, msg.payload)
        print("[NUC] Edge → Host forwarded")
        return

    # 3) Edge status -> cache only
    if msg.topic == EDGE_STATUS:
        pkt = safe_json(msg.payload)
        if isinstance(pkt, dict) and pkt.get("header", {}).get("message_type") == "device_status":
            name = pkt.get("body", {}).get("name") or pkt.get("header", {}).get("source_device") or "unknown"
            device_cache[name] = {"body": pkt.get("body", {}), "last_seen": time.time()}
            print(f"[NUC] Cached status for {name}")
        return


def main():
    client = mqtt.Client(client_id="vica-nuc-relay")
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER, PORT, 60)
    print("[NUC] Relay running...")
    client.loop_forever()


if __name__ == "__main__":
    main()
 