"""
Network Client Module for Sentinel Nexus V2

This module handles TCP communication between the host computer and edge devices.
Provides reliable connection management and message passing.
"""

import json
import socket
import threading
import time
import logging
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConnectionStatus(Enum):
    """Connection status enumeration."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class NetworkMessage:
    """Represents a network message."""
    message_type: str
    data: Dict[str, Any]
    timestamp: float
    message_id: Optional[str] = None
    device_id: Optional[str] = None  # Added for edge device compatibility
    
    def to_json(self, use_type_field: bool = False) -> str:
        """Convert message to JSON string.
        
        Args:
            use_type_field: If True, use 'type' field (for edge device spec compliance)
                           If False, use 'message_type' field (for compatibility)
        """
        message_dict = {
            'data': self.data,
            'timestamp': self.timestamp,
            'message_id': self.message_id,
            'device_id': self.device_id
        }
        
        # Use 'type' for edge device spec compliance, 'message_type' for compatibility
        if use_type_field:
            message_dict['type'] = self.message_type
        else:
            message_dict['message_type'] = self.message_type
        
        return json.dumps(message_dict)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'NetworkMessage':
        """Create message from JSON string."""
        data = json.loads(json_str)
        return cls(
            message_type=data.get('message_type', data.get('type', 'unknown')),
            data=data.get('data', {}),
            timestamp=data.get('timestamp', time.time()),
            message_id=data.get('message_id'),
            device_id=data.get('device_id')
        )


class NetworkClient:
    """TCP client for communicating with edge devices."""
    
    def __init__(self, host: str, port: int, timeout: float = 5.0):
        """
        Initialize network client.
        
        Args:
            host: Edge device IP address
            port: Edge device port
            timeout: Connection timeout in seconds
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.socket: Optional[socket.socket] = None
        self.status = ConnectionStatus.DISCONNECTED
        self.message_handlers: Dict[str, Callable] = {}
        self.heartbeat_interval = 30.0
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.response_thread: Optional[threading.Thread] = None
        self.running = False
        
    def connect(self) -> bool:
        """Establish connection to edge device."""
        try:
            self.status = ConnectionStatus.CONNECTING
            logger.info(f"Connecting to {self.host}:{self.port}")
            
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.timeout)  # Only for initial connection
            self.socket.connect((self.host, self.port))
            
            # Remove timeout after connection to keep connection alive
            self.socket.settimeout(None)
            
            self.status = ConnectionStatus.CONNECTED
            self.running = True
            
            # Start heartbeat thread
            self.heartbeat_thread = threading.Thread(
                target=self._heartbeat_loop,
                daemon=True
            )
            self.heartbeat_thread.start()
            
            # Start response listening thread
            self.response_thread = threading.Thread(
                target=self._response_loop,
                daemon=True
            )
            self.response_thread.start()
            
            logger.info(f"Connected to {self.host}:{self.port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to {self.host}:{self.port}: {e}")
            self.status = ConnectionStatus.ERROR
            self._cleanup()
            return False
    
    def send_disconnect(self) -> bool:
        """Send disconnect message to edge device before closing connection."""
        if self.status != ConnectionStatus.CONNECTED or not self.socket:
            logger.debug("Not connected, skipping disconnect message")
            return False
        
        try:
            message = NetworkMessage(
                message_type="disconnect",
                data={"reason": "user_disconnect"},
                timestamp=time.time()
            )
            # Send message without checking running status (we're disconnecting)
            message_data = message.to_json(use_type_field=True).encode('utf-8')
            message_length = len(message_data)
            
            if message_length <= 1024:
                self.socket.send(message_data)
                logger.debug(f"Sent disconnect message ({message_length} bytes)")
            else:
                self.socket.send(message_length.to_bytes(4, 'big'))
                self.socket.send(message_data)
                logger.debug(f"Sent large disconnect message ({message_length} bytes)")
            
            return True
        except Exception as e:
            logger.warning(f"Failed to send disconnect message (socket may already be closed): {e}")
            return False
    
    def send_exit(self) -> bool:
        """Send exit message to edge device before closing connection."""
        if self.status != ConnectionStatus.CONNECTED or not self.socket:
            logger.debug("Not connected, skipping exit message")
            return False
        
        try:
            message = NetworkMessage(
                message_type="exit",
                data={"reason": "application_exit"},
                timestamp=time.time()
            )
            # Send message without checking running status (we're exiting)
            message_data = message.to_json(use_type_field=True).encode('utf-8')
            message_length = len(message_data)
            
            if message_length <= 1024:
                self.socket.send(message_data)
                logger.info(f"Sent exit message ({message_length} bytes)")
            else:
                self.socket.send(message_length.to_bytes(4, 'big'))
                self.socket.send(message_data)
                logger.info(f"Sent large exit message ({message_length} bytes)")
            
            return True
        except Exception as e:
            logger.warning(f"Failed to send exit message (socket may already be closed): {e}")
            return False
    
    def disconnect(self):
        """Disconnect from edge device."""
        logger.info(f"Disconnecting from {self.host}:{self.port}")
        
        # Send disconnect message to edge device before closing
        if self.status == ConnectionStatus.CONNECTED:
            self.send_disconnect()
            # Give a small moment for the message to be sent
            time.sleep(0.1)
        
        self.running = False
        self.status = ConnectionStatus.DISCONNECTED
        self._cleanup()
    
    def _cleanup(self):
        """Clean up socket and threads."""
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None
        
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=2.0)
        
        if self.response_thread and self.response_thread.is_alive():
            self.response_thread.join(timeout=2.0)
    
    def send_message(self, message: NetworkMessage) -> bool:
        """Send message to edge device with smart protocol selection."""
        if self.status != ConnectionStatus.CONNECTED or not self.socket:
            logger.error("Not connected to edge device")
            return False
        
        try:
            # Use 'type' field for edge device specification compliance
            message_data = message.to_json(use_type_field=True).encode('utf-8')
            message_length = len(message_data)
            
            # Use small JSON for small messages, length-prefixed for large messages
            if message_length <= 1024:  # Small message threshold
                # Send small JSON directly (no length prefix)
                self.socket.send(message_data)
                logger.debug(f"Sent small message: {message.message_type} ({message_length} bytes)")
            else:
                # Send length first (4 bytes, big-endian) for large messages
                self.socket.send(message_length.to_bytes(4, 'big'))
                # Send message data
                self.socket.send(message_data)
                logger.debug(f"Sent large message: {message.message_type} ({message_length} bytes)")
            
            return True
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            self.status = ConnectionStatus.ERROR
            return False
    
    def send_query(self, query_text: str) -> bool:
        """Send a query to the edge device."""
        message = NetworkMessage(
            message_type="query",
            data={"query": query_text},
            timestamp=time.time()
        )
        return self.send_message(message)
    
    def send_heartbeat(self) -> bool:
        """Send heartbeat message to maintain connection."""
        message = NetworkMessage(
            message_type="heartbeat",
            data={"status": "alive"},
            timestamp=time.time()
        )
        return self.send_message(message)
    
    def _heartbeat_loop(self):
        """Background heartbeat loop."""
        while self.running and self.status == ConnectionStatus.CONNECTED:
            try:
                success = self.send_heartbeat()
                if not success:
                    logger.warning("Heartbeat failed - connection may be lost")
                    self.status = ConnectionStatus.ERROR
                    break
                time.sleep(self.heartbeat_interval)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                self.status = ConnectionStatus.ERROR
                break
    
    def _response_loop(self):
        """Background response listening loop with improved protocol detection."""
        buffer = b''
        
        while self.running and self.status == ConnectionStatus.CONNECTED:
            try:
                if not self.socket:
                    break
                
                # Set a timeout for receiving data
                self.socket.settimeout(1.0)
                
                # Receive data and add to buffer - use larger buffer for large messages
                data = self.socket.recv(65536)  # Increased from 4096 to handle large live_feed_result messages
                if not data:
                    logger.warning("No data received - connection may be lost")
                    self.status = ConnectionStatus.ERROR
                    break
                
                logger.info(f"📥 RAW DATA RECEIVED: {len(data)} bytes")
                logger.debug(f"   First 200 bytes (hex): {data[:200].hex()}")
                logger.debug(f"   First 200 bytes (repr): {repr(data[:200])}")
                
                buffer += data
                logger.debug(f"   Buffer size after append: {len(buffer)} bytes")
                
                # Process complete messages from buffer
                messages_processed_this_loop = 0
                while buffer:
                    logger.info(f"🔄 Processing buffer: {len(buffer)} bytes remaining")
                    original_buffer_size = len(buffer)
                    message_found = False
                    
                    # FIRST: Try length-prefixed protocol (check before JSON parsing)
                    if len(buffer) >= 4:
                        try:
                            # Check if first 4 bytes look like a length prefix
                            potential_length = int.from_bytes(buffer[:4], 'big')
                            if 100 <= potential_length <= 10000000:  # Reasonable message size range
                                total_length = 4 + potential_length
                                
                                if len(buffer) >= total_length:
                                    # We have the complete length-prefixed message
                                    message_data = buffer[4:total_length]
                                    try:
                                        message_str = message_data.decode('utf-8')
                                        logger.info(f"🔍 Found length-prefixed message ({potential_length} bytes JSON)")
                                        logger.debug(f"   Full JSON preview: {message_str[:200]}...")
                                        
                                        # Extract message type before parsing for early detection
                                        try:
                                            import json as json_lib
                                            json_obj = json_lib.loads(message_str)
                                            msg_type_from_json = json_obj.get('type', 'unknown')
                                            logger.info(f"   Detected message type from JSON: '{msg_type_from_json}'")
                                            
                                            if msg_type_from_json == "live_feed_result":
                                                logger.info(f"🎯🎯🎯 LIVE_FEED_RESULT detected in length-prefixed message! 🎯🎯🎯")
                                        except:
                                            pass
                                        
                                        try:
                                            message = NetworkMessage.from_json(message_str)
                                            logger.info(f"✅ Received large message: {message.message_type} ({potential_length} bytes)")
                                            logger.info(f"   Parsed message_type: '{message.message_type}'")
                                            logger.info(f"   Message has {len(message.data) if message.data else 0} data fields")
                                            self._handle_incoming_message(message)
                                            message_found = True
                                            messages_processed_this_loop += 1
                                        except Exception as e:
                                            logger.error(f"❌ Error parsing length-prefixed message: {e}")
                                            logger.error(f"   Message string preview: {message_str[:500]}")
                                            import traceback
                                            logger.error(f"   Traceback: {traceback.format_exc()}")
                                        
                                        # Remove processed message from buffer
                                        buffer = buffer[total_length:]
                                        logger.info(f"   Removed {total_length} bytes from buffer, {len(buffer)} bytes remaining")
                                        continue
                                    except UnicodeDecodeError:
                                        # Not valid UTF-8, might not be a length prefix after all
                                        pass
                        except (ValueError, OverflowError):
                            # First 4 bytes are not a valid length prefix
                            pass
                    
                    # SECOND: Try to parse as small JSON message
                    try:
                        # Look for complete JSON message in buffer
                        message_str = buffer.decode('utf-8', errors='replace')
                        logger.debug(f"   Decoded buffer preview: {message_str[:100]}...")
                        
                        # Find first '{' in buffer
                        json_start = message_str.find('{')
                        if json_start >= 0:
                            # Start parsing from first '{'
                            working_str = message_str[json_start:]
                            
                            # Find the end of the JSON message by counting braces
                            brace_count = 0
                            end_pos = -1
                            for i, char in enumerate(working_str):
                                if char == '{':
                                    brace_count += 1
                                elif char == '}':
                                    brace_count -= 1
                                    if brace_count == 0:
                                        end_pos = i + 1
                                        break
                            
                            if end_pos > 0:
                                # Complete JSON message found
                                json_str = working_str[:end_pos].strip()
                                actual_start = json_start
                                actual_end = json_start + end_pos
                                
                                logger.info(f"🔍 Found JSON message in buffer at position {actual_start}-{actual_end} ({len(json_str)} bytes)")
                                logger.debug(f"   Full JSON: {json_str}")
                                
                                # Extract message type before parsing for early detection
                                try:
                                    import json as json_lib
                                    json_obj = json_lib.loads(json_str)
                                    msg_type_from_json = json_obj.get('type', 'unknown')
                                    logger.info(f"   Detected message type from JSON: '{msg_type_from_json}'")
                                    
                                    if msg_type_from_json == "live_feed_result":
                                        logger.info(f"🎯🎯🎯 LIVE_FEED_RESULT detected in raw JSON! 🎯🎯🎯")
                                except Exception as e:
                                    logger.debug(f"   Could not extract message type: {e}")
                                
                                try:
                                    message = NetworkMessage.from_json(json_str)
                                    logger.info(f"✅ Received small message: {message.message_type} ({len(json_str)} bytes)")
                                    logger.info(f"   Parsed message_type: '{message.message_type}'")
                                    logger.info(f"   Message has {len(message.data) if message.data else 0} data fields")
                                    self._handle_incoming_message(message)
                                    message_found = True
                                    messages_processed_this_loop += 1
                                except Exception as e:
                                    logger.error(f"❌ Error parsing JSON message: {e}")
                                    logger.error(f"   JSON string preview: {json_str[:500]}")
                                    import traceback
                                    logger.error(f"   Traceback: {traceback.format_exc()}")
                                
                                # Remove processed message from buffer (by byte length)
                                json_bytes = json_str.encode('utf-8')
                                # Need to account for leading bytes before JSON start
                                buffer = buffer[actual_start + len(json_bytes):]
                                logger.info(f"   Removed message from buffer, {len(buffer)} bytes remaining")
                                continue
                    except (UnicodeDecodeError, ValueError) as e:
                        # Buffer doesn't decode as UTF-8, might be binary or incomplete
                        logger.debug(f"   Buffer decode issue: {type(e).__name__}")
                        pass
                    
                    # If we get here, we couldn't parse a message
                    if not message_found:
                        if len(buffer) == original_buffer_size:
                            # Buffer didn't shrink, nothing was processed
                            logger.warning(f"⚠️ Could not parse any message from buffer ({len(buffer)} bytes)")
                            logger.warning(f"   Buffer hex preview: {buffer[:50].hex()}")
                            logger.warning(f"   Buffer repr preview: {repr(buffer[:50])}")
                            # Skip one byte to prevent infinite loop
                            buffer = buffer[1:]
                        else:
                            # Buffer changed but no message found - this shouldn't happen
                            logger.warning(f"⚠️ Buffer size changed but no message found")
                            break
                
                if messages_processed_this_loop > 0:
                    logger.info(f"✅ Processed {messages_processed_this_loop} message(s) in this loop")
                
            except socket.timeout:
                # Timeout is expected, continue listening
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Response loop error: {e}")
                    self.status = ConnectionStatus.ERROR
                break
    
    def _handle_incoming_message(self, message: NetworkMessage):
        """Handle incoming message from edge device."""
        logger.info(f"📨 Received message: {message.message_type} from {self.host}:{self.port}")
        logger.info(f"   Message Type (raw): '{message.message_type}'")
        logger.info(f"   Data Keys: {list(message.data.keys()) if message.data else 'No data'}")
        logger.info(f"   Message ID: {message.message_id}")
        logger.info(f"   Device ID: {message.device_id}")
        
        # Special logging for live_feed_result messages
        if message.message_type == "live_feed_result":
            logger.info(f"🎯 LIVE_FEED_RESULT MESSAGE RECEIVED!")
            logger.info(f"   This message should trigger UI updates")
            if message.data:
                analysis = message.data.get('analysis', 'N/A')[:100]
                frame_num = message.data.get('frame_number', 'N/A')
                logger.info(f"   Frame: {frame_num}, Analysis preview: {analysis}...")
        
        logger.debug(f"   Full Data: {message.data}")
        
        handler = self.message_handlers.get(message.message_type)
        if handler:
            try:
                logger.info(f"✅ Handler found for '{message.message_type}' - calling handler...")
                handler(message)
                logger.info(f"✅ Handler completed successfully for {message.message_type}")
            except Exception as e:
                logger.error(f"❌ Message handler error for {message.message_type}: {e}")
                import traceback
                logger.error(f"   Traceback: {traceback.format_exc()}")
        else:
            logger.warning(f"⚠️ No handler registered for message type: '{message.message_type}'")
            logger.warning(f"   Available handlers: {list(self.message_handlers.keys())}")
            logger.warning(f"   Message data keys: {list(message.data.keys()) if message.data else 'No data'}")
            if message.message_type == "live_feed_result":
                logger.error(f"🚨 CRITICAL: live_feed_result message received but no handler!")
                logger.error(f"   This means live feed results are being received but not processed!")
                logger.error(f"   Available handlers: {list(self.message_handlers.keys())}")
    
    def register_message_handler(self, message_type: str, handler: Callable):
        """Register handler for specific message types."""
        self.message_handlers[message_type] = handler
        logger.info(f"Registered handler for message type: {message_type}")
    
    def is_connected(self) -> bool:
        """Check if connected to edge device."""
        return self.status == ConnectionStatus.CONNECTED
    
    def get_status(self) -> ConnectionStatus:
        """Get current connection status."""
        return self.status


class EdgeDeviceConnection:
    """Manages connection to a specific edge device."""
    
    def __init__(self, device_id: str, host: str, port: int):
        """
        Initialize edge device connection.
        
        Args:
            device_id: Unique device identifier
            host: Device IP address
            port: Device port
        """
        self.device_id = device_id
        self.client = NetworkClient(host, port)
        self.connected = False
        self.last_activity = time.time()
        
    def connect(self) -> bool:
        """Connect to the edge device."""
        success = self.client.connect()
        self.connected = success
        if success:
            self.last_activity = time.time()
        return success
    
    def disconnect(self):
        """Disconnect from the edge device."""
        self.client.disconnect()
        self.connected = False
    
    def exit(self):
        """Send exit message and disconnect from the edge device."""
        if self.connected and self.client.is_connected():
            self.client.send_exit()
            # Give a small moment for the message to be sent
            time.sleep(0.1)
        
        # Clean up connection without sending disconnect message
        self.client.running = False
        self.client.status = ConnectionStatus.DISCONNECTED
        self.client._cleanup()
        self.connected = False
    
    def send_query(self, query: str) -> bool:
        """Send query to edge device."""
        if not self.connected:
            logger.error(f"Not connected to device {self.device_id}")
            return False
        
        success = self.client.send_query(query)
        if success:
            self.last_activity = time.time()
        return success
    
    def register_response_handler(self, handler: Callable):
        """Register handler for query responses."""
        self.client.register_message_handler("query_response", handler)
        logger.info(f"Registered response handler for device {self.device_id}")
    
    def register_error_handler(self, handler: Callable):
        """Register handler for error messages."""
        self.client.register_message_handler("error", handler)
        logger.info(f"Registered error handler for device {self.device_id}")
    
    def is_connected(self) -> bool:
        """Check if connected to device."""
        return self.connected and self.client.is_connected()
    
    def get_status(self) -> str:
        """Get connection status string."""
        return self.client.get_status().value


class ConnectionManager:
    """Manages multiple edge device connections."""
    
    def __init__(self):
        """Initialize connection manager."""
        self.connections: Dict[str, EdgeDeviceConnection] = {}
        self.connection_callbacks: List[Callable] = []
        
    def add_device(self, device_id: str, host: str, port: int) -> EdgeDeviceConnection:
        """Add a new edge device connection."""
        connection = EdgeDeviceConnection(device_id, host, port)
        self.connections[device_id] = connection
        logger.info(f"Added device {device_id} at {host}:{port}")
        return connection
    
    def connect_device(self, device_id: str) -> bool:
        """Connect to specific device."""
        if device_id not in self.connections:
            logger.error(f"Device {device_id} not found")
            return False
        
        connection = self.connections[device_id]
        success = connection.connect()
        
        if success:
            self._notify_callbacks("device_connected", device_id)
        else:
            self._notify_callbacks("device_connection_failed", device_id)
        
        return success
    
    def disconnect_device(self, device_id: str):
        """Disconnect from specific device."""
        if device_id in self.connections:
            self.connections[device_id].disconnect()
            self._notify_callbacks("device_disconnected", device_id)
    
    def disconnect_all(self):
        """Disconnect from all devices."""
        for device_id in list(self.connections.keys()):
            self.disconnect_device(device_id)
    
    def exit_all(self):
        """Send exit message and disconnect from all devices."""
        for device_id in list(self.connections.keys()):
            if device_id in self.connections:
                self.connections[device_id].exit()
                self._notify_callbacks("device_disconnected", device_id)
    
    def send_query_to_device(self, device_id: str, query: str) -> bool:
        """Send query to specific device."""
        if device_id not in self.connections:
            logger.error(f"Device {device_id} not found")
            return False
        
        return self.connections[device_id].send_query(query)
    
    def register_response_handler(self, device_id: str, handler: Callable):
        """Register response handler for specific device."""
        if device_id in self.connections:
            self.connections[device_id].register_response_handler(handler)
        else:
            logger.error(f"Device {device_id} not found")
    
    def register_error_handler(self, device_id: str, handler: Callable):
        """Register error handler for specific device."""
        if device_id in self.connections:
            self.connections[device_id].register_error_handler(handler)
        else:
            logger.error(f"Device {device_id} not found")
    
    def register_message_handler(self, device_id: str, message_type: str, handler: Callable):
        """Register message handler for specific device and message type."""
        if device_id in self.connections:
            self.connections[device_id].client.register_message_handler(message_type, handler)
        else:
            logger.error(f"Device {device_id} not found")
    
    def get_connected_devices(self) -> List[str]:
        """Get list of connected device IDs."""
        return [
            device_id for device_id, connection in self.connections.items()
            if connection.is_connected()
        ]
    
    def get_device_status(self, device_id: str) -> Optional[str]:
        """Get status of specific device."""
        if device_id in self.connections:
            return self.connections[device_id].get_status()
        return None
    
    def register_callback(self, callback: Callable):
        """Register callback for connection events."""
        self.connection_callbacks.append(callback)
    
    def _notify_callbacks(self, event: str, device_id: str):
        """Notify registered callbacks of events."""
        for callback in self.connection_callbacks:
            try:
                callback(event, device_id)
            except Exception as e:
                logger.error(f"Callback error: {e}")


# Example usage and testing
if __name__ == "__main__":
    # Create connection manager
    manager = ConnectionManager()
    
    # Add a test device
    device_id = "test_device_001"
    host = "10.148.0.65"  # Edge device IP
    port = 8080
    
    connection = manager.add_device(device_id, host, port)
    
    # Register callback for connection events
    def connection_callback(event: str, device_id: str):
        print(f"Connection event: {event} for device {device_id}")
    
    manager.register_callback(connection_callback)
    
    # Attempt to connect
    print(f"Connecting to device {device_id} at {host}:{port}")
    success = manager.connect_device(device_id)
    
    if success:
        print("Connected successfully!")
        
        # Send a test query
        query = "What objects do you see in the video?"
        print(f"Sending query: {query}")
        manager.send_query_to_device(device_id, query)
        
        # Keep connection alive for a bit
        time.sleep(5)
        
        # Disconnect
        manager.disconnect_device(device_id)
        print("Disconnected")
    else:
        print("Failed to connect")
