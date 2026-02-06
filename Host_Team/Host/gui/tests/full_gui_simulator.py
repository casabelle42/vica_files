#!/usr/bin/env python3
"""
LAS-VICA Full GUI Feature Simulator
====================================

Simulates ALL GUI features with PROPER JSON packet structure matching
what real VILA edge devices would send through the server.

This matches the packet structure defined in:
    Host_Team/Host/packetStructure.md

Packet Types Simulated:
- discovery_response: List of available edge devices
- query_response: Images with detections from VILA inference
- device_status: Real-time device health updates

Usage:
    python full_gui_simulator.py
"""

import os
import sys
import json
import time
import base64
import random
import uuid
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable

# Add parent directories to path
current_dir = Path(__file__).parent
gui_dir = current_dir.parent
host_dir = gui_dir.parent
host_team_dir = host_dir.parent
project_root = host_team_dir.parent

for path in [str(current_dir), str(gui_dir), str(host_dir), str(host_team_dir), str(project_root)]:
    if path not in sys.path:
        sys.path.insert(0, path)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

# Test images directory
TEST_IMAGES_DIR = current_dir / "test_images"


class PacketFactory:
    """
    Creates JSON packets matching the exact structure from packetStructure.md
    This simulates what real VILA edge devices would send.
    """
    
    @staticmethod
    def create_header(source_device: str, message_type: str) -> Dict:
        """Create standard packet header (Section 0 of spec)."""
        return {
            "timestamp": datetime.now().isoformat(),
            "source_device": source_device,
            "message_type": message_type
        }
    
    @staticmethod
    def create_discovery_response(devices: List[Dict]) -> Dict:
        """
        Create discovery_response packet (Section 3.2 of spec).
        
        Format:
        {
            "header": {...},
            "body": {
                "devices": [
                    {
                        "name": "<edge_name>",
                        "status": "online | offline",
                        "cpu": 0.0,
                        "ram": 0.0,
                        "gpu": 0.0,
                        "network_strength": -60,
                        "isProcessing": false
                    }
                ]
            }
        }
        """
        return {
            "header": PacketFactory.create_header("MockServer", "discovery_response"),
            "body": {
                "devices": devices
            }
        }
    
    @staticmethod
    def create_query_response(
        source_device: str,
        query_id: str,
        image_base64: str,
        image_width: int,
        image_height: int,
        chunk_index: int,
        total_chunks: int,
        frame_id: int,
        detections: List[Dict]
    ) -> Dict:
        """
        Create query_response packet (Section 1.2 of spec).
        
        Format:
        {
            "header": {
                "timestamp": "<ISO-8601>",
                "source_device": "<edge_name>",
                "message_type": "query_response"
            },
            "body": {
                "query_id": "<uuid>",
                "metadata": {
                    "image_width": 800,
                    "image_height": 600,
                    "format": "jpeg",
                    "image_base64": "<base64_data>",
                    "chunk_index": 0,
                    "total_chunks": 1
                },
                "frame": {
                    "frame_id": 0,
                    "timestamp": "<ISO-8601>",
                    "detections": [
                        {
                            "label": "person",
                            "confidence": 0.95,
                            "dets": ["det1"]
                        }
                    ]
                }
            }
        }
        """
        return {
            "header": PacketFactory.create_header(source_device, "query_response"),
            "body": {
                "query_id": query_id,
                "metadata": {
                    "image_width": image_width,
                    "image_height": image_height,
                    "format": "jpeg",
                    "image_base64": image_base64,
                    "chunk_index": chunk_index,
                    "total_chunks": total_chunks
                },
                "frame": {
                    "frame_id": frame_id,
                    "timestamp": datetime.now().isoformat(),
                    "detections": detections
                }
            }
        }
    
    @staticmethod
    def create_device_status(
        device_name: str,
        cpu: float,
        ram: float,
        gpu: float,
        network_strength: int,
        is_processing: bool
    ) -> Dict:
        """
        Create device_status packet (Section 1.2 of spec).
        
        Format:
        {
            "header": {...},
            "body": {
                "name": "<edge_name>",
                "cpu": 0.0,
                "ram": 0.0,
                "gpu": 0.0,
                "network_strength": -60,
                "isProcessing": true
            }
        }
        """
        return {
            "header": PacketFactory.create_header(device_name, "device_status"),
            "body": {
                "name": device_name,
                "cpu": cpu,
                "ram": ram,
                "gpu": gpu,
                "network_strength": network_strength,
                "isProcessing": is_processing
            }
        }


class SimulatedVILADevice:
    """
    Simulates a VILA edge device with realistic behavior.
    Generates proper JSON packets as defined in packetStructure.md
    """
    
    def __init__(self, device_id: int, name: str, ip: str):
        self.device_id = device_id
        self.name = name
        self.ip = ip
        self.status = "online"
        self.cpu = random.uniform(20, 60)
        self.ram = random.uniform(40, 70)
        self.gpu = random.uniform(10, 50)
        self.network_strength = random.randint(-70, -40)
        self.is_processing = False
        self.version = f"v2.{random.randint(0, 5)}.{random.randint(0, 9)}"
        
    def update_metrics(self):
        """Simulate realistic metric fluctuations."""
        if self.is_processing:
            self.cpu = min(95, self.cpu + random.uniform(-5, 15))
            self.gpu = min(95, self.gpu + random.uniform(-3, 20))
        else:
            self.cpu = max(5, min(80, self.cpu + random.uniform(-8, 8)))
            self.gpu = max(5, min(60, self.gpu + random.uniform(-5, 5)))
        
        self.ram = max(30, min(85, self.ram + random.uniform(-2, 2)))
        self.network_strength = max(-80, min(-30, self.network_strength + random.randint(-3, 3)))
    
    def get_discovery_info(self) -> Dict:
        """Get device info for discovery_response packet."""
        return {
            "name": self.name,
            "status": self.status,
            "cpu": round(self.cpu, 1),
            "ram": round(self.ram, 1),
            "gpu": round(self.gpu, 1),
            "network_strength": self.network_strength,
            "isProcessing": self.is_processing,
            # Additional fields for GUI compatibility
            "device_name": self.name,
            "device_id": self.name.lower().replace("-", "_"),
            "ip": self.ip
        }
    
    def get_status_packet(self) -> Dict:
        """Generate a device_status packet."""
        return PacketFactory.create_device_status(
            device_name=self.name,
            cpu=round(self.cpu, 1),
            ram=round(self.ram, 1),
            gpu=round(self.gpu, 1),
            network_strength=self.network_strength,
            is_processing=self.is_processing
        )
    
    def to_gui_format(self) -> Dict:
        """Convert to GUI-compatible format for display."""
        connection = "Strong" if self.network_strength > -50 else ("Medium" if self.network_strength > -65 else "Weak")
        activity = "Processing" if self.is_processing else "Active"
        return {
            "name": self.name,
            "location": f"IP: {self.ip}",
            "status": "Online" if self.status == "online" else "Offline",
            "connection": connection,
            "metadata": f"{self.version} • {activity}"
        }


class VILAQuerySimulator:
    """
    Simulates VILA inference responses with proper packet structure.
    """
    
    # Simulated VILA inference results for different queries
    INFERENCE_RESULTS = {
        "what do you see": {
            # Returns images from ALL 3 cameras
            "images": ["edge_cam_01_combined.jpg", "edge_cam_02_combined.jpg", "edge_cam_03_combined.jpg"],
            "source_devices": ["Edge-Cam-01", "Edge-Cam-02", "Edge-Cam-03"],
            "detections_per_image": [
                [{"label": "person", "confidence": 0.94, "bbox": [120, 150, 180, 350]},
                 {"label": "person", "confidence": 0.91, "bbox": [200, 145, 260, 345]},
                 {"label": "car", "confidence": 0.98, "bbox": [50, 200, 350, 450]}],
                [{"label": "person", "confidence": 0.89, "bbox": [100, 140, 160, 340]},
                 {"label": "person", "confidence": 0.86, "bbox": [180, 145, 240, 345]},
                 {"label": "car", "confidence": 0.97, "bbox": [50, 200, 350, 450]}],
                [{"label": "person", "confidence": 0.92, "bbox": [130, 155, 190, 355]},
                 {"label": "person", "confidence": 0.88, "bbox": [210, 150, 270, 350]},
                 {"label": "car", "confidence": 0.96, "bbox": [50, 200, 350, 450]}]
            ]
        },
        "person behind": {
            "images": ["edge_cam_01_person_02.jpg", "edge_cam_02_person_02.jpg", "edge_cam_03_person_03.jpg"],
            "source_devices": ["Edge-Cam-01", "Edge-Cam-02", "Edge-Cam-03"],
            "detections_per_image": [
                [{"label": "person", "confidence": 0.94, "bbox": [120, 150, 180, 350]},
                 {"label": "person", "confidence": 0.91, "bbox": [200, 145, 260, 345]}],
                [{"label": "person", "confidence": 0.89, "bbox": [100, 140, 160, 340]},
                 {"label": "person", "confidence": 0.87, "bbox": [200, 145, 260, 345]}],
                [{"label": "person", "confidence": 0.92, "bbox": [80, 130, 140, 330]},
                 {"label": "person", "confidence": 0.88, "bbox": [160, 135, 220, 335]},
                 {"label": "person", "confidence": 0.85, "bbox": [240, 140, 300, 340]}]
            ]
        },
        "anyone behind": {
            "images": ["edge_cam_01_person_02.jpg", "edge_cam_02_person_02.jpg"],
            "source_devices": ["Edge-Cam-01", "Edge-Cam-02"],
            "detections_per_image": [
                [{"label": "person", "confidence": 0.91, "bbox": [100, 140, 160, 340]},
                 {"label": "person", "confidence": 0.89, "bbox": [200, 145, 260, 345]}],
                [{"label": "person", "confidence": 0.87, "bbox": [150, 150, 210, 350]},
                 {"label": "person", "confidence": 0.84, "bbox": [220, 155, 280, 355]}]
            ]
        },
        "black car": {
            # CAR bounding boxes - uses car detection images
            "images": ["edge_cam_01_car.jpg", "edge_cam_02_car.jpg"],
            "source_devices": ["Edge-Cam-01", "Edge-Cam-02"],
            "detections_per_image": [
                [{"label": "car", "confidence": 0.98, "bbox": [50, 200, 350, 450]}],
                [{"label": "car", "confidence": 0.97, "bbox": [60, 210, 360, 460]}]
            ]
        },
        "car": {
            # CAR bounding boxes only
            "images": ["edge_cam_01_car.jpg", "edge_cam_02_car.jpg"],
            "source_devices": ["Edge-Cam-01", "Edge-Cam-02"],
            "detections_per_image": [
                [{"label": "car", "confidence": 0.98, "bbox": [50, 200, 350, 450]}],
                [{"label": "car", "confidence": 0.96, "bbox": [55, 205, 355, 455]}]
            ]
        },
        "people": {
            "images": ["edge_cam_01_person_02.jpg", "edge_cam_02_person_02.jpg", "edge_cam_03_person_03.jpg"],
            "source_devices": ["Edge-Cam-01", "Edge-Cam-02", "Edge-Cam-03"],
            "detections_per_image": [
                [{"label": "person", "confidence": 0.91, "bbox": [100, 140, 160, 340]},
                 {"label": "person", "confidence": 0.89, "bbox": [200, 145, 260, 345]}],
                [{"label": "person", "confidence": 0.88, "bbox": [110, 145, 170, 345]},
                 {"label": "person", "confidence": 0.86, "bbox": [190, 140, 250, 340]}],
                [{"label": "person", "confidence": 0.92, "bbox": [80, 130, 140, 330]},
                 {"label": "person", "confidence": 0.88, "bbox": [160, 135, 220, 335]},
                 {"label": "person", "confidence": 0.85, "bbox": [240, 140, 300, 340]}]
            ]
        }
    }
    
    @classmethod
    def process_query(cls, query: str, default_source_device: str) -> List[Dict]:
        """
        Simulate VILA inference and return list of query_response packets.
        
        Returns proper JSON packets as defined in packetStructure.md Section 1.2
        Each image can come from a different source device (camera).
        """
        query_id = str(uuid.uuid4())
        query_lower = query.lower()
        
        # Find matching inference result
        result = None
        for pattern, data in cls.INFERENCE_RESULTS.items():
            if pattern in query_lower:
                result = data
                break
        
        # Default if no match - show all 3 cameras
        if result is None:
            result = {
                "images": ["edge_cam_01_combined.jpg", "edge_cam_02_combined.jpg", "edge_cam_03_combined.jpg"],
                "source_devices": ["Edge-Cam-01", "Edge-Cam-02", "Edge-Cam-03"],
                "detections_per_image": [
                    [{"label": "object", "confidence": 0.75, "bbox": [100, 100, 200, 200]}],
                    [{"label": "object", "confidence": 0.72, "bbox": [110, 110, 210, 210]}],
                    [{"label": "object", "confidence": 0.78, "bbox": [90, 90, 190, 190]}]
                ]
            }
        
        # Get source devices list (or use default for all)
        source_devices = result.get("source_devices", [default_source_device] * len(result["images"]))
        
        # Generate response packets
        packets = []
        total_chunks = len(result["images"])
        
        for idx, image_name in enumerate(result["images"]):
            image_path = TEST_IMAGES_DIR / image_name
            
            if not image_path.exists():
                print(f"[VILA] Warning: Image not found: {image_name}")
                continue
            
            # Load image and encode
            with open(image_path, "rb") as f:
                image_data = f.read()
                image_base64 = base64.b64encode(image_data).decode("utf-8")
            
            # Get image dimensions (assume 800x600 for test images)
            image_width = 800
            image_height = 600
            
            # Get detections for this image
            detections = result["detections_per_image"][idx] if idx < len(result["detections_per_image"]) else []
            
            # Format detections for packet
            formatted_detections = []
            for det in detections:
                formatted_detections.append({
                    "label": det["label"],
                    "confidence": det["confidence"],
                    "dets": [f"det_{idx}_{len(formatted_detections)}"],
                    "bbox": det.get("bbox", [0, 0, 100, 100])
                })
            
            # Get source device for this image (different cameras)
            source_device = source_devices[idx] if idx < len(source_devices) else default_source_device
            
            # Create query_response packet
            packet = PacketFactory.create_query_response(
                source_device=source_device,
                query_id=query_id,
                image_base64=image_base64,
                image_width=image_width,
                image_height=image_height,
                chunk_index=idx,
                total_chunks=total_chunks,
                frame_id=idx,
                detections=formatted_detections
            )
            
            packets.append(packet)
        
        return packets


class GUISimulator(QObject):
    """
    Main simulator that coordinates GUI updates using proper packet processing.
    Simulates the full data flow from VILA edge devices through to the GUI.
    """
    
    # Signals for thread-safe GUI updates
    update_devices_signal = pyqtSignal(list)
    update_device_status_signal = pyqtSignal(str, dict)
    process_packet_signal = pyqtSignal(dict, str)  # packet, query_text
    
    def __init__(self, devices_window=None):
        super().__init__()
        
        self.devices_window = devices_window
        
        # Create simulated VILA devices
        self.devices = [
            SimulatedVILADevice(1, "Edge-Cam-01", "192.168.1.101"),
            SimulatedVILADevice(2, "Edge-Cam-02", "192.168.1.102"),
            SimulatedVILADevice(3, "Edge-Cam-03", "192.168.1.103"),
        ]
        
        self.status_timer = None
        self.running = False
        self.query_window = None  # Will be set when query window opens
        self.current_query_text = ""  # Track current query for packet processing
        
        # Connect signals
        if devices_window:
            self.update_devices_signal.connect(devices_window.update_devices)
        
        # Connect packet processing signal (thread-safe GUI updates)
        self.process_packet_signal.connect(self._process_packet_on_main_thread)
    
    def start(self):
        """Start background simulation."""
        self.running = True
        print("[Simulator] Started - simulating VILA edge devices")
        
        # Periodic status updates
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._send_status_updates)
        self.status_timer.start(5000)  # Every 5 seconds
    
    def stop(self):
        """Stop simulation."""
        self.running = False
        if self.status_timer:
            self.status_timer.stop()
        print("[Simulator] Stopped")
    
    def _send_status_updates(self):
        """Send device_status packets (simulates real-time updates)."""
        for device in self.devices:
            device.update_metrics()
            packet = device.get_status_packet()
            
            # Log the packet (simulates what would be received via MQTT)
            print(f"[MQTT IN] device_status from {device.name}: CPU={packet['body']['cpu']:.1f}%, GPU={packet['body']['gpu']:.1f}%")
    
    def _process_packet_on_main_thread(self, packet: Dict, query_text: str):
        """Process query_response packet on the main Qt thread (thread-safe)."""
        if not self.query_window:
            print("[GUI] No query window available for packet processing")
            return
        
        process_query_response_packet(packet, self.query_window, query_text)
    
    def handle_discovery(self) -> List[Dict]:
        """
        Handle discovery request and return discovery_response packet.
        Returns GUI-formatted device list.
        """
        print("\n[MQTT OUT] Sending discovery request...")
        time.sleep(0.3)  # Simulate network latency
        
        # Create discovery_response packet
        device_info_list = [d.get_discovery_info() for d in self.devices]
        packet = PacketFactory.create_discovery_response(device_info_list)
        
        # Log the packet
        print(f"[MQTT IN] discovery_response:")
        print(f"  {json.dumps(packet, indent=2, default=str)[:500]}...")
        
        # Convert to GUI format
        gui_devices = [d.to_gui_format() for d in self.devices]
        return gui_devices
    
    def handle_query(self, query_text: str, on_packet_received: Callable = None):
        """
        Handle query request and simulate VILA inference response.
        Calls on_packet_received for each query_response packet.
        """
        print(f"\n[MQTT OUT] Sending query_request: '{query_text}'")
        
        def process():
            # Mark first device as processing
            self.devices[0].is_processing = True
            
            # Simulate inference time
            time.sleep(random.uniform(1.0, 2.0))
            
            # Generate query_response packets
            packets = VILAQuerySimulator.process_query(query_text, self.devices[0].name)
            
            print(f"[VILA] Generated {len(packets)} query_response packets")
            
            for idx, packet in enumerate(packets):
                # Log packet structure (truncate base64 for readability)
                log_packet = json.loads(json.dumps(packet))
                if "body" in log_packet and "metadata" in log_packet["body"]:
                    b64_len = len(log_packet["body"]["metadata"].get("image_base64", ""))
                    log_packet["body"]["metadata"]["image_base64"] = f"<{b64_len} bytes>"
                
                print(f"\n[MQTT IN] query_response ({idx+1}/{len(packets)}):")
                print(f"  Header: {json.dumps(packet['header'], indent=4)}")
                print(f"  Body.query_id: {packet['body']['query_id']}")
                print(f"  Body.metadata.image_width: {packet['body']['metadata']['image_width']}")
                print(f"  Body.metadata.image_height: {packet['body']['metadata']['image_height']}")
                print(f"  Body.metadata.chunk_index: {packet['body']['metadata']['chunk_index']}/{packet['body']['metadata']['total_chunks']}")
                print(f"  Body.frame.detections: {len(packet['body']['frame']['detections'])} objects")
                for det in packet['body']['frame']['detections']:
                    print(f"    - {det['label']}: {det['confidence']:.2f}")
                
                if on_packet_received:
                    on_packet_received(packet)
                
                # Delay between chunks
                if idx < len(packets) - 1:
                    time.sleep(0.2)
            
            # Mark device as done
            self.devices[0].is_processing = False
            print(f"\n[VILA] Query processing complete")
        
        threading.Thread(target=process, daemon=True).start()


def process_query_response_packet(packet: Dict, query_window, query_text: str = "") -> None:
    """
    Process a query_response packet and update the GUI.
    This is called on the main Qt thread via signal, so it's thread-safe.
    
    - Adds image thumbnails to "Images Returned" section
    - Makes thumbnails clickable to show in main preview
    - Updates metadata section with detection info
    """
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtCore import QByteArray, Qt
    
    body = packet.get("body", {})
    header = packet.get("header", {})
    
    # Extract data from packet
    pkt_metadata = body.get("metadata", {})
    frame = body.get("frame", {})
    
    image_base64 = pkt_metadata.get("image_base64", "")
    detections = frame.get("detections", [])
    chunk_index = pkt_metadata.get("chunk_index", 0)
    total_chunks = pkt_metadata.get("total_chunks", 1)
    
    if not image_base64:
        print("[GUI] No image data in packet")
        return
    
    print(f"[GUI] Processing image {chunk_index + 1}/{total_chunks}...")
    
    # Build metadata dict for this image
    det_summary = ", ".join([f"{d['label']}({d['confidence']:.0%})" for d in detections[:3]])
    max_confidence = max([d['confidence'] for d in detections], default=0)
    
    image_metadata = {
        "image": f"Frame {chunk_index + 1}/{total_chunks}",
        "edge_device": header.get("source_device", "Unknown"),
        "query": query_text or "User query",
        "response": det_summary or "No detections",
        "confidence_rate": f"{max_confidence * 100:.1f}%",
        "time_processed": header.get("timestamp", datetime.now().isoformat())[:19],
        "detections": detections,
        "image_base64": image_base64
    }
    
    try:
        # Decode image
        try:
            image_bytes = base64.b64decode(image_base64)
            pixmap = QPixmap()
            if not pixmap.loadFromData(QByteArray(image_bytes)):
                print("[GUI] Failed to load image from base64 data")
                return
            print(f"[GUI] Image loaded: {pixmap.width()}x{pixmap.height()}")
        except Exception as e:
            print(f"[GUI] Error decoding image: {e}")
            import traceback
            traceback.print_exc()
            return
        
        # Add clickable thumbnail to "Images Returned" section
        # (Image preview stays empty until user clicks a thumbnail)
        try:
            add_clickable_thumbnail(query_window, pixmap, image_metadata)
        except Exception as e:
            print(f"[GUI] Error adding thumbnail: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"[GUI] Added image {chunk_index + 1}/{total_chunks} to display")
        
    except Exception as e:
        print(f"[GUI] Unexpected error processing packet: {e}")
        import traceback
        traceback.print_exc()


def update_metadata_display(query_window, metadata: Dict) -> None:
    """Update the metadata labels in the query window."""
    if not hasattr(query_window, 'metadata_labels'):
        return
    
    field_mapping = {
        "image": "image",
        "edge_device": "edge_device", 
        "query": "query",
        "response": "response",
        "confidence_rate": "confidence_rate",
        "time_processed": "time_processed"
    }
    
    for gui_field, meta_key in field_mapping.items():
        if gui_field in query_window.metadata_labels:
            label = query_window.metadata_labels[gui_field]
            value = metadata.get(meta_key, "N/A")
            prefix = gui_field.replace("_", " ").title()
            label.setText(f"{prefix}: {value}")


def add_clickable_thumbnail(query_window, pixmap: 'QPixmap', metadata: Dict) -> None:
    """Add a clickable thumbnail to the Images Returned section."""
    from PyQt6.QtGui import QCursor
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel
    
    if not hasattr(query_window, 'returned_images_layout'):
        return
    
    # Create thumbnail label
    thumb_label = QLabel()
    thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    thumb_label.setStyleSheet(
        "background-color: rgba(255, 255, 255, 0.15);"
        "border-radius: 8px;"
        "padding: 4px;"
        "border: 2px solid transparent;"
    )
    thumb_label.setFixedSize(180, 135)
    thumb_label.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
    
    # Scale and set thumbnail
    scaled_thumb = pixmap.scaled(
        176, 131,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation
    )
    thumb_label.setPixmap(scaled_thumb)
    
    # Store full pixmap and metadata for click handler
    thumb_label._full_pixmap = pixmap
    thumb_label._metadata = metadata
    
    # Click handler - show in main preview
    def on_thumbnail_clicked(event):
        # Update main image preview
        if hasattr(query_window, 'image_label'):
            main_scaled = thumb_label._full_pixmap.scaled(
                query_window.image_label.width(),
                query_window.image_label.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            query_window.image_label.setPixmap(main_scaled)
        
        # Update metadata
        update_metadata_display(query_window, thumb_label._metadata)
        
        # Highlight selected thumbnail
        for i in range(query_window.returned_images_layout.count()):
            item = query_window.returned_images_layout.itemAt(i)
            if item and item.widget():
                item.widget().setStyleSheet(
                    "background-color: rgba(255, 255, 255, 0.15);"
                    "border-radius: 8px;"
                    "padding: 4px;"
                    "border: 2px solid transparent;"
                )
        
        thumb_label.setStyleSheet(
            "background-color: rgba(255, 255, 255, 0.25);"
            "border-radius: 8px;"
            "padding: 4px;"
            "border: 2px solid #5F73F9;"
        )
        
        print(f"[GUI] Selected: {thumb_label._metadata.get('image', 'Unknown')}")
    
    thumb_label.mousePressEvent = on_thumbnail_clicked
    
    # Add to layout
    query_window.returned_images_layout.addWidget(thumb_label)
    
    # Store reference
    if hasattr(query_window, 'returned_images'):
        query_window.returned_images.append({
            "label": thumb_label,
            "metadata": metadata
        })


def run_simulated_gui():
    """Run the GUI with full VILA simulation."""
    
    try:
        from s3_availableDevices import MainWindow as AvailableDevicesWindow
    except ImportError:
        from availableDevices import MainWindow as AvailableDevicesWindow
    
    print("=" * 70)
    print("LAS-VICA GUI Simulator - VILA Edge Device Simulation")
    print("=" * 70)
    print()
    print("This simulator uses the EXACT JSON packet structure from:")
    print("  Host_Team/Host/packetStructure.md")
    print()
    print("Packets simulated:")
    print("  - discovery_response (Section 3.2)")
    print("  - query_response (Section 1.2)")
    print("  - device_status (Section 1.2)")
    print()
    print("Try these queries:")
    print("  - 'is there anyone behind the black car'")
    print("  - 'show me all people'")
    print("  - 'where is the black car'")
    print()
    print("=" * 70)
    print()
    
    app = QApplication(sys.argv)
    
    devices_window = AvailableDevicesWindow()
    devices_window.setWindowTitle("LAS-VICA - VILA Simulation Mode")
    devices_window.show()
    
    simulator = GUISimulator(devices_window)
    
    # Discovery handler
    def on_discover():
        def do_discovery():
            device_list = simulator.handle_discovery()
            simulator.update_devices_signal.emit(device_list)
        threading.Thread(target=do_discovery, daemon=True).start()
    
    devices_window.set_discover_callback(on_discover)
    
    # Query window setup - must disconnect and reconnect the button signal
    def create_query_callback(qw):
        """Create the query callback for a query window."""
        def on_query(query_text):
            print(f"\n[SIMULATOR] Query received: '{query_text}'")
            
            # Store reference to query window in simulator for signal-based updates
            simulator.query_window = qw
            simulator.current_query_text = query_text
            
            # Clear previous images before new query
            if hasattr(qw, 'returned_images_layout'):
                while qw.returned_images_layout.count():
                    child = qw.returned_images_layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
            if hasattr(qw, 'returned_images'):
                qw.returned_images.clear()
            
            def handle_packet(packet):
                # Emit signal to process packet on main thread (thread-safe!)
                simulator.process_packet_signal.emit(packet, query_text)
            simulator.handle_query(query_text, handle_packet)
        return on_query
    
    def open_query_with_callback():
        """Open query window and set up callback."""
        # Create or show the query window
        if devices_window._query_window is None or not devices_window._query_window.isVisible():
            try:
                from s4_query import MainWindow as QueryWindow
            except ImportError:
                from query import MainWindow as QueryWindow
            devices_window._query_window = QueryWindow()
            devices_window._query_window.show()
        else:
            devices_window._query_window.raise_()
            devices_window._query_window.activateWindow()
        
        # Set the callback
        query_window = devices_window._query_window
        if query_window:
            callback = create_query_callback(query_window)
            query_window.set_query_callback(callback)
            query_window._on_query_callback = callback
            print("[GUI] Query window opened - callback connected")
    
    # Disconnect old signal and connect new one
    if hasattr(devices_window, 'query_btn') and devices_window.query_btn:
        try:
            devices_window.query_btn.clicked.disconnect()
        except:
            pass  # No connections to disconnect
        devices_window.query_btn.clicked.connect(open_query_with_callback)
        print("[GUI] Query button rewired to simulator")
    
    simulator.start()
    
    print("[GUI] Ready. Click 'Discover' to find VILA edge devices.\n")
    
    exit_code = app.exec()
    simulator.stop()
    
    return exit_code


def main():
    # Ensure test images exist
    if not TEST_IMAGES_DIR.exists() or not list(TEST_IMAGES_DIR.glob("*.jpg")):
        print("Generating test images...")
        from generate_test_images import main as generate_images
        generate_images()
        print()
    
    return run_simulated_gui()


if __name__ == "__main__":
    sys.exit(main())
