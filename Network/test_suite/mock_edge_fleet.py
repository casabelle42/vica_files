import os
import json
import time
import threading
from datetime import datetime

import paho.mqtt.client as mqtt


BROKER = os.environ.get("VICA_MQTT_BROKER", "localhost")
PORT = int(os.environ.get("VICA_MQTT_PORT", "1883"))
EDGE_COUNT = int(os.environ.get("VICA_TEST_EDGE_COUNT", "3"))

# tiny valid 1x1 png
IMG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WmY4lUAAAAASUVORK5CYII="


def now_iso():
    return datetime.now().isoformat()


class MockEdge:
    def __init__(self, name):
        self.name = name
        self.client = mqtt.Client(client_id=f"mock-{name}")
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.stop_ev = threading.Event()

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(f"edge/{self.name}/control")
            client.subscribe("edge/control")
            print(f"[{self.name}] subscribed to edge/{self.name}/control and edge/control")

    def start(self, connect_retries=20, retry_delay=0.5):
        last_error = None
        for _ in range(max(1, int(connect_retries))):
            try:
                self.client.connect(BROKER, PORT, 60)
                self.client.loop_start()
                threading.Thread(target=self.status_loop, daemon=True).start()
                return
            except Exception as exc:
                last_error = exc
                time.sleep(max(0.1, float(retry_delay)))
        raise RuntimeError(
            f"[{self.name}] Unable to connect to MQTT broker at {BROKER}:{PORT} after retries"
        ) from last_error

    def stop(self):
        self.stop_ev.set()
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

    def status_loop(self):
        while not self.stop_ev.is_set():
            pkt = {
                "header": {
                    "timestamp": now_iso(),
                    "source_device": self.name,
                    "message_type": "device_status",
                },
                "body": {
                    "name": self.name,
                    "cpu": 10.0,
                    "ram": 20.0,
                    "gpu": 0.0,
                    "network_strength": -55,
                    "isProcessing": False,
                    "available_models": ["dino-v2"],
                    "active_model": "dino-v2",
                },
            }
            self.client.publish("edge/status", json.dumps(pkt))
            time.sleep(1.5)

    def on_message(self, client, userdata, msg):
        try:
            pkt = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return

        if pkt.get("header", {}).get("message_type") != "query_request":
            return

        body = pkt.get("body", {})
        targets = body.get("target_devices") or []

        # safety filter for any broadcast packet that still carries targets
        if targets and self.name not in targets:
            return

        qid = body.get("query_id", "unknown")
        query = body.get("query", "")

        resp = {
            "header": {
                "timestamp": now_iso(),
                "source_device": self.name,
                "message_type": "query_response",
            },
            "body": {
                "query_id": qid,
                "status": "success",
                "model_used": "dino-v2",
                "error": None,
                "answer": f"{self.name} handled: {query}",
                "metadata": {
                    "image_width": 1,
                    "image_height": 1,
                    "format": "png",
                    "image_base64": IMG_B64,
                    "chunk_index": 0,
                    "total_chunks": 1,
                },
                "frame": {
                    "frame_id": 0,
                    "timestamp": now_iso(),
                    "detections": [
                        {"label": "mock_object", "confidence": 0.99, "dets": ["det0"]}
                    ],
                },
            },
        }
        self.client.publish("edge/results", json.dumps(resp))
        print(f"[{self.name}] responded to query_id={qid}")


def main():
    edges = [MockEdge(f"Edge-Cam-{i:02d}") for i in range(1, EDGE_COUNT + 1)]
    for edge in edges:
        edge.start()

    print("Mock edge fleet running. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        for edge in edges:
            edge.stop()


if __name__ == "__main__":
    main()
