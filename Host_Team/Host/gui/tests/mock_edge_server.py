#!/usr/bin/env python3
"""
Mock Edge Server for LAS-VICA GUI Testing
==========================================

Simulates an edge device that responds to MQTT queries with test images.
This allows testing the GUI without real edge devices or VILA inference.

Features:
- Responds to discovery requests with mock device info
- Responds to query requests with pre-generated test images
- Simulates realistic response times and metadata

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
        
    def _create_header(self, message_type: str, source_device: str = "MockEdgeServer") -> Dict:
        """Create a standard packet header."""
        return {
            "timestamp": datetime.now().isoformat(),
            "source_device": source_device,
            "message_type": message_type
        }
    
    def _load_image_base64(self, image_name: str) -> Optional[str]:
        """Load an image and return as base64 string."""
        image_path = TEST_IMAGES_DIR / image_name
        
        if not image_path.exists():
            print(f"  Warning: Test image not found: {image_path}")
            return None
        
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    
    def _handle_discovery(self, message: Dict, reply_topic: str):
        """Handle discovery request."""
        print(f"[MockServer] Handling discovery request")
        
        # Build device list
        devices_list = [device.get_status() for device in self.devices]
        
        response = {
            "header": self._create_header("discovery_response"),
            "body": {
                "devices": devices_list,
                "available_devices": devices_list  # Alternative key for compatibility
            },
            "devices": devices_list,  # Top-level for compatibility
            "request_id": message.get("request_id")
        }
        
        # Simulate network delay
        time.sleep(0.3)
        
        self.client.publish(reply_topic, json.dumps(response))
        print(f"[MockServer] Sent discovery response with {len(devices_list)} devices to {reply_topic}")
    
    def _handle_query(self, message: Dict, reply_topic: str):
        """Handle query request with test images."""
        query_text = message.get("query", "")
        query_id = message.get("request_id", str(uuid.uuid4()))
        
        print(f"[MockServer] Handling query: '{query_text}'")
        
        # Match query to response pattern
        match_result = QueryMatcher.match_query(query_text)
        
        if not match_result:
            print(f"[MockServer] No matching pattern for query")
            return
        
        # Mark device as processing
        self.devices[0].is_processing = True
        
        # Simulate inference time
        time.sleep(1.0)
        
        # Send response images
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
                "header": self._create_header("query_response", self.devices[0].device_name),
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
            
            self.client.publish(reply_topic, json.dumps(response))
            print(f"[MockServer] Sent image {idx + 1}/{total_chunks}: {image_name}")
            
            # Small delay between chunks
            if idx < total_chunks - 1:
                time.sleep(0.2)
        
        # Mark device as done processing
        self.devices[0].is_processing = False
        print(f"[MockServer] Query complete. Sent {total_chunks} images.")
    
    def _on_connect(self, client, userdata, flags, rc):
        """Handle MQTT connection."""
        if rc == 0:
            print(f"[MockServer] Connected to MQTT broker at {self.broker_ip}:{self.broker_port}")
            client.subscribe(self.control_topic)
            print(f"[MockServer] Subscribed to: {self.control_topic}")
        else:
            print(f"[MockServer] Connection failed with code: {rc}")
    
    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages."""
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            print(f"[MockServer] Invalid JSON received on {msg.topic}")
            return
        
        print(f"[MockServer] Received message on {msg.topic}")
        
        # Get command type
        command = payload.get("command", "")
        reply_topic = payload.get("reply_topic", "edge/response")
        
        # Handle different commands
        if command == "discover":
            threading.Thread(
                target=self._handle_discovery,
                args=(payload, reply_topic),
                daemon=True
            ).start()
        elif command == "query":
            threading.Thread(
                target=self._handle_query,
                args=(payload, reply_topic),
                daemon=True
            ).start()
        else:
            print(f"[MockServer] Unknown command: {command}")
    
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
