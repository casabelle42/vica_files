#!/usr/bin/env python3
"""
NUC MQTT Relay + Discovery (minimal)

- Host -> Edge forwarded (except discovery)
- Edge results -> Host forwarded
- Edge status -> cached
- Host discovery -> NUC replies with discovery_response from cache
"""

import json
import os
import time
import paho.mqtt.client as mqtt
from paho.mqtt.client import CallbackAPIVersion

BROKER = "localhost"
PORT = 1883

HOST_TO_SERVER = "host/control"
SERVER_TO_EDGE = "edge/control"

EDGE_TO_SERVER = "edge/results"
SERVER_TO_HOST = "host/results"

EDGE_STATUS = "edge/status"   

VERBOSE = os.environ.get("VICA_NUC_VERBOSE", "0").strip() not in ("0", "", "false", "False", "no", "No")

device_cache = {}  


def safe_json(payload: bytes):
    try:
        return json.loads(payload.decode("utf-8"))
    except Exception:
        return None


def normalize_target_devices(body) -> list[str]:
    """Return a list of edge device names from query_request body."""
    if not isinstance(body, dict):
        return []
    td = body.get("target_devices")
    if isinstance(td, str) and td.strip():
        return [td.strip()]
    if isinstance(td, list):
        return [str(t).strip() for t in td if isinstance(t, str) and str(t).strip()]
    ts = body.get("target_device")
    if isinstance(ts, str) and ts.strip():
        return [ts.strip()]
    return []


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


def on_connect(client, userdata, flags, reason_code, properties):
    print(f"[NUC] Connected to broker (reason_code={reason_code})")
    result = client.subscribe([
        (HOST_TO_SERVER, 0),
        (EDGE_TO_SERVER, 0),
        (EDGE_STATUS, 0),   
    ])
    print(f"[NUC] Subscribe result: {result}")
    if VERBOSE:
        print(f"[NUC] on_connect flags={flags} properties={properties}")

def on_message(client, userdata, msg):
    # 1) Host -> NUC
    if VERBOSE:
        print(f"[NUC] *** RAW MESSAGE *** topic={msg.topic} payload={msg.payload[:200]}")
    
    if msg.topic == HOST_TO_SERVER:
        pkt = safe_json(msg.payload)
        if VERBOSE:
            print(f"[NUC] Parsed packet: {pkt}")
            print(f"[NUC] Message type: {pkt.get('header', {}).get('message_type') if pkt else 'PARSE FAILED'}")

        if isinstance(pkt, dict) and pkt.get("header", {}).get("message_type") == "discovery":
            resp = make_discovery_response(server_name="NUC")
            if VERBOSE:
                print(f"[NUC] Publishing discovery_response to {SERVER_TO_HOST}: {json.dumps(resp)[:200]}")
            result = client.publish(SERVER_TO_HOST, json.dumps(resp).encode("utf-8"))
            if VERBOSE:
                print(f"[NUC] Publish result: rc={result.rc}")
            print("[NUC] Host discovery → sent discovery_response")
            return

        # Device-specific routing for query_request based on target_devices
        if isinstance(pkt, dict) and pkt.get("header", {}).get("message_type") == "query_request":
            body = pkt.get("body", {}) if isinstance(pkt.get("body"), dict) else {}
            targets = normalize_target_devices(body)
            qid = body.get("query_id", "?")
            model = body.get("model")
            if targets:
                for device_name in targets:
                    device_topic = f"edge/{device_name}/control"
                    client.publish(device_topic, msg.payload)
                    print(
                        f"[NUC] Query routed → {device_topic} "
                        f"(query_id={qid}, model={model})"
                    )
                return
            print(
                f"[NUC] Query broadcast → {SERVER_TO_EDGE} "
                f"(query_id={qid}, no target_devices in body)"
            )

        # All other messages from host to edge (via broadcast topic)
        client.publish(SERVER_TO_EDGE, msg.payload)
        if VERBOSE:
            print("[NUC] Host → Edge forwarded")
        return

    # 2) Edge results 
    if msg.topic == EDGE_TO_SERVER:
        client.publish(SERVER_TO_HOST, msg.payload)
        if VERBOSE:
            print("[NUC] Edge → Host forwarded")
        return

    # 3) Edge status -> cache AND forward to host
    if msg.topic == EDGE_STATUS:
        pkt = safe_json(msg.payload)
        if isinstance(pkt, dict) and pkt.get("header", {}).get("message_type") == "device_status":
            name = pkt.get("body", {}).get("name") or pkt.get("header", {}).get("source_device") or "unknown"
            device_cache[name] = {"body": pkt.get("body", {}), "last_seen": time.time()}
            if VERBOSE:
                print(f"[NUC] Cached + forwarding status for {name}")
            client.publish(SERVER_TO_HOST, msg.payload)  # <-- add this one line
        return


def main():
    client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id="vica-nuc-relay",
    )
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER, PORT, 60)
    print("[NUC] Relay running...")
    client.loop_forever()


if __name__ == "__main__":
    main()
 