#!/usr/bin/env python3
"""
Mock Edge Server for LAS-VICA GUI Testing
==========================================

Simulates an edge device that responds to MQTT queries with test images.
This allows testing the GUI without real edge devices or VILA inference.

Features:
- Publishes device_status heartbeats on edge/status (NUC relay discovery cache)
- Handles query_request packets on edge/control (current host packet format)
- Publishes query_response chunks on edge/results
- Legacy command: discover/query format still supported

Usage:
    python mock_edge_server.py [--broker IP] [--port PORT]
"""

import os
import sys
import json
import time
import base64
import uuid
import argparse
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add parent directories to path
current_dir = Path(__file__).parent
gui_dir = current_dir.parent
host_dir = gui_dir.parent
host_team_dir = host_dir.parent
project_root = host_team_dir.parent

for path in [str(current_dir), str(gui_dir), str(host_dir), str(host_team_dir), str(project_root)]:
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
    print("Warning: paho-mqtt not installed. Run: pip install paho-mqtt")


# Test images directory
TEST_IMAGES_DIR = current_dir / "test_images"

# Topics used by Edge/client.py + Network/server.py relay
STATUS_TOPIC = "edge/status"
RESULTS_TOPIC = "edge/results"
STATUS_INTERVAL_SEC = 2.0


class MockEdgeDevice:
    """Simulates an edge device with camera and VILA inference capabilities."""
    
    def __init__(self, device_name: str = "Edge-Cam-01"):
        self.device_name = device_name
        self.status = "online"
        self.cpu = 45.2
        self.ram = 62.8
        self.gpu = 38.5
        self.network_strength = -55
        self.is_processing = False
        
    def get_status(self) -> Dict:
        """Return current device status."""
        return {
            "name": self.device_name,
            "device_name": self.device_name,
            "device_id": self.device_name.lower().replace("-", "_"),
            "ip": "192.168.1.100",
            "status": self.status,
            "cpu": self.cpu + (hash(time.time()) % 10 - 5),  # Slight variation
            "ram": self.ram + (hash(time.time()) % 6 - 3),
            "gpu": self.gpu + (hash(time.time()) % 8 - 4),
            "network_strength": self.network_strength,
            "isProcessing": self.is_processing
        }


class QueryMatcher:
    """Matches queries to appropriate test responses."""
    
    # Query patterns and their corresponding image sets
    QUERY_PATTERNS = {
        "person behind": {
            "images": ["person_behind_car_01.jpg", "person_behind_car_02.jpg", "person_behind_car_03.jpg"],
            "response_text": "Yes, I detected {count} person(s) standing behind the black car.",
            "detection_label": "person"
        },
        "anyone behind": {
            "images": ["person_behind_car_01.jpg", "person_behind_car_02.jpg"],
            "response_text": "Yes, there are {count} people visible behind the black car.",
            "detection_label": "person"
        },
        "black car": {
            "images": ["person_behind_car_04.jpg", "person_behind_car_05.jpg"],
            "response_text": "I found the black car with {count} person(s) nearby.",
            "detection_label": "person"
        },
        "people": {
            "images": ["person_behind_car_01.jpg", "person_behind_car_02.jpg", "person_behind_car_03.jpg"],
            "response_text": "I detected {count} people in the scene.",
            "detection_label": "person"
        }
    }
    
    @classmethod
    def match_query(cls, query: str) -> Optional[Dict]:
        """Find matching pattern for a query."""
        query_lower = query.lower()
        
        for pattern, response_config in cls.QUERY_PATTERNS.items():
            if pattern in query_lower:
                return response_config
        
        # Default response if no pattern matches
        return {
            "images": ["person_behind_car_01.jpg"],
            "response_text": "Query processed. Found relevant images.",
            "detection_label": "object"
        }


class MockEdgeServer:
    """Mock MQTT server that simulates edge device responses."""
    
    def __init__(
        self,
        broker_ip: str = "localhost",
        broker_port: int = 1883,
        control_topic: str = "edge/control",
        num_devices: int = 2
    ):
        self.broker_ip = broker_ip
        self.broker_port = broker_port
        self.control_topic = control_topic
        
        # Create mock devices
        self.devices = [
            MockEdgeDevice(f"Edge-Cam-{i:02d}") for i in range(1, num_devices + 1)
        ]
        
        self.client = None
        self.running = False
        
    def _create_header(self, message_type: str, source_device: str) -> Dict:
        """Create a standard packet header."""
        return {
            "timestamp": datetime.now().isoformat(),
            "source_device": source_device,
            "message_type": message_type
        }

    def _make_packet(self, message_type: str, body: Dict, source_device: str) -> Dict:
        return {
            "header": self._create_header(message_type, source_device),
            "body": body,
        }

    def _publish_device_status(self, device: MockEdgeDevice) -> None:
        """Heartbeat on edge/status — NUC relay caches these for discovery."""
        if not self.client:
            return
        status = device.get_status()
        pkt = self._make_packet(
            "device_status",
            {
                "name": status["name"],
                "cpu": float(status["cpu"]),
                "ram": float(status["ram"]),
                "gpu": float(status["gpu"]),
                "network_strength": int(status["network_strength"]),
                "isProcessing": bool(status["isProcessing"]),
            },
            device.device_name,
        )
        self.client.publish(STATUS_TOPIC, json.dumps(pkt))
        print(f"[MockServer] Published device_status for {device.device_name}")

    def _publish_all_device_status(self) -> None:
        for device in self.devices:
            self._publish_device_status(device)

    def _status_loop(self) -> None:
        while self.running:
            try:
                self._publish_all_device_status()
            except Exception as e:
                print(f"[MockServer] Status loop error: {e}")
            time.sleep(STATUS_INTERVAL_SEC)

    @staticmethod
    def _parse_packet(payload: Dict) -> tuple:
        """Return (message_type, body) for current or legacy host packets."""
        if isinstance(payload, dict) and isinstance(payload.get("header"), dict):
            header = payload["header"]
            return header.get("message_type"), payload.get("body") or {}

        command = (payload.get("command") or "").lower()
        if command == "discover":
            return "discovery", payload
        if command == "query":
            return "query_request", {
                "query_id": payload.get("request_id") or str(uuid.uuid4()),
                "query": payload.get("query", ""),
            }
        return None, {}

    @staticmethod
    def _should_process_query(device_name: str, body: Dict) -> bool:
        targets = body.get("target_devices")
        if not isinstance(targets, list) or not targets:
            return True
        normalized = {
            str(t).strip().lower() for t in targets if isinstance(t, str) and t.strip()
        }
        return device_name.strip().lower() in normalized
    
    def _load_image_base64(self, image_name: str) -> Optional[str]:
        """Load an image and return as base64 string."""
        image_path = TEST_IMAGES_DIR / image_name
        
        if not image_path.exists():
            print(f"  Warning: Test image not found: {image_path}")
            return None
        
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    
    def _handle_discovery_packet(self) -> None:
        """NUC relay answers discovery from edge/status cache — refresh status now."""
        print("[MockServer] Discovery request received — refreshing device_status heartbeats")
        self._publish_all_device_status()

    def _handle_query_request(self, body: Dict, device: MockEdgeDevice) -> None:
        """Handle query_request packet body for one mock edge device."""
        query_text = (body.get("query") or "").strip()
        query_id = body.get("query_id") or str(uuid.uuid4())

        if not self._should_process_query(device.device_name, body):
            print(
                f"[MockServer] Skipping query for {device.device_name} "
                f"(not in target_devices)"
            )
            return

        print(f"[MockServer] {device.device_name} handling query: '{query_text}'")
        
        # Match query to response pattern
        match_result = QueryMatcher.match_query(query_text)
        
        if not match_result:
            print(f"[MockServer] No matching pattern for query")
            return
        
        device.is_processing = True
        self._publish_device_status(device)

        # Simulate inference time
        time.sleep(1.0)

        images = match_result["images"]
        total_chunks = len(images)

        for idx, image_name in enumerate(images):
            image_base64 = self._load_image_base64(image_name)
            
            if not image_base64:
                continue
            
            # Create detection data
            num_detections = idx + 1  # Vary detections per image
            detections = []
            for det_idx in range(num_detections):
                detections.append({
                    "label": match_result["detection_label"],
                    "confidence": 0.85 + (hash(f"{image_name}{det_idx}") % 15) / 100,
                    "dets": [f"det_{det_idx + 1}"],
                    "bbox": [100 + det_idx * 80, 150, 160 + det_idx * 80, 350]
                })
            
            response = {
                "header": self._create_header("query_response", device.device_name),
                "body": {
                    "query_id": query_id,
                    "metadata": {
                        "image_width": 800,
                        "image_height": 600,
                        "format": "jpeg",
                        "image_base64": image_base64,
                        "chunk_index": idx,
                        "total_chunks": total_chunks
                    },
                    "frame": {
                        "frame_id": idx,
                        "timestamp": datetime.now().isoformat(),
                        "detections": detections
                    },
                    "response_text": match_result["response_text"].format(count=num_detections)
                },
                "request_id": query_id
            }
            
            self.client.publish(RESULTS_TOPIC, json.dumps(response))
            print(
                f"[MockServer] {device.device_name}: sent image "
                f"{idx + 1}/{total_chunks} → {RESULTS_TOPIC}"
            )

            if idx < total_chunks - 1:
                time.sleep(0.2)

        device.is_processing = False
        self._publish_device_status(device)
        print(f"[MockServer] {device.device_name}: query complete ({total_chunks} images).")
    
    def _on_connect(self, client, userdata, flags, rc):
        """Handle MQTT connection."""
        if rc == 0:
            print(f"[MockServer] Connected to MQTT broker at {self.broker_ip}:{self.broker_port}")
            client.subscribe(self.control_topic)
            print(f"[MockServer] Subscribed to: {self.control_topic}")
            print(
                f"[MockServer] Publishing heartbeats to {STATUS_TOPIC} "
                f"(required for NUC discovery cache)"
            )
            self._publish_all_device_status()
            threading.Thread(target=self._status_loop, daemon=True).start()
        else:
            print(f"[MockServer] Connection failed with code: {rc}")

    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages on edge/control."""
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            print(f"[MockServer] Invalid JSON received on {msg.topic}")
            return

        msg_type, body = self._parse_packet(payload)
        print(f"[MockServer] Received on {msg.topic}: message_type={msg_type!r}")

        if msg_type == "discovery":
            threading.Thread(target=self._handle_discovery_packet, daemon=True).start()
            return

        if msg_type == "query_request":
            for device in self.devices:
                threading.Thread(
                    target=self._handle_query_request,
                    args=(body, device),
                    daemon=True,
                ).start()
            return

        if msg_type:
            print(f"[MockServer] Ignoring unhandled message_type: {msg_type}")
        else:
            print(f"[MockServer] Unrecognized payload (expected header/body packet)")
    
    def start(self):
        """Start the mock server."""
        if not MQTT_AVAILABLE:
            print("Error: paho-mqtt is required. Install with: pip install paho-mqtt")
            return
        
        self.client = mqtt.Client()
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        
        print(f"[MockServer] Starting Mock Edge Server...")
        print(f"[MockServer] Broker: {self.broker_ip}:{self.broker_port}")
        print(f"[MockServer] Control topic: {self.control_topic}")
        print(f"[MockServer] Mock devices: {[d.device_name for d in self.devices]}")
        print(f"[MockServer] Test images dir: {TEST_IMAGES_DIR}")
        print()
        
        try:
            self.client.connect(self.broker_ip, self.broker_port, 60)
            self.running = True
            self.client.loop_forever()
        except KeyboardInterrupt:
            print("\n[MockServer] Shutting down...")
            self.running = False
            self.client.disconnect()
        except Exception as e:
            print(f"[MockServer] Error: {e}")
            self.running = False


def main():
    parser = argparse.ArgumentParser(description="Mock Edge Server for LAS-VICA testing")
    parser.add_argument("--broker", default="localhost", help="MQTT broker IP address")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--topic", default="edge/control", help="Control topic to listen on")
    parser.add_argument("--devices", type=int, default=2, help="Number of mock devices")
    
    args = parser.parse_args()
    
    # Check if test images exist
    if not TEST_IMAGES_DIR.exists() or not list(TEST_IMAGES_DIR.glob("*.jpg")):
        print("Test images not found. Generating them first...")
        from generate_test_images import main as generate_images
        generate_images()
        print()
    
    server = MockEdgeServer(
        broker_ip=args.broker,
        broker_port=args.port,
        control_topic=args.topic,
        num_devices=args.devices
    )
    
    server.start()


if __name__ == "__main__":
    main()
