"""
Device Discovery Module for Sentinel Nexus V2

This module handles the discovery of edge devices on the local network
using multiple discovery methods for robust connectivity.
"""

import asyncio
import socket
import threading
import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import ipaddress
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class EdgeDevice:
    """Represents a discovered edge device."""
    ip_address: str
    port: int
    device_id: str
    device_name: str
    status: str  # 'online', 'offline', 'connecting'
    last_seen: float
    capabilities: Dict[str, Any]
    model_status: str = "unknown"  # 'not_loaded', 'loading', 'ready', 'error'
    model_ready: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert device to dictionary for serialization."""
        return {
            'ip_address': self.ip_address,
            'port': self.port,
            'device_id': self.device_id,
            'device_name': self.device_name,
            'status': self.status,
            'last_seen': self.last_seen,
            'capabilities': self.capabilities,
            'model_status': self.model_status,
            'model_ready': self.model_ready
        }


class DeviceDiscovery:
    """Handles discovery of edge devices on the local network."""
    
    def __init__(self, discovery_port: int = 8080, timeout: float = 2.0):
        """
        Initialize device discovery.
        
        Args:
            discovery_port: Port to scan for edge devices
            timeout: Connection timeout in seconds
        """
        self.discovery_port = discovery_port
        self.timeout = timeout
        self.discovered_devices: Dict[str, EdgeDevice] = {}
        self.discovery_active = False
        self.discovery_thread: Optional[threading.Thread] = None
        
    def get_device_ip_list(self) -> List[str]:
        """Get the specific list of IP addresses to scan for edge devices."""
        # Define the 5 specific IP addresses to scan
        device_ips = [
            "10.148.0.52",     # Edge device IP
            # "10.148.0.113",    # Host IP (optional for testing)
            # "192.168.4.101",    # Second edge device
            # "192.168.4.102",    # Third edge device
            # "192.168.4.103"     # Fourth edge device
        ]
        
        print(f"=== Scanning specific device IPs: {device_ips} ===")
        return device_ips
    
    def scan_network_range(self, network_range: str) -> List[str]:
        """Scan network range for potential edge devices."""
        potential_devices = []
        network = ipaddress.IPv4Network(network_range)
        
        logger.info(f"Scanning network range: {network_range}")
        print(f"=== Scanning network range: {network_range} ===")
        
        for ip in network.hosts():
            ip_str = str(ip)
            print(f"=== Checking IP: {ip_str} ===")
            if self._is_edge_device(ip_str):
                print(f"=== Found potential device at: {ip_str} ===")
                potential_devices.append(ip_str)
                logger.info(f"Found potential edge device at {ip_str}")
        
        print(f"=== Found {len(potential_devices)} potential devices: {potential_devices} ===")
        return potential_devices
    
    def _is_edge_device(self, ip_address: str) -> bool:
        """Check if an IP address hosts an edge device."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                result = sock.connect_ex((ip_address, self.discovery_port))
                return result == 0
        except Exception:
            return False
    
    def _discover_device_info(self, ip_address: str) -> Optional[EdgeDevice]:
        """Attempt to discover device information via TCP connection.

        Tries small JSON first (no length prefix) to match edge server behavior,
        then falls back to length-prefixed protocol.
        """
        try:
            print(f"=== Attempting to connect to {ip_address}:{self.discovery_port} ===")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5.0)  # 5 second timeout
                print(f"=== Connecting to {ip_address} ===")
                sock.connect((ip_address, self.discovery_port))
                print(f"=== Connected to {ip_address} ===")
                
                # Build small JSON discovery request (no length prefix)
                discovery_request_small = {
                    "type": "discovery_request",
                    "data": {},
                    "timestamp": time.time()
                }
                print(f"=== Sending discovery request (small JSON) to {ip_address} ===")
                sock.send(json.dumps(discovery_request_small).encode('utf-8'))

                # Try to read small response first
                print(f"=== Waiting for response from {ip_address} ===")
                sock.settimeout(2.0)
                data = sock.recv(4096)
                if not data:
                    print(f"=== No response received from {ip_address} (small read) ===")
                    return None

                try:
                    response_str = data.decode('utf-8')
                    response = json.loads(response_str)
                except Exception:
                    # Fall back to length-prefixed protocol if small JSON fails
                    print(f"=== Falling back to length-prefixed response from {ip_address} ===")
                    # First 4 bytes should be length
                    if len(data) >= 4:
                        message_length = int.from_bytes(data[:4], 'big')
                        message_data = data[4:]
                        while len(message_data) < message_length:
                            chunk = sock.recv(min(4096, message_length - len(message_data)))
                            if not chunk:
                                print(f"=== Connection lost while receiving response from {ip_address} ===")
                                return None
                            message_data += chunk
                        response_str = message_data.decode('utf-8')
                        response = json.loads(response_str)
                    else:
                        print(f"=== Invalid response header from {ip_address} ===")
                        return None

                # Validate discovery response
                resp_type = response.get("type") or response.get("message_type")
                if resp_type == "discovery_response":
                    device_data = response.get("data", {})
                    print(f"=== Device data: {device_data} ===")
                    device = EdgeDevice(
                        ip_address=ip_address,
                        port=self.discovery_port,
                        device_id=device_data.get("device_id", f"device_{ip_address}"),
                        device_name=device_data.get("device_name", f"Edge Device {ip_address}"),
                        status="online",
                        last_seen=time.time(),
                        capabilities=device_data.get("capabilities", {})
                    )
                    
                    # Store model status information if available
                    device.model_status = device_data.get("model_status", "unknown")
                    device.model_ready = device_data.get("model_ready", False)
                    print(f"=== Successfully discovered: {device.device_name} ===")
                    return device
                else:
                    print(f"=== Unexpected response type: {resp_type} ===")
                    
        except socket.timeout:
            print(f"=== Connection timeout to {ip_address} ===")
        except ConnectionRefusedError:
            print(f"=== Connection refused by {ip_address} ===")
        except Exception as e:
            print(f"=== Failed to discover device at {ip_address}: {e} ===")
            logger.debug(f"Failed to discover device at {ip_address}: {e}")
        
        return None
    
    def discover_devices(self) -> List[EdgeDevice]:
        """Discover all available edge devices on the network."""
        discovered = []
        # Use specific IP list instead of scanning full network range
        potential_devices = self.get_device_ip_list()
        
        logger.info(f"Scanning {len(potential_devices)} specific device IPs")
        print(f"Potential devices: {potential_devices}")
        
        for ip_address in potential_devices:
            print(f"Attempting to discover device at {ip_address}")
            device = self._discover_device_info(ip_address)
            if device:
                discovered.append(device)
                self.discovered_devices[device.device_id] = device
                logger.info(f"Discovered device: {device.device_name} at {device.ip_address}")
                print(f"Successfully discovered: {device.device_name}")
            else:
                print(f"Failed to discover device at {ip_address}")
        
        return discovered
    
    def start_continuous_discovery(self, interval: float = 30.0):
        """Start continuous device discovery in background thread."""
        if self.discovery_active:
            logger.warning("Discovery already active")
            return
        
        self.discovery_active = True
        self.discovery_thread = threading.Thread(
            target=self._continuous_discovery_loop,
            args=(interval,),
            daemon=True
        )
        self.discovery_thread.start()
        logger.info(f"Started continuous discovery with {interval}s interval")
    
    def stop_continuous_discovery(self):
        """Stop continuous device discovery."""
        self.discovery_active = False
        if self.discovery_thread:
            self.discovery_thread.join(timeout=5.0)
        logger.info("Stopped continuous discovery")
    
    def _continuous_discovery_loop(self, interval: float):
        """Background loop for continuous device discovery."""
        while self.discovery_active:
            try:
                self.discover_devices()
                time.sleep(interval)
            except Exception as e:
                logger.error(f"Error in continuous discovery: {e}")
                time.sleep(interval)
    
    def get_discovered_devices(self) -> List[EdgeDevice]:
        """Get list of currently discovered devices."""
        return list(self.discovered_devices.values())
    
    def get_device_by_id(self, device_id: str) -> Optional[EdgeDevice]:
        """Get specific device by ID."""
        return self.discovered_devices.get(device_id)
    
    def remove_device(self, device_id: str):
        """Remove device from discovered list."""
        if device_id in self.discovered_devices:
            del self.discovered_devices[device_id]
            logger.info(f"Removed device: {device_id}")


class NetworkScanner:
    """Network scanning utilities for device discovery."""
    
    @staticmethod
    def scan_port_range(ip_address: str, start_port: int = 8000, end_port: int = 9000) -> List[int]:
        """Scan a range of ports on a specific IP address."""
        open_ports = []
        
        for port in range(start_port, end_port + 1):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1.0)
                    result = sock.connect_ex((ip_address, port))
                    if result == 0:
                        open_ports.append(port)
            except Exception:
                continue
        
        return open_ports
    
    @staticmethod
    def get_local_ip() -> str:
        """Get the local machine's IP address."""
        try:
            # Connect to a remote address to determine local IP
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
        except Exception:
            return "127.0.0.1"


# Example usage and testing
if __name__ == "__main__":
    # Create discovery instance
    discovery = DeviceDiscovery(discovery_port=8080, timeout=2.0)
    
    print("Starting device discovery...")
    devices = discovery.discover_devices()
    
    print(f"\nDiscovered {len(devices)} devices:")
    for device in devices:
        print(f"  - {device.device_name} ({device.device_id}) at {device.ip_address}:{device.port}")
        print(f"    Status: {device.status}, Capabilities: {device.capabilities}")
    
    # Start continuous discovery
    discovery.start_continuous_discovery(interval=30.0)
    
    try:
        # Keep running to show continuous discovery
        while True:
            time.sleep(10)
            current_devices = discovery.get_discovered_devices()
            print(f"Currently tracking {len(current_devices)} devices")
    except KeyboardInterrupt:
        print("\nStopping discovery...")
        discovery.stop_continuous_discovery()
