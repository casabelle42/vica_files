#!/usr/bin/env python3
"""
Host MQTT Client

- Sends discovery requests to NUC → receives discovery_response
- Sends commands to NUC → forwarded to edge → receives results back
- Listens continuously for incoming packets on host/results
"""

import json
import queue
import time
import uuid
import paho.mqtt.client as mqtt


class MQTTHostClient:
    """
    Host-side MQTT client:
    - Publishes commands/discovery to host/control
    - Listens for responses on host/results
    """

    def __init__(self, mqtt_broker="localhost", mqtt_port=1883):
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port

        self.outgoing_queue = queue.Queue()
        self.incoming_queue = queue.Queue()

        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message

    # ------------------------
    # MQTT callbacks
    # ------------------------
    def _on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"[MQTTHostClient] ✅ Connected to {self.mqtt_broker}:{self.mqtt_port}")
            # Subscribe FIRST inside on_connect — broker confirms before we publish anything
            client.subscribe("host/results")
            print("[MQTTHostClient] Subscribed to host/results")
            # NOW safe to send discovery — subscription is guaranteed active
            self._send_discovery_on_connect()
        else:
            print(f"[MQTTHostClient] ❌ Connection failed rc={rc}")

    def _send_discovery_on_connect(self):
        """Called from on_connect — subscription is live before this fires."""
        pkt = {
            "header": {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "source_device": "host",
                "message_id": str(uuid.uuid4()),
                "message_type": "discovery"   # <-- NUC checks exactly this field
            },
            "body": {}
        }
        payload = json.dumps(pkt, separators=(",", ":"), ensure_ascii=False)
        self.mqtt_client.publish("host/control", payload)
        print("[MQTTHostClient] 🔍 Sent discovery request")

    # ------------------------
    # Incoming packet handler
    # ------------------------
    def _handle_incoming(self, pkt):
        if not isinstance(pkt, dict):
            return

        msg_type = pkt.get("header", {}).get("message_type")

        if msg_type == "discovery_response":
            devices = pkt.get("body", {}).get("devices", [])
            print(f"\n[MQTTHostClient] 📡 Discovery response — {len(devices)} device(s):")
            for d in devices:
                status_icon = "🟢" if d.get("status") == "online" else "🔴"
                print(f"  {status_icon} {d.get('name')} | "
                      f"CPU: {d.get('cpu', 0):.1f}% | "
                      f"RAM: {d.get('ram', 0):.1f}% | "
                      f"GPU: {d.get('gpu', 0):.1f}% | "
                      f"Processing: {d.get('isProcessing', False)}")
            print()

        elif msg_type == "device_status":
            body = pkt.get("body", {})
            print(f"[MQTTHostClient] 📊 Status from {body.get('name', 'unknown')} — "
                  f"CPU: {body.get('cpu', 0):.1f}% | RAM: {body.get('ram', 0):.1f}%")

        else:
            # Generic result from edge
            print(f"[MQTTHostClient] 📨 Result received: {json.dumps(pkt, indent=2)}")

    # ------------------------
    # Outgoing packet builder
    # ------------------------
    def _make_header(self, message_type: str) -> dict:
        return {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source_device": "host",
            "message_id": str(uuid.uuid4()),
            "message_type": message_type
        }

    def send_discovery(self):
        pkt = {
            "header": self._make_header("discovery"),
            "body": {}
        }
        self.outgoing_queue.put(("host/control", pkt))
        print("[MQTTHostClient] 🔍 Queued discovery request")

    def send_command(self, command: str, params: dict = None):
        pkt = {
            "header": self._make_header("command"),
            "body": {
                "command": command,
                "params": params or {}
            }
        }
        self.outgoing_queue.put(("host/control", pkt))
        print(f"[MQTTHostClient] 📤 Queued command: {command}")

    # ------------------------
    # Publish loop
    # ------------------------
    def _publish_outgoing(self):
        while not self.outgoing_queue.empty():
            topic, packet = self.outgoing_queue.get()
            try:
                payload_str = json.dumps(packet, separators=(",", ":"), ensure_ascii=False)
                self.mqtt_client.publish(topic, payload_str)
                print(f"[MQTTHostClient] Published to {topic}: {payload_str[:200]}")
            except Exception as e:
                print(f"[MQTTHostClient] Error publishing: {e}")

    # ------------------------
    # Start
    # ------------------------
    def start(self):
        try:
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.mqtt_client.loop_start()
            print("[MQTTHostClient] Listening for messages...")

            while True:
                self._publish_outgoing()
                time.sleep(0.05)

        except KeyboardInterrupt:
            print("[MQTTHostClient] Stopping...")
        except Exception as e:
            print(f"[MQTTHostClient] Error: {e}")


# ------------------------
# Run
# ------------------------
if __name__ == "__main__":
    import sys

    NUC_BROKER_IP = "10.148.0.95"  # NUC's IP
    NUC_BROKER_PORT = 1883

    host = MQTTHostClient(mqtt_broker=NUC_BROKER_IP, mqtt_port=NUC_BROKER_PORT)

    # Connect in background
    host.mqtt_client.connect(NUC_BROKER_IP, NUC_BROKER_PORT, 60)
    host.mqtt_client.loop_start()
    time.sleep(0.5)  # Let connection settle

    # Send a discovery request on startup
    host.send_discovery()

    # Main loop
    try:
        while True:
            host._publish_outgoing()
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("[MQTTHostClient] Stopped.")