"""
MQTT Packet Handler for GUI
Maps incoming MQTT packets (as defined in packetStructure.md) to GUI updates.
This handler bridges MQTT packet structures to the GUIHandler commands.

Usage:
    # Setup
    app = QApplication(sys.argv)
    devices_window = AvailableDevicesWindow()
    devices_window.show()
    
    gui_handler = GUIHandler(
        available_devices_window=devices_window,
        query_window=None  # Will be set when query window is created
    )
    
    packet_handler = MQTTPacketHandler(gui_handler)
    
    # When receiving MQTT packets, process them:
    # (In your MQTT on_message callback)
    def on_mqtt_message(client, userdata, message):
        packet_json = message.payload.decode('utf-8')
        result = packet_handler.process_packet(packet_json)
        print(f"Packet processed: {result}")
    
    # Example packet formats are shown in the main() function below.
"""

import json
import sys
import os
import logging
from typing import Any, Dict, Optional
from datetime import datetime

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyQt6.QtWidgets import QApplication
from Host.gui.gui_handler import GUIHandler
from Host_Team.Host.gui.availableDevices import MainWindow as AvailableDevicesWindow
from Host.gui.query import MainWindow as QueryWindow

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MQTTPacketHandler:
    """
    Handler that processes MQTT packets according to packetStructure.md
    and maps them to GUI updates via GUIHandler.
    """
    
    def __init__(self, gui_handler: GUIHandler):
        """
        Initialize the MQTT packet handler.
        
        Args:
            gui_handler: Instance of GUIHandler to use for GUI updates
        """
        self.gui_handler = gui_handler
        
        # Message type to handler mapping
        self.message_handlers = {
            # Incoming to Host (from EDGE)
            "available_devices": self._handle_available_devices,
            "device_status": self._handle_device_status,
            "query_response": self._handle_query_response,
            "container_status": self._handle_container_status,
            "cancel_query_status": self._handle_cancel_query_status,
            
            # From Server
            "discovery_response": self._handle_discovery_response,
        }
    
    def process_packet(self, packet_json: str) -> Dict[str, Any]:
        """
        Process an MQTT packet and update the GUI accordingly.
        
        Args:
            packet_json: JSON string containing MQTT packet (as per packetStructure.md)
            
        Returns:
            Dictionary with status and result information
        """
        try:
            packet = json.loads(packet_json)
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON format: {str(e)}"
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}
        
        # Validate packet structure
        if "header" not in packet:
            error_msg = "Missing 'header' field in packet"
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}
        
        header = packet.get("header", {})
        message_type = header.get("message_type")
        source_device = header.get("source_device", "Unknown")
        timestamp = header.get("timestamp", datetime.now().isoformat())
        
        if not message_type:
            error_msg = "Missing 'message_type' in packet header"
            logger.error(error_msg)
            return {"status": "error", "message": error_msg}
        
        logger.info(f"Processing packet: {message_type} from {source_device}")
        
        # Route to appropriate handler
        if message_type in self.message_handlers:
            try:
                result = self.message_handlers[message_type](packet)
                return {"status": "success", "message_type": message_type, "result": result}
            except Exception as e:
                error_msg = f"Error processing {message_type}: {str(e)}"
                logger.error(error_msg, exc_info=True)
                return {"status": "error", "message": error_msg}
        else:
            warning_msg = f"Unknown message type: {message_type}"
            logger.warning(warning_msg)
            return {"status": "warning", "message": warning_msg}
    
    # ==================== Packet Handlers ====================
    
    def _handle_available_devices(self, packet: Dict) -> Dict:
        """
        Handle available_devices packet (2.2.1).
        Updates the devices list in the Available Devices window.
        """
        body = packet.get("body", {})
        devices_data = body.get("devices", [])
        
        if not devices_data:
            logger.warning("available_devices packet has no devices")
            return {"message": "No devices in packet"}
        
        # Transform packet data to GUI format
        gui_devices = []
        for device in devices_data:
            gui_device = {
                "name": device.get("name", "Unknown Device"),
                "location": self._generate_location_from_name(device.get("name", "")),
                "status": self._map_status(device.get("status", "offline")),
                "connection": self._map_network_strength(device.get("network_strength", -100)),
                "metadata": self._generate_metadata(device)
            }
            gui_devices.append(gui_device)
        
        # Update GUI via handler
        update_command = {
            "command": "update_devices",
            "params": {"devices": gui_devices}
        }
        
        result = self.gui_handler.process_json(json.dumps(update_command))
        logger.info(f"Updated {len(gui_devices)} devices in GUI")
        return result
    
    def _handle_device_status(self, packet: Dict) -> Dict:
        """
        Handle device_status packet (2.2.2).
        Updates status of a specific device.
        """
        body = packet.get("body", {})
        device_name = body.get("name", "")
        
        if not device_name:
            logger.warning("device_status packet missing device name")
            return {"message": "No device name in packet"}
        
        # Map packet data to GUI status format
        status_update = {
            "status": self._map_processing_status(body.get("isProcessing", False)),
            "connection": self._map_network_strength(body.get("network_strength", -100)),
            "metadata": self._generate_status_metadata(body)
        }
        
        # Update GUI via handler
        update_command = {
            "command": "update_device_status",
            "params": {
                "device_name": device_name,
                "status": status_update
            }
        }
        
        result = self.gui_handler.process_json(json.dumps(update_command))
        logger.info(f"Updated status for device: {device_name}")
        return result
    
    def _handle_query_response(self, packet: Dict) -> Dict:
        """
        Handle query_response packet (2.2.3).
        Displays image and metadata in the Query window.
        
        Note: This handler supports multi-chunk responses. If total_chunks > 1,
        you may want to buffer chunks and combine them before displaying.
        """
        body = packet.get("body", {})
        query_id = body.get("query_id", "")
        metadata = body.get("metadata", {})
        frame = body.get("frame", {})
        
        # Extract image data
        image_base64 = metadata.get("image_base64", "")
        image_format = metadata.get("format", "jpeg")
        chunk_index = metadata.get("chunk_index", 0)
        total_chunks = metadata.get("total_chunks", 1)
        
        # Extract frame data
        detections = frame.get("detections", [])
        frame_id = frame.get("frame_id", 0)
        frame_timestamp = frame.get("timestamp", "")
        
        # TODO: For multi-chunk images, you may want to buffer and combine chunks
        # For now, we display each chunk as it arrives
        if total_chunks > 1:
            logger.info(f"Processing chunk {chunk_index + 1}/{total_chunks} for query {query_id}")
        
        # Build metadata for GUI (field names must match query.py metadata_labels)
        gui_metadata = {
            "image": f"frame_{frame_id}.{image_format}",
            "edge_device": packet.get("header", {}).get("source_device", "Unknown"),
            "query": f"Query ID: {query_id}",
            "response": self._format_detections(detections),
            "confidence_rate": self._calculate_confidence(detections),
            "time_processed": frame_timestamp or datetime.now().isoformat()
        }
        
        results = []
        
        # Display main image if available
        if image_base64:
            # Prepare base64 data URL
            image_data_url = f"data:image/{image_format};base64,{image_base64}"
            
            display_command = {
                "command": "display_image",
                "params": {
                    "image_data": image_base64,
                    "image_path": None
                }
            }
            result1 = self.gui_handler.process_json(json.dumps(display_command))
            results.append(result1)
            
            # Add to returned images
            add_image_command = {
                "command": "add_returned_image",
                "params": {
                    "image_data": image_base64,
                    "metadata": gui_metadata
                }
            }
            result2 = self.gui_handler.process_json(json.dumps(add_image_command))
            results.append(result2)
        
        # Update metadata
        metadata_command = {
            "command": "update_metadata",
            "params": {"metadata": gui_metadata}
        }
        result3 = self.gui_handler.process_json(json.dumps(metadata_command))
        results.append(result3)
        
        logger.info(f"Processed query_response for query_id: {query_id}")
        return {"message": "Query response processed", "results": results}
    
    def _handle_container_status(self, packet: Dict) -> Dict:
        """
        Handle container_status packet (2.2.4).
        Updates device status based on container information.
        """
        body = packet.get("body", {})
        source_device = packet.get("header", {}).get("source_device", "")
        
        if not source_device:
            logger.warning("container_status packet missing source device")
            return {"message": "No source device in packet"}
        
        # Map container status to device status
        container_status = body.get("status", "stopped")
        current_operation = body.get("current_operation", "idle")
        
        # Update device status
        status_update = {
            "status": self._map_container_status(container_status, current_operation),
            "metadata": f"Container: {container_status} • {current_operation}"
        }
        
        update_command = {
            "command": "update_device_status",
            "params": {
                "device_name": source_device,
                "status": status_update
            }
        }
        
        result = self.gui_handler.process_json(json.dumps(update_command))
        logger.info(f"Updated container status for device: {source_device}")
        return result
    
    def _handle_cancel_query_status(self, packet: Dict) -> Dict:
        """
        Handle cancel_query_status packet (1.2.4).
        Logs the cancellation status.
        """
        body = packet.get("body", {})
        query_id = body.get("query_id", "")
        status = body.get("status", "unknown")
        
        logger.info(f"Query {query_id} cancellation status: {status}")
        return {"message": f"Query cancellation: {status}", "query_id": query_id, "status": status}
    
    def _handle_discovery_response(self, packet: Dict) -> Dict:
        """
        Handle discovery_response packet (3.2.1).
        Updates the devices list from server response.
        """
        body = packet.get("body", {})
        devices_data = body.get("devices", [])
        
        if not devices_data:
            logger.warning("discovery_response packet has no devices")
            return {"message": "No devices in discovery response"}
        
        # Transform packet data to GUI format (same as available_devices)
        gui_devices = []
        for device in devices_data:
            gui_device = {
                "name": device.get("name", "Unknown Device"),
                "location": self._generate_location_from_name(device.get("name", "")),
                "status": self._map_status(device.get("status", "offline")),
                "connection": self._map_network_strength(device.get("network_strength", -100)),
                "metadata": self._generate_metadata(device)
            }
            gui_devices.append(gui_device)
        
        # Update GUI via handler
        update_command = {
            "command": "update_devices",
            "params": {"devices": gui_devices}
        }
        
        result = self.gui_handler.process_json(json.dumps(update_command))
        logger.info(f"Updated {len(gui_devices)} devices from discovery response")
        return result
    
    # ==================== Helper Methods ====================
    
    def _map_status(self, status: str) -> str:
        """Map packet status to GUI status string."""
        status_map = {
            "online": "Online",
            "offline": "Offline",
            "Needs Attention": "Needs Attention"
        }
        return status_map.get(status.lower(), status)
    
    def _map_network_strength(self, strength: int) -> str:
        """Map network strength (dBm) to connection quality string."""
        if strength >= -50:
            return "Excellent"
        elif strength >= -60:
            return "Strong"
        elif strength >= -70:
            return "Medium"
        elif strength >= -80:
            return "Weak"
        else:
            return "Very Weak"
    
    def _map_processing_status(self, is_processing: bool) -> str:
        """Map processing flag to status string."""
        return "Processing" if is_processing else "Online"
    
    def _map_container_status(self, container_status: str, operation: str) -> str:
        """Map container status to device status."""
        if container_status == "error":
            return "Error"
        elif container_status == "stopped":
            return "Offline"
        elif operation == "processing":
            return "Processing"
        elif operation == "loading_model":
            return "Loading"
        else:
            return "Online"
    
    def _generate_location_from_name(self, device_name: str) -> str:
        """Generate a location string from device name.
        
        Note: The packetStructure.md does not include a 'location' field.
        This is auto-generated for display purposes. In a real implementation,
        you might maintain a separate device registry with location data,
        or extend the packet structure to include location information.
        """
        if not device_name:
            return "Location unknown"
        
        # Extract device number if present for varied location descriptions
        device_locations = {
            "Edge Device 1": "This Edge Device is located in room 131 of Fayetteville University Lyon Science Annex.",
            "Edge Device 2": "This Edge Device is located in hallway of Fayetteville University Lyon Science Annex.",
            "Edge Device 3": "This Edge Device is located in room 132 of Fayetteville University Lyon Science Annex.",
        }
        
        return device_locations.get(device_name, f"This Edge Device is located at {device_name}.")
    
    def _generate_metadata(self, device: Dict) -> str:
        """Generate metadata string from device data."""
        parts = []
        
        # Add version if available (from metadata or other fields)
        if "version" in device:
            parts.append(f"v{device['version']}")
        
        # Add status indicator
        status = device.get("status", "unknown")
        if status == "online":
            if device.get("isProcessing", False):
                parts.append("Processing")
            else:
                parts.append("Active")
        elif status == "offline":
            parts.append("Offline")
        
        return " • ".join(parts) if parts else "Active"
    
    def _generate_status_metadata(self, body: Dict) -> str:
        """Generate metadata string from device status body."""
        parts = []
        
        # Add CPU/RAM/GPU if available
        cpu = body.get("cpu", 0)
        ram = body.get("ram", 0)
        gpu = body.get("gpu", 0)
        
        if cpu > 0 or ram > 0 or gpu > 0:
            resource_parts = []
            if cpu > 0:
                resource_parts.append(f"CPU: {cpu:.1f}%")
            if ram > 0:
                resource_parts.append(f"RAM: {ram:.1f}%")
            if gpu > 0:
                resource_parts.append(f"GPU: {gpu:.1f}%")
            if resource_parts:
                parts.append(" • ".join(resource_parts))
        
        # Add processing status
        if body.get("isProcessing", False):
            parts.append("Processing")
        else:
            parts.append("Idle")
        
        return " • ".join(parts) if parts else "Active"
    
    def _format_detections(self, detections: list) -> str:
        """Format detection list into readable string."""
        if not detections:
            return "No detections"
        
        detection_strings = []
        for det in detections:
            label = det.get("label", "Unknown")
            confidence = det.get("confidence", 0.0)
            detection_strings.append(f"{label} ({confidence:.1%})")
        
        return ", ".join(detection_strings)
    
    def _calculate_confidence(self, detections: list) -> str:
        """Calculate average confidence from detections."""
        if not detections:
            return "N/A"
        
        confidences = [det.get("confidence", 0.0) for det in detections]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return f"{avg_confidence:.1%}"


def simulate_discovery_response(packet_handler: MQTTPacketHandler):
    """
    Simulate a discovery_response packet from the server.
    In real usage, this would come from MQTT broker.
    
    This demonstrates how discovery_response (packetStructure.md section 3.2.1)
    populates the Available Devices GUI.
    """
    discovery_response = {
        "header": {
            "timestamp": datetime.now().isoformat(),
            "source_device": "server",
            "message_type": "discovery_response"
        },
        "body": {
            "devices": [
                {
                    "name": "Edge Device 1",
                    "status": "online",
                    "cpu": 45.5,
                    "ram": 60.2,
                    "gpu": 30.0,
                    "network_strength": -55,
                    "isProcessing": False
                },
                {
                    "name": "Edge Device 2",
                    "status": "online",
                    "cpu": 30.0,
                    "ram": 50.0,
                    "gpu": 20.0,
                    "network_strength": -65,
                    "isProcessing": True
                },
                {
                    "name": "Edge Device 3",
                    "status": "offline",
                    "cpu": 0.0,
                    "ram": 0.0,
                    "gpu": 0.0,
                    "network_strength": -85,
                    "isProcessing": False
                }
            ]
        }
    }
    
    print(f"\n[DISCOVERY RESPONSE] Received discovery_response packet:")
    print(json.dumps(discovery_response, indent=2))
    
    # Process the packet - this will update the Available Devices GUI
    result = packet_handler.process_packet(json.dumps(discovery_response))
    print(f"\n[DISCOVERY RESPONSE] Processing result: {result}")


def simulate_query_response(packet_handler: MQTTPacketHandler, query_text: str):
    """
    Simulate a query_response packet from an edge device.
    In real usage, this would come from MQTT broker after sending query_request.
    
    This demonstrates how query_response (packetStructure.md section 2.2.3)
    populates the Query window with image and metadata.
    """
    import uuid
    
    # Create a simple 1x1 pixel PNG as base64 for demo
    # In real usage, this would be actual image data from edge device
    demo_image_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    
    query_response = {
        "header": {
            "timestamp": datetime.now().isoformat(),
            "source_device": "Edge Device 1",
            "message_type": "query_response"
        },
        "body": {
            "query_id": str(uuid.uuid4()),
            "metadata": {
                "image_width": 1920,
                "image_height": 1080,
                "format": "jpeg",
                "image_base64": demo_image_base64,
                "chunk_index": 0,
                "total_chunks": 1
            },
            "frame": {
                "frame_id": 1,
                "timestamp": datetime.now().isoformat(),
                "detections": [
                    {
                        "label": "person",
                        "confidence": 0.95,
                        "dets": ["bbox1"]
                    },
                    {
                        "label": "car",
                        "confidence": 0.87,
                        "dets": ["bbox2"]
                    }
                ]
            }
        }
    }
    
    print(f"\n[QUERY RESPONSE] Received query_response packet for query: '{query_text}'")
    print(json.dumps(query_response, indent=2))
    
    # Process the packet - this will update the Query window
    result = packet_handler.process_packet(json.dumps(query_response))
    print(f"\n[QUERY RESPONSE] Processing result: {result}")


def main():
    """Example demonstrating MQTT packet handler usage."""
    app = QApplication(sys.argv)
    
    # Create and show the available devices window first
    devices_window = AvailableDevicesWindow()
    devices_window.show()
    
    # Query window will be created on-demand when Query button is clicked
    query_window = None
    
    # Create GUI handler
    gui_handler = GUIHandler(
        available_devices_window=devices_window,
        query_window=query_window
    )
    
    # Create MQTT packet handler
    packet_handler = MQTTPacketHandler(gui_handler)
    
    # === DISCOVERY CALLBACK SETUP ===
    # This callback is called when the user clicks the "Discover" button
    # In a real implementation, this would send an MQTT message
    def on_discover_requested():
        """
        Called when user clicks Discover button.
        Sends a discovery_request packet as per packetStructure.md section 3.1.
        """
        discovery_request = {
            "header": {
                "timestamp": datetime.now().isoformat(),
                "source_device": "host_device",
                "message_type": "discovery_request"
            },
            "body": {}
        }
        print(f"\n[DISCOVER] Sending discovery_request packet:")
        print(json.dumps(discovery_request, indent=2))
        
        # In real implementation: mqtt_client.publish("topic/discovery", json.dumps(discovery_request))
        
        # For demo purposes, simulate a discovery_response after a short delay
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, lambda: simulate_discovery_response(packet_handler))
    
    # Register the discover callback with the devices window
    devices_window.set_discover_callback(on_discover_requested)
    
    # === QUERY CALLBACK SETUP ===
    def on_query_requested(query_text: str):
        """
        Called when user clicks Send in the Query window.
        Sends a query_request packet as per packetStructure.md section 2.1.
        """
        import uuid
        query_request = {
            "header": {
                "timestamp": datetime.now().isoformat(),
                "source_device": "host_device",
                "message_type": "query_request"
            },
            "body": {
                "query_id": str(uuid.uuid4()),
                "query": query_text
            }
        }
        print(f"\n[QUERY] Sending query_request packet:")
        print(json.dumps(query_request, indent=2))
        
        # In real implementation: mqtt_client.publish("topic/query", json.dumps(query_request))
        
        # For demo purposes, simulate a query_response after a short delay
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(800, lambda: simulate_query_response(packet_handler, query_text))
    
    # Function to update handler when query window is created
    def update_handler_query_window():
        nonlocal query_window
        if devices_window._query_window and devices_window._query_window != query_window:
            query_window = devices_window._query_window
            gui_handler.query_window = query_window
            # Register the query callback
            query_window.set_query_callback(on_query_requested)
            logger.info("Query window created and registered with handler")
    
    # Timer to check for query window creation
    from PyQt6.QtCore import QTimer
    query_check_timer = QTimer()
    query_check_timer.timeout.connect(update_handler_query_window)
    query_check_timer.start(500)  # Check every 500ms

    print("\n" + "="*60)
    print("MQTT Packet Handler Example")
    print("="*60)
    print("WORKFLOW:")
    print("1. Available Devices window is now open (initially empty)")
    print("2. Click 'Discover' to send discovery_request and receive devices")
    print("3. Click 'Query' to open the Query window")
    print("4. Enter a query and click 'Send' to get image results")
    print("="*60)
    print("\nPacket flow (as per packetStructure.md):")
    print("  - Discover button -> sends 'discovery_request' (section 3.1)")
    print("  - Server responds with 'discovery_response' (section 3.2)")
    print("  - Query 'Send' -> sends 'query_request' (section 2.1)")
    print("  - Edge responds with 'query_response' (section 2.2)")
    print("="*60)
    print("\nExample packet formats:")
    print("\n1. available_devices packet:")
    print(json.dumps({
        "header": {
            "timestamp": datetime.now().isoformat(),
            "source_device": "edge_device_1",
            "message_type": "available_devices"
        },
        "body": {
            "devices": [
                {
                    "name": "Edge Device 1",
                    "status": "online",
                    "cpu": 45.5,
                    "ram": 60.2,
                    "gpu": 30.0,
                    "network_strength": -55
                }
            ]
        }
    }, indent=2))
    
    print("\n2. query_response packet:")
    print(json.dumps({
        "header": {
            "timestamp": datetime.now().isoformat(),
            "source_device": "edge_device_1",
            "message_type": "query_response"
        },
        "body": {
            "query_id": "123e4567-e89b-12d3-a456-426614174000",
            "metadata": {
                "image_width": 1920,
                "image_height": 1080,
                "format": "jpeg",
                "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
                "chunk_index": 0,
                "total_chunks": 1
            },
            "frame": {
                "frame_id": 1,
                "timestamp": datetime.now().isoformat(),
                "detections": [
                    {
                        "label": "person",
                        "confidence": 0.95,
                        "dets": ["det1"]
                    }
                ]
            }
        }
    }, indent=2))
    
    print("\n" + "="*60)
    print("To process a packet, use:")
    print("  packet_handler.process_packet(packet_json_string)")
    print("="*60 + "\n")
    
    # Example: Process a sample available_devices packet
    sample_packet = {
        "header": {
            "timestamp": datetime.now().isoformat(),
            "source_device": "edge_device_1",
            "message_type": "available_devices"
        },
        "body": {
            "devices": [
                {
                    "name": "Edge Device 1",
                    "status": "online",
                    "cpu": 45.5,
                    "ram": 60.2,
                    "gpu": 30.0,
                    "network_strength": -55
                },
                {
                    "name": "Edge Device 2",
                    "status": "online",
                    "cpu": 30.0,
                    "ram": 50.0,
                    "gpu": 20.0,
                    "network_strength": -65
                }
            ]
        }
    }
    
    # Uncomment to test packet processing:
    # result = packet_handler.process_packet(json.dumps(sample_packet))
    # print(f"Packet processing result: {result}")
    
    # Run the application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
