#!/usr/bin/env python3
"""
Sentinel Nexus V2 - Edge Network Server
TCP server that handles connections from host computers and manages VILA AI processing.
"""

import socket
import threading
import json
import time
import logging
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import base64
import cv2
import numpy as np
from query_handler import QueryHandler
from vila_integration import VILAProcessor
from data_triage_controller import DataTriageController

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('edge_server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class MessageTypes(Enum):
    DISCOVERY_REQUEST = "discovery_request"
    DISCOVERY_RESPONSE = "discovery_response"
    CONNECT = "connect"
    CONNECT_RESPONSE = "connect_response"
    QUERY = "query"
    QUERY_RESPONSE = "query_response"
    LIVE_FEED_STARTED = "live_feed_started"
    LIVE_FEED_RESULT = "live_feed_result"
    LIVE_FEED_STOPPED = "live_feed_stopped"
    LIVE_FEED_ERROR = "live_feed_error"
    HEARTBEAT = "heartbeat"
    HEARTBEAT_RESPONSE = "heartbeat_response"
    IMAGE_DATA = "image_data"
    STOP = "stop"
    STOP_RESPONSE = "stop_response"
    DISCONNECT = "disconnect"
    DISCONNECT_RESPONSE = "disconnect_response"
    EXIT = "exit"
    EXIT_RESPONSE = "exit_response"
    ERROR = "error"
    STATUS_UPDATE = "status_update"


@dataclass
class ClientConnection:
    """Represents a connected client"""
    socket: socket.socket
    address: tuple
    last_heartbeat: float
    client_id: str
    connected: bool = True
    streaming: bool = False  # Whether client is receiving streaming results

    def send_live_feed_result(self, live_feed_data):
        """Send live feed result to this client"""
        try:
            message = Message(
                type=MessageTypes.LIVE_FEED_RESULT.value,
                data=live_feed_data,
                timestamp=time.time(),
                message_id=f"stream_{int(time.time())}",
                device_id="jetson_orin_nano"
            )

            # Send the message using the server's send method
            # We'll need to pass the server instance or create a method here
            return message
        except Exception as e:
            logger.error(f"Error creating live feed result message: {e}")
            return None


@dataclass
class Message:
    """Standard message structure"""
    type: str
    data: Dict[str, Any]
    timestamp: float
    message_id: str
    device_id: str = "edge_device"


class EdgeNetworkServer:
    """TCP server that handles connections from host computers"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8080, max_clients: int = 5):
        self.host = host
        self.port = port
        self.max_clients = max_clients
        self.server_socket = None
        self.clients: Dict[str, ClientConnection] = {}
        self.running = False
        self.query_handler = QueryHandler()
        self.vila_processor = None
        self.device_id = "jetson_orin_nano"
        self.model_status = "not_loaded"

        # Initialize data triage controller (enabled by default for testing)
        # Use video0 - same camera as VILA (Linux can handle multiple readers)
        video_source = 0  # Use /dev/video0 - same as VILA
        try:
            self.triage_controller = DataTriageController(
                video_source=video_source, width=1280, height=720, jpeg_quality=85)
            # Don't initialize camera at startup - will initialize on first capture
            # This allows VILA to start first, then we can share the camera
            self.triage_controller.enable()  # Enable for testing
            logger.info(
                f"Data triage controller initialized (will use /dev/video{video_source} on first capture)")
        except Exception as e:
            logger.warning(
                f"Could not initialize triage controller: {e}, will attempt capture anyway")
            self.triage_controller = DataTriageController(
                video_source=video_source, width=1280, height=720, jpeg_quality=85)
            self.triage_controller.enable()

        # Clean up any lingering containers on startup
        self._cleanup_containers()

        # VILA processor will be initialized on first query

    def _cleanup_containers(self):
        """Clean up any lingering Docker containers on startup and shutdown"""
        try:
            logger.info("Cleaning up any lingering Docker containers...")

            # Stop all running containers
            try:
                result = subprocess.run(
                    ["docker", "ps", "-q"],
                    capture_output=True,
                    text=True,
                    timeout=5  # Shorter timeout
                )
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Timeout getting container list, trying force cleanup...")
                result = None
            except KeyboardInterrupt:
                logger.warning("Interrupted while getting container list")
                return

            if result and result.returncode == 0 and result.stdout.strip():
                container_ids = result.stdout.strip().split('\n')
                logger.info(
                    f"Found {len(container_ids)} running containers, stopping them...")

                for container_id in container_ids:
                    if container_id:
                        try:
                            container_id = container_id.strip()
                            if not container_id:
                                continue

                            # Try graceful stop first with short timeout
                            logger.info(
                                f"Attempting to stop container {container_id}...")
                            stop_process = subprocess.Popen(
                                ["docker", "stop", container_id],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE
                            )

                            try:
                                # Very short timeout
                                stop_process.wait(timeout=3)
                                if stop_process.returncode == 0:
                                    logger.info(
                                        f"Stopped container {container_id}")
                                else:
                                    logger.warning(
                                        f"Container {container_id} stop returned code {stop_process.returncode}, forcing kill...")
                                    raise subprocess.TimeoutExpired("stop", 3)
                            except subprocess.TimeoutExpired:
                                logger.warning(
                                    f"Timeout stopping container {container_id}, forcing kill...")
                                stop_process.kill()
                                stop_process.wait(timeout=1)

                                # Force kill immediately
                                kill_process = subprocess.Popen(
                                    ["docker", "kill", container_id],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE
                                )
                                try:
                                    kill_process.wait(timeout=3)
                                    logger.info(
                                        f"Force killed container {container_id}")
                                except subprocess.TimeoutExpired:
                                    kill_process.kill()
                                    logger.warning(
                                        f"Could not kill container {container_id}, may need manual cleanup")
                            except KeyboardInterrupt:
                                logger.warning(
                                    f"Interrupted while stopping container {container_id}")
                                stop_process.kill()
                                return
                        except Exception as e:
                            logger.warning(
                                f"Error stopping container {container_id}: {e}")

            # Remove all stopped containers (with shorter timeout)
            try:
                result = subprocess.run(
                    ["docker", "ps", "-aq"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                logger.warning(
                    "Timeout or interrupt getting stopped container list, skipping removal")
                result = None

            if result and result.returncode == 0 and result.stdout.strip():
                container_ids = result.stdout.strip().split('\n')
                logger.info(
                    f"Found {len(container_ids)} stopped containers, removing them...")

                for container_id in container_ids:
                    if container_id:
                        try:
                            container_id = container_id.strip()
                            if not container_id:
                                continue

                            # Use Popen for better control
                            rm_process = subprocess.Popen(
                                ["docker", "rm", container_id],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE
                            )
                            try:
                                rm_process.wait(timeout=3)
                                if rm_process.returncode == 0:
                                    logger.info(
                                        f"Removed container {container_id}")
                                else:
                                    logger.warning(
                                        f"Could not remove container {container_id} (may not exist)")
                            except subprocess.TimeoutExpired:
                                logger.warning(
                                    f"Timeout removing container {container_id}")
                                rm_process.kill()
                            except KeyboardInterrupt:
                                logger.warning(
                                    f"Interrupted while removing container {container_id}")
                                rm_process.kill()
                                return
                        except Exception as e:
                            logger.warning(
                                f"Error removing container {container_id}: {e}")

            logger.info("Container cleanup completed")

        except KeyboardInterrupt:
            logger.warning("Container cleanup interrupted by user")
        except subprocess.TimeoutExpired:
            logger.warning("Container cleanup timed out, continuing...")
        except Exception as e:
            logger.error(f"Error during container cleanup: {e}")

    def _initialize_vila(self):
        """Initialize VILA processor on first query"""
        try:
            logger.info("Initializing VILA processor...")
            self.model_status = "loading"
            logger.info("This may take 15-20 seconds for model loading...")

            # Send initial loading status according to protocol
            self._broadcast_status_update(
                message="Loading VILA-1.5-3b model... This may take a few minutes.",
                status_type="model_loading",
                progress=0,
                estimated_time=300,
                current_step="Initializing model components"
            )

            # Create VILA processor
            self.vila_processor = VILAProcessor()
            # Set server instance reference so VILA can send results to all clients
            self.vila_processor.set_server_instance(self)

            # Send progress update
            self._broadcast_status_update(
                message="Starting VILA Docker container...",
                status_type="model_loading",
                progress=25,
                current_step="Starting Docker container"
            )

            # Start VILA process (this will start the Docker container)
            self.vila_processor._start_vila_process()

            # Send progress update
            self._broadcast_status_update(
                message="VILA Docker container started, waiting for model to be ready...",
                status_type="model_loading",
                progress=50,
                current_step="Waiting for model initialization"
            )

            # Wait for model to be ready with timeout
            import time
            start_time = time.time()
            timeout = 60  # 60 seconds timeout

            while time.time() - start_time < timeout:
                if self.vila_processor.model_ready:
                    self.model_status = "ready"
                    logger.info(
                        "VILA processor initialized successfully - ready for queries!")

                    # Send completion status according to protocol
                    self._broadcast_status_update(
                        message="VILA-1.5-3b model loaded successfully and ready for analysis.",
                        status_type="model_ready",
                        progress=100,
                        load_time=15.0,  # Approximate load time
                        model_size="1.5B parameters",
                        memory_usage="2.1GB"
                    )
                    return True

                time.sleep(1)

            # If we get here, model loading timed out
            raise Exception("VILA model loading timed out")

        except Exception as e:
            logger.error(f"Failed to initialize VILA processor: {e}")
            self.model_status = "error"
            self._broadcast_status_update(
                message=f"Failed to load VILA model: {e}",
                status_type="model_error",
                error_code="MODEL_LOAD_ERROR",
                error_details=str(e),
                suggestions=["Check system resources",
                             "Restart edge device", "Check Docker container"]
            )
            return False

    def _broadcast_status_update(self, message: str, status_type: str = "model_loading", progress: int = 0, estimated_time: int = 0, **kwargs):
        """Broadcast status update to all connected clients"""
        try:
            status_data = {
                'status_type': status_type,
                'message': message,
                'progress': progress,
                'estimated_time': estimated_time,
                'timestamp': time.time(),
                **kwargs
            }

            status_message = Message(
                type=MessageTypes.STATUS_UPDATE.value,
                data=status_data,
                timestamp=time.time(),
                message_id=f"status_{int(time.time())}",
                device_id=self.device_id
            )

            for client_id, client in self.clients.items():
                try:
                    self._send_message(status_message, client)
                    logger.info(
                        f"Status update sent to {client.address}: {status_type} - {message}")
                except Exception as e:
                    logger.error(
                        f"Failed to send status update to {client.address}: {e}")

        except Exception as e:
            logger.error(f"Error broadcasting status update: {e}")

    def start_server(self):
        """Start the TCP server"""
        try:
            self.server_socket = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(self.max_clients)

            self.running = True
            logger.info(
                f"Edge Network Server started on {self.host}:{self.port}")
            logger.info(f"Max clients: {self.max_clients}")
            logger.info(f"Model status: {self.model_status}")

            # Start heartbeat monitor
            heartbeat_thread = threading.Thread(
                target=self._heartbeat_monitor, daemon=True)
            heartbeat_thread.start()

            # Accept connections
            while self.running:
                try:
                    client_socket, address = self.server_socket.accept()
                    if len(self.clients) >= self.max_clients:
                        logger.warning(
                            f"Max clients reached, rejecting connection from {address}")
                        client_socket.close()
                        continue

                    client_id = f"client_{len(self.clients)}_{int(time.time())}"
                    client = ClientConnection(
                        socket=client_socket,
                        address=address,
                        last_heartbeat=time.time(),
                        client_id=client_id
                    )

                    self.clients[client_id] = client
                    logger.info(
                        f"Client connected: {address} (ID: {client_id})")

                    # Handle client in separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client,),
                        daemon=True
                    )
                    client_thread.start()

                except Exception as e:
                    if self.running:
                        logger.error(f"Error accepting connection: {e}")

        except Exception as e:
            logger.error(f"Failed to start server: {e}")
        finally:
            self.stop_server()

    def _handle_client(self, client: ClientConnection):
        """Handle communication with a specific client"""
        try:
            while client.connected and self.running:
                # Receive message
                message = self._receive_message(client)
                if not message:
                    # No message received, but keep connection alive
                    continue

                # Update last_heartbeat on ANY message (not just heartbeat) to prevent timeout
                # Any message from client indicates they're still active
                client.last_heartbeat = time.time()

                # Process message
                response = self._process_message(message, client)
                if response:
                    logger.info(
                        f"Sending response: {response.type} to {client.address}")
                    self._send_message(response, client)
                else:
                    logger.warning(
                        f"No response generated for message type: {message.type}")

        except Exception as e:
            logger.error(f"Error handling client {client.client_id}: {e}")
        finally:
            self._disconnect_client(client)

    def _receive_message(self, client: ClientConnection) -> Optional[Message]:
        """Receive a message from client"""
        try:
            # Check if client is still connected before attempting to receive
            if not client.connected or not client.socket:
                return None

            # First, try to receive a small message (JSON only)
            client.socket.settimeout(1.0)
            data = client.socket.recv(1024)
            if not data:
                return None

            # Try to parse as JSON
            try:
                message_data = json.loads(data.decode('utf-8'))
                return Message(
                    type=message_data.get('type', ''),
                    data=message_data.get('data', {}),
                    timestamp=message_data.get('timestamp', time.time()),
                    message_id=message_data.get(
                        'message_id', f"msg_{int(time.time())}"),
                    device_id=message_data.get('device_id', self.device_id)
                )
            except json.JSONDecodeError:
                # Try length-prefixed protocol
                if len(data) >= 4:
                    length = int.from_bytes(data[:4], byteorder='big')
                    if len(data) >= 4 + length:
                        json_data = data[4:4+length]
                        message_data = json.loads(json_data.decode('utf-8'))
                        return Message(
                            type=message_data.get('type', ''),
                            data=message_data.get('data', {}),
                            timestamp=message_data.get(
                                'timestamp', time.time()),
                            message_id=message_data.get('message_id', ''),
                            device_id=message_data.get(
                                'device_id', self.device_id)
                        )

            return None

        except socket.timeout:
            # Timeout is normal, just continue waiting
            return None
        except (OSError, ValueError) as e:
            # Socket errors (including Bad file descriptor) indicate connection is broken
            # This is expected when client disconnects
            if client.connected:
                logger.debug(
                    f"Socket error receiving message (connection may be closed): {e}")
            return None
        except Exception as e:
            logger.error(f"Error receiving message: {e}")
            return None

    def _send_message(self, message: Message, client: ClientConnection):
        """Send a message to client"""
        try:
            message_data = {
                'type': message.type,
                'data': message.data,
                'timestamp': message.timestamp,
                'message_id': message.message_id,
                'device_id': message.device_id
            }

            json_data = json.dumps(message_data).encode('utf-8')

            # Use length-prefixed protocol for larger messages
            if len(json_data) >= 1024:
                length_prefix = len(json_data).to_bytes(4, byteorder='big')
                full_message = length_prefix + json_data
            else:
                full_message = json_data

            client.socket.sendall(full_message)

        except Exception as e:
            logger.error(f"Error sending message: {e}")

    def _process_message(self, message: Message, client: ClientConnection) -> Optional[Message]:
        """Process incoming message and generate response"""
        try:
            # Handle empty or malformed message types
            if not message.type or message.type == '':
                # Check if it looks like a stop command based on data
                if message.data and any(keyword in str(message.data).lower() for keyword in ['stop', 'shutdown', 'exit', 'quit', 'close']):
                    logger.info(
                        "Detected stop command with empty type, treating as stop")
                    return self._handle_stop(message, client)
                # Check if it looks like a query based on data
                elif message.data and 'query' in message.data:
                    logger.info(
                        "Detected query message with empty type, treating as query")
                    return self._handle_query(message, client)
                # Check if it looks like a heartbeat based on data
                elif message.data and message.data.get('status') == 'alive':
                    logger.info(
                        "Detected heartbeat message with empty type, treating as heartbeat")
                    return self._handle_heartbeat(message, client)
                else:
                    logger.warning(f"Empty message type received: {message}")
                    logger.info(f"Message data content: {message.data}")
                    logger.info(
                        f"Message keys: {list(message.data.keys()) if message.data else 'No data'}")

                    # If we can't identify the message type, but it's from a client,
                    # it might be a stop command from the UI
                    logger.info(
                        "Treating unknown empty message type as potential stop command")
                    return self._handle_stop(message, client)

            if message.type == MessageTypes.DISCOVERY_REQUEST.value:
                return self._handle_discovery_request(message, client)
            elif message.type == MessageTypes.CONNECT.value:
                return self._handle_connect(message, client)
            elif message.type == MessageTypes.QUERY.value:
                return self._handle_query(message, client)
            elif message.type == MessageTypes.HEARTBEAT.value:
                return self._handle_heartbeat(message, client)
            elif message.type == MessageTypes.STOP.value:
                return self._handle_stop(message, client)
            elif message.type == MessageTypes.DISCONNECT.value:
                return self._handle_disconnect(message, client)
            elif message.type == MessageTypes.EXIT.value:
                return self._handle_exit(message, client)
            else:
                logger.warning(f"Unknown message type: '{message.type}'")
                logger.info(f"Received message: {message}")
                # Return error message instead of None
                return self._create_error_message(f"Unknown message type: {message.type}", message.message_id or "unknown")

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return self._create_error_message(str(e), message.message_id)

    def _handle_discovery_request(self, message: Message, client: ClientConnection) -> Message:
        """Handle device discovery request"""
        logger.info(f"Discovery request from {client.address}")

        discovery_data = {
            'device_id': self.device_id,
            'device_type': 'jetson_orin_nano',
            'capabilities': ['video_analysis', 'vila_processing'],
            'model_status': self.model_status,
            'model_ready': self.model_status == "ready",
            'model_loading': self.model_status == "loading",
            'camera_available': True,
            'max_resolution': '1280x720',
            'supported_formats': ['jpeg', 'rgb'],
            'processing_fps': 0.5,
            'memory_usage': 'optimized',
            'model_auto_load': False  # Model loads on first query
        }

        return Message(
            type=MessageTypes.DISCOVERY_RESPONSE.value,
            data=discovery_data,
            timestamp=time.time(),
            message_id=message.message_id,
            device_id=self.device_id
        )

    def _handle_connect(self, message: Message, client: ClientConnection) -> Message:
        """Handle connection request"""
        logger.info(f"Connection request from {client.address}")

        connect_data = {
            'status': 'connected',
            'device_id': self.device_id,
            'model_status': self.model_status,
            'capabilities': ['video_analysis', 'vila_processing'],
            'timestamp': time.time()
        }

        return Message(
            type=MessageTypes.CONNECT_RESPONSE.value,
            data=connect_data,
            timestamp=time.time(),
            message_id=message.message_id,
            device_id=self.device_id
        )

    def _handle_query(self, message: Message, client: ClientConnection) -> Message:
        """Handle AI query request"""
        logger.info(
            f"Query request from {client.address}: {message.data.get('query', '')}")

        try:
            query = message.data.get('query', '')
            if not query:
                raise ValueError("No query provided")

            # Initialize VILA processor if not already done
            if self.model_status == "not_loaded":
                logger.info("Model not loaded, initializing VILA...")
                if not self._initialize_vila():
                    raise ValueError("Failed to initialize VILA model")

            # Process query with VILA
            if self.vila_processor and self.model_status == "ready":
                # Send processing status
                self._send_status_update(
                    message="Processing query with VILA model...",
                    client=client,
                    status_type="query_processing",
                    progress=50
                )

                # Send live feed started message
                self._send_live_feed_started(query, client)

                # Check if this is a streaming request
                streaming_mode = message.data.get('streaming', False)

                if streaming_mode:
                    # Start streaming mode
                    logger.info(
                        f"Starting streaming mode for client {client.client_id}")
                    client.streaming = True
                    self.vila_processor.start_streaming(client)

                    # Send initial result if available
                    if self.vila_processor.last_result:
                        live_feed_data = {
                            'analysis': self.vila_processor.last_result.get('response', ''),
                            'confidence': self.vila_processor.last_result.get('confidence', 0.8),
                            'processing_time': self.vila_processor.last_result.get('processing_time', 1.5),
                            'frame_number': self.vila_processor.last_result.get('frame_number', 1),
                            'query_text': query,
                            'timestamp': time.time(),
                            'model_version': 'VILA-1.5-3b',
                            'inference_device': 'CUDA',
                            'frame_metadata': {
                                'resolution': '1280x720',
                                'fps': 30,
                                'compression': 'JPEG',
                                'quality': 85
                            }
                        }

                        logger.info(
                            f"Streaming started - initial result: {self.vila_processor.last_result.get('response', '')}")
                        return Message(
                            type=MessageTypes.LIVE_FEED_RESULT.value,
                            data=live_feed_data,
                            timestamp=time.time(),
                            message_id=message.message_id,
                            device_id=self.device_id
                        )
                    else:
                        # No result yet, just confirm streaming started
                        return Message(
                            type=MessageTypes.LIVE_FEED_STARTED.value,
                            data={
                                'streaming': True, 'message': 'Streaming started, waiting for analysis...'},
                            timestamp=time.time(),
                            message_id=message.message_id,
                            device_id=self.device_id
                        )
                else:
                    # Single query mode (original behavior)
                    result = self.vila_processor.process_query(query)

                    # Capture image for this query (data triage test)
                    image_data_dict = None
                    logger.info("Attempting to capture image for query...")
                    if self.triage_controller and self.triage_controller.enabled:
                        try:
                            logger.info(
                                f"Triage controller enabled, camera initialized: {self.triage_controller.frame_capture.is_initialized()}")
                            image_data_dict = self.triage_controller.capture_image_for_query(
                                query)
                            if image_data_dict:
                                logger.info(
                                    f"✓ Captured image for query: {image_data_dict['size_bytes']} bytes, {image_data_dict.get('width')}x{image_data_dict.get('height')}")
                            else:
                                logger.warning(
                                    "Image capture returned None (camera may not be available)")
                        except Exception as e:
                            logger.error(
                                f"Error capturing image for query: {e}", exc_info=True)
                    else:
                        logger.warning(
                            "Triage controller not enabled or not available")

                    # Send live feed result message
                    live_feed_data = {
                        'analysis': result.get('response', ''),
                        'confidence': result.get('confidence', 0.0),
                        'processing_time': result.get('processing_time', 0.0),
                        'frame_number': result.get('frame_count', 1),
                        'query_text': query,
                        'timestamp': time.time(),
                        'model_version': 'VILA-1.5-3b',
                        'inference_device': 'CUDA',
                        'frame_metadata': {
                            'resolution': '1280x720',
                            'fps': 30,
                            'compression': 'JPEG',
                            'quality': 85
                        }
                    }

                    logger.info(
                        f"Sending live feed result: {result.get('response', '')}")

                    # Send image data if available from triage controller
                    if image_data_dict and image_data_dict.get('jpeg_bytes'):
                        self._send_image_data(image_data_dict['jpeg_bytes'], client,
                                              width=image_data_dict.get(
                                                  'width', 1280),
                                              height=image_data_dict.get('height', 720))

                    # Send image data if available from VILA result (legacy)
                    if 'image_data' in result and result['image_data']:
                        self._send_image_data(result['image_data'], client)

                    return Message(
                        type=MessageTypes.LIVE_FEED_RESULT.value,
                        data=live_feed_data,
                        timestamp=time.time(),
                        message_id=message.message_id,
                        device_id=self.device_id
                    )
            elif self.model_status == "loading":
                # Send status update that model is still loading
                self._send_status_update(
                    message="Model is still loading, please wait...",
                    client=client,
                    status_type="model_loading",
                    progress=75
                )
                raise ValueError("Model is still loading, please wait")
            else:
                raise ValueError(
                    f"Model not ready (status: {self.model_status})")

        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return self._create_live_feed_error_message(str(e), message.message_id)

    def _send_status_update(self, message: str, client: ClientConnection, status_type: str = "model_loading", progress: int = 0, **kwargs):
        """Send status update to specific client"""
        try:
            status_data = {
                'status_type': status_type,
                'message': message,
                'progress': progress,
                'timestamp': time.time(),
                **kwargs
            }

            status_message = Message(
                type=MessageTypes.STATUS_UPDATE.value,
                data=status_data,
                timestamp=time.time(),
                message_id=f"status_{int(time.time())}",
                device_id=self.device_id
            )

            self._send_message(status_message, client)
            logger.info(
                f"Status update sent to {client.address}: {status_type} - {message}")

        except Exception as e:
            logger.error(f"Error sending status update: {e}")

    def _handle_heartbeat(self, message: Message, client: ClientConnection) -> Message:
        """Handle heartbeat request"""
        client.last_heartbeat = time.time()
        logger.info(
            f"Heartbeat received from {client.address}, responding with status: {self.model_status}")

        return Message(
            type=MessageTypes.HEARTBEAT_RESPONSE.value,
            data={
                'status': 'alive',
                'model_status': self.model_status,
                'timestamp': time.time()
            },
            timestamp=time.time(),
            message_id=message.message_id,
            device_id=self.device_id
        )

    def _handle_stop(self, message: Message, client: ClientConnection) -> Optional[Message]:
        """Handle stop command synchronously: terminate container, then respond."""
        logger.info(f"Stop command received from {client.address}")

        try:
            if self.vila_processor:
                logger.info(
                    "Immediately terminating VILA container (synchronous stop)...")
                # Ensure deterministic container kill by name and wait for removal
                self.vila_processor.terminate_container_immediately(
                    container_name="sn_vila", wait_timeout=12)

            # Reset status after termination
            self.model_status = "not_loaded"

            # Ensure any streaming flags on clients are cleared
            if self.vila_processor:
                with self.vila_processor.streaming_lock:
                    for _, connected_client in list(self.clients.items()):
                        connected_client.streaming = False

            # Only after successful termination, send the response
            stop_response = Message(
                type=MessageTypes.STOP_RESPONSE.value,
                data={
                    'status': 'stopped',
                    'message': 'Model and container terminated. Ready for new queries.'
                },
                timestamp=time.time(),
                message_id=message.message_id,
                device_id=self.device_id
            )

            return stop_response

        except Exception as e:
            logger.error(
                f"Error handling synchronous stop: {e}", exc_info=True)
            return self._create_error_message(f"Error during stop: {e}", message.message_id)

    def _stop_model_background(self):
        """Stop VILA model in background thread to avoid blocking client handler"""
        try:
            if self.vila_processor:
                logger.info("Stopping VILA model...")
                self.vila_processor.stop_model()

            # Reset model status
            self.model_status = "not_loaded"

            # Stop all streaming for all clients
            if self.vila_processor:
                with self.vila_processor.streaming_lock:
                    for client_id, connected_client in list(self.clients.items()):
                        if connected_client.streaming:
                            logger.info(
                                f"Stopping streaming for client {connected_client.client_id}")
                            connected_client.streaming = False
                            self.vila_processor.stop_streaming(
                                connected_client)

            # Clear query queue
            if self.query_handler:
                logger.info("Clearing query queue...")
                self.query_handler.clear_queue()

            logger.info(
                "Stop command completed - container killed, server ready for new queries")
        except Exception as e:
            logger.error(f"Error in background stop_model: {e}", exc_info=True)

    def _handle_disconnect(self, message: Message, client: ClientConnection) -> Optional[Message]:
        """Handle disconnect command from client - closes containers and stops server"""
        logger.info(f"Disconnect command received from {client.address}")

        try:
            # Send disconnect response immediately before shutdown
            disconnect_response = Message(
                type=MessageTypes.DISCONNECT_RESPONSE.value,
                data={
                    'status': 'disconnecting',
                    'message': 'Server shutting down. Containers will be closed.'
                },
                timestamp=time.time(),
                message_id=message.message_id,
                device_id=self.device_id
            )

            # Send the response
            self._send_message(disconnect_response, client)
            logger.info(
                f"Disconnect response sent to {client.address} - Initiating server shutdown")

            # Perform graceful shutdown (this will close containers and stop server)
            # Use a separate thread to allow response to be sent first
            shutdown_thread = threading.Thread(
                target=self._graceful_shutdown, daemon=False)
            shutdown_thread.start()

            return None  # No additional response needed

        except Exception as e:
            logger.error(f"Error handling disconnect command: {e}")
            # Still proceed with shutdown even if response sending fails
            shutdown_thread = threading.Thread(
                target=self._graceful_shutdown, daemon=False)
            shutdown_thread.start()
            return None

    def _handle_exit(self, message: Message, client: ClientConnection) -> Optional[Message]:
        """Handle exit command from host - triggers server shutdown"""
        logger.info(
            f"Exit command received from {client.address} (reason: {message.data.get('reason', 'unknown')})")

        try:
            # Send exit response immediately before shutdown
            exit_response = Message(
                type=MessageTypes.EXIT_RESPONSE.value,
                data={
                    'status': 'shutting_down',
                    'message': 'Server shutting down due to host exit.'
                },
                timestamp=time.time(),
                message_id=message.message_id,
                device_id=self.device_id
            )

            # Send the response
            self._send_message(exit_response, client)
            logger.info(
                f"Exit response sent to {client.address} - Initiating server shutdown")

            # Perform graceful shutdown (this will close containers and stop server)
            # Use a separate thread to allow response to be sent first
            shutdown_thread = threading.Thread(
                target=self._graceful_shutdown, daemon=False)
            shutdown_thread.start()

            return None  # No additional response needed

        except Exception as e:
            logger.error(f"Error handling exit command: {e}")
            # Still proceed with shutdown even if response sending fails
            shutdown_thread = threading.Thread(
                target=self._graceful_shutdown, daemon=False)
            shutdown_thread.start()
            return None

    def _graceful_shutdown(self):
        """Perform graceful shutdown of the server"""
        try:
            logger.info("Initiating graceful server shutdown...")

            # Stop VILA processor if running
            if self.vila_processor:
                logger.info("Stopping VILA processor...")
                self.vila_processor.stop()

            # Stop query processing
            if self.query_handler:
                logger.info("Stopping query processing...")
                self.query_handler.stop_processing()
                self.query_handler.clear_queue()

            # Cleanup data triage controller
            if self.triage_controller:
                logger.info("Cleaning up data triage controller...")
                self.triage_controller.cleanup()

            # Set running flag to false to stop accepting new connections
            self.running = False

            # Disconnect all clients
            for client in list(self.clients.values()):
                self._disconnect_client(client)

            # Close server socket
            if self.server_socket:
                self.server_socket.close()

            # Clean up containers
            self._cleanup_containers()

            logger.info("Graceful shutdown completed")

            # Exit the process
            import os
            os._exit(0)

        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}")
            import os
            os._exit(1)

    def _send_live_feed_started(self, query: str, client: ClientConnection):
        """Send live feed started message"""
        try:
            live_feed_data = {
                'query_text': query,
                'frame_interval': 3,
                'buffer_size': 5,
                'model_ready': True,
                'model_loading': False,
                'processing_settings': {
                    'frame_skip': 2,
                    'analysis_frequency': 'every_3rd_frame',
                    'person_detection_enabled': True,
                    'confidence_threshold': 0.5
                },
                'system_status': {
                    'gpu_usage': 45.2,
                    'memory_usage': 3.8,
                    'cpu_usage': 23.1,
                    'temperature': 65.4
                }
            }

            message = Message(
                type=MessageTypes.LIVE_FEED_STARTED.value,
                data=live_feed_data,
                timestamp=time.time(),
                message_id=f"live_feed_{int(time.time())}",
                device_id=self.device_id
            )

            self._send_message(message, client)
            logger.info(f"Live feed started message sent to {client.address}")

        except Exception as e:
            logger.error(f"Error sending live feed started message: {e}")

    def _send_image_data(self, image_data: bytes, client: ClientConnection, width: int = 1280, height: int = 720):
        """Send image data to client"""
        try:
            # Encode image as base64
            image_b64 = base64.b64encode(image_data).decode('utf-8')

            message = Message(
                type=MessageTypes.IMAGE_DATA.value,
                data={
                    'image_id': f"frame_{int(time.time())}",
                    'image_data': image_b64,
                    'timestamp': time.time(),
                    'width': width,
                    'height': height,
                    'format': 'JPEG',
                    'compression': 'base64',
                    'query_id': f"query_{int(time.time())}",
                    'frame_number': 1,
                    'analysis_result': {
                        'analysis': 'VILA analysis result',
                        'confidence': 0.8,
                        'processing_time': 1.2
                    },
                    'metadata': {
                        'camera_settings': {
                            'brightness': 0.5,
                            'contrast': 0.7,
                            'saturation': 0.8
                        },
                        'detection_info': {
                            'person_detected': True,
                            'detection_confidence': 0.92,
                            'bounding_box': [120, 80, 200, 300]
                        }
                    }
                },
                timestamp=time.time(),
                message_id=f"img_{int(time.time())}",
                device_id=self.device_id
            )

            self._send_message(message, client)

        except Exception as e:
            logger.error(f"Error sending image data: {e}")

    def _create_error_message(self, error_msg: str, message_id: str) -> Message:
        """Create error response message"""
        return Message(
            type=MessageTypes.ERROR.value,
            data={
                'error': error_msg,
                'timestamp': time.time()
            },
            timestamp=time.time(),
            message_id=message_id,
            device_id=self.device_id
        )

    def _create_live_feed_error_message(self, error_msg: str, message_id: str) -> Message:
        """Create live feed error message"""
        return Message(
            type=MessageTypes.LIVE_FEED_ERROR.value,
            data={
                'error_type': 'processing_error',
                'error_message': error_msg,
                'frame_number': 1,
                'error_code': 'PROCESSING_ERROR',
                'error_details': {
                    'error_description': error_msg,
                    'suggestion': 'Check system resources and try again'
                },
                'recovery_attempted': False,
                'recovery_successful': False,
                'timestamp': time.time()
            },
            timestamp=time.time(),
            message_id=message_id,
            device_id=self.device_id
        )

    def _heartbeat_monitor(self):
        """Monitor client heartbeats and disconnect inactive clients"""
        while self.running:
            try:
                current_time = time.time()
                inactive_clients = []

                for client_id, client in self.clients.items():
                    if current_time - client.last_heartbeat > 120:  # 2 minute timeout for model loading
                        inactive_clients.append(client_id)

                for client_id in inactive_clients:
                    logger.warning(
                        f"Client {client_id} timed out, disconnecting")
                    self._disconnect_client(self.clients[client_id])

                time.sleep(5)  # Check every 5 seconds

            except Exception as e:
                logger.error(f"Error in heartbeat monitor: {e}")
                time.sleep(5)

    def _disconnect_client(self, client: ClientConnection):
        """Disconnect a client"""
        try:
            # Mark as disconnected first to prevent race conditions
            client.connected = False

            # Stop streaming if client was streaming
            if client.streaming and self.vila_processor:
                try:
                    self.vila_processor.stop_streaming(client)
                except Exception as e:
                    logger.warning(
                        f"Error stopping streaming for client {client.client_id}: {e}")

            # Close socket if it exists and is still open
            if client.socket:
                try:
                    client.socket.close()
                except Exception as e:
                    logger.debug(
                        f"Socket already closed or error closing: {e}")

            # Remove from clients dictionary
            if client.client_id in self.clients:
                del self.clients[client.client_id]

            logger.info(f"Client {client.client_id} disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting client {e}")
            # Try to remove from dictionary anyway
            try:
                if hasattr(client, 'client_id') and client.client_id in self.clients:
                    del self.clients[client.client_id]
            except:
                pass

    def stop_server(self):
        """Stop the server"""
        logger.info("Stopping Edge Network Server...")
        self.running = False

        # Stop VILA processor if running
        if self.vila_processor:
            try:
                logger.info("Stopping VILA processor...")
                self.vila_processor.stop()
            except Exception as e:
                logger.error(f"Error stopping VILA processor: {e}")

        # Disconnect all clients
        for client in list(self.clients.values()):
            self._disconnect_client(client)

        if self.server_socket:
            self.server_socket.close()

        # Clean up containers on shutdown
        self._cleanup_containers()

        logger.info("Edge Network Server stopped")


def main():
    """Main server entry point"""
    logger.info("Starting Sentinel Nexus V2 Edge Server")

    server = EdgeNetworkServer(host="0.0.0.0", port=8080, max_clients=5)

    try:
        server.start_server()
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
    finally:
        server.stop_server()


if __name__ == "__main__":
    main()
