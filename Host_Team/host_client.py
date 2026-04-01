#!/usr/bin/env python3
import json
import queue
import time
import uuid
import paho.mqtt.client as mqtt


class MQTTHostClient:

    def __init__(self, mqtt_broker="localhost", mqtt_port=1883):
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port

        self.outgoing_queue = queue.Queue()
        self.incoming_queue = queue.Queue()

        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"[MQTTHostClient] ✅ Connected to {self.mqtt_broker}:{self.mqtt_port}")
            client.subscribe("host/results")
            print("[MQTTHostClient] Subscribed to host/results")
            # Send discovery immediately — subscription is confirmed before this runs
            self._publish_direct("host/control", {
                "header": {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "source_device": "host",
                    "message_id": str(uuid.uuid4()),
                    "message_type": "discovery"
                },
                "body": {}
            })
            print("[MQTTHostClient] 🔍 Sent discovery request")
        else:
            print(f"[MQTTHostClient] ❌ Connection failed rc={rc}")

    def _on_mqtt_message(self, client, userdata, msg):
        try:
            payload_str = msg.payload.decode()
            print(f"[MQTTHostClient] Received on {msg.topic}: {payload_str[:300]}")
            pkt = json.loads(payload_str)
            self.incoming_queue.put(pkt)
            self._handle_incoming(pkt)
        except Exception as e:
            print(f"[MQTTHostClient] Error handling message: {e}")

    def _handle_incoming(self, pkt):
        if not isinstance(pkt, dict):
            return
        msg_type = pkt.get("header", {}).get("message_type")

        if msg_type == "discovery_response":
            devices = pkt.get("body", {}).get("devices", [])
            print(f"\n[MQTTHostClient] 📡 Discovery response — {len(devices)} device(s):")
            for d in devices:
                icon = "🟢" if d.get("status") == "online" else "🔴"
                print(f"  {icon} {d.get('name')} | CPU: {d.get('cpu', 0):.1f}% | "
                    f"RAM: {d.get('ram', 0):.1f}% | GPU: {d.get('gpu', 0):.1f}%")

        elif msg_type == "device_status":
            body = pkt.get("body", {})
            name = body.get("name", "unknown")
            # Store latest status per device, don't print every single one
            self.device_status_cache[name] = {
                "body": body,
                "last_seen": time.time()
            }

        else:
            print(f"[MQTTHostClient] 📨 Result: {json.dumps(pkt, indent=2)}")

    def _make_header(self, message_type: str) -> dict:
        return {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source_device": "host",
            "message_id": str(uuid.uuid4()),
            "message_type": message_type
        }

    def _publish_direct(self, topic: str, pkt: dict):
        """Publish immediately — use only from on_connect or the main loop thread."""
        payload = json.dumps(pkt, separators=(",", ":"), ensure_ascii=False)
        self.mqtt_client.publish(topic, payload)

    def send_discovery(self):
        pkt = {"header": self._make_header("discovery"), "body": {}}
        self.outgoing_queue.put(("host/control", pkt))
        print("[MQTTHostClient] 🔍 Queued discovery request")

    def send_command(self, command: str, params: dict = None):
        pkt = {
            "header": self._make_header("command"),
            "body": {"command": command, "params": params or {}}
        }
        self.outgoing_queue.put(("host/control", pkt))
        print(f"[MQTTHostClient] 📤 Queued command: {command}")

    def _publish_outgoing(self):
        while not self.outgoing_queue.empty():
            topic, packet = self.outgoing_queue.get()
            try:
                payload = json.dumps(packet, separators=(",", ":"), ensure_ascii=False)
                self.mqtt_client.publish(topic, payload)
                print(f"[MQTTHostClient] Published to {topic}: {payload[:200]}")
            except Exception as e:
                print(f"[MQTTHostClient] Error publishing: {e}")

    def start(self):
        """Single entry point — connect once, loop forever."""
        self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
        self.mqtt_client.loop_start()
        print("[MQTTHostClient] Listening for messages...")
        try:
            while True:
                self._publish_outgoing()
                time.sleep(0.05)
        except KeyboardInterrupt:
            print("[MQTTHostClient] Stopped.")


if __name__ == "__main__":
    NUC_BROKER_IP = "10.148.0.95"
    NUC_BROKER_PORT = 1883

    host = MQTTHostClient(mqtt_broker=NUC_BROKER_IP, mqtt_port=NUC_BROKER_PORT)
    host.start()  # single call — connects once, handles everything