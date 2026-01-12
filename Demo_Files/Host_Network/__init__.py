"""
Network Module for Sentinel Nexus V2

This module provides network communication functionality between the host computer
and edge devices, including device discovery and TCP client connections.
"""

from .device_discovery import DeviceDiscovery, EdgeDevice, NetworkScanner
from .network_client import NetworkClient, EdgeDeviceConnection, ConnectionManager, NetworkMessage, ConnectionStatus

__all__ = [
    'DeviceDiscovery',
    'EdgeDevice', 
    'NetworkScanner',
    'NetworkClient',
    'EdgeDeviceConnection',
    'ConnectionManager',
    'NetworkMessage',
    'ConnectionStatus'
]
