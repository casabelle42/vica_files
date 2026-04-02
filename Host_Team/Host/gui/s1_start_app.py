#!/usr/bin/env python3
"""
Host Main Entrypoint
-------------------
Runs the PyQt GUI and wires GUI button clicks (Discover / Send Query) to MQTT
commands using the existing HostCommandSender class.

This keeps code separated:
- GUI stays in Host/gui/*
- GUI logic mapping stays in Host/gui/gui_handler.py 
- MQTT request/response stays in host_client.py
- This file ONLY wires them together and runs the app.
"""

import os
import sys
import json
import socket
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QObject, pyqtSignal


# ---- Ensure project root is importable ----
current_dir = os.path.dirname(os.path.abspath(__file__))
host_dir = os.path.dirname(current_dir)  # Host/
host_team_dir = os.path.dirname(host_dir)  # Host_Team/
project_root = os.path.dirname(host_team_dir)  # project root

for path in [current_dir, host_dir, host_team_dir, project_root]:
    if path not in sys.path:
        sys.path.insert(0, path)

from s3_availableDevices import MainWindow as AvailableDevicesWindow
from gui_handler import GUIHandler
from host_client import HostCommandSender

def _safe_extract_devices(response: dict) -> list:
    if not isinstance(response, dict):
        return []

    if isinstance(response.get("devices"), list):
        return response["devices"]

    if isinstance(response.get("available_devices"), list):
        return response["available_devices"]

    body = response.get("body")
    if isinstance(body, dict) and isinstance(body.get("available_devices"), list):
        return body["available_devices"]

    return []

def _to_gui_devices(raw_devices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert raw discovery device dicts into the schema expected by availibleDevices.py
    Expected keys: name, location, status, connection, metadata
    """
    gui_devices: List[Dict[str, Any]] = []

    for d in raw_devices or []:
        name = d.get("device_name") or d.get("device_id") or "Unknown"
        ip = d.get("ip", "")
        raw_status = (d.get("status") or "").lower().strip()

        if raw_status == "online":
            status = "Online"
        elif raw_status == "offline":
            status = "Offline"
        else:
            status = "Unknown"

        gui_devices.append({
            "name": name,
            "location": f"IP: {ip}" if ip else "IP: unknown",
            "status": status,
            "connection": "Strong",      # placeholder for now
            "metadata": "v1 • Active"    # placeholder for now
        })

    return gui_devices

class UiDispatcher(QObject):
    update_devices_signal = pyqtSignal(list)

    def __init__(self, window):
        super().__init__()
        self._window = window
        self.update_devices_signal.connect(self._window.update_devices)

def main():
    # ---- CONFIG ----
    MQTT_BROKER_IP = os.environ.get("VICA_MQTT_BROKER", "10.148.0.95")
    MQTT_PORT = int(os.environ.get("VICA_MQTT_PORT", "1883"))
    CONTROL_TOPIC = os.environ.get("VICA_CONTROL_TOPIC", "edge/control")

    # A host-specific reply topic prevents cross-talk if multiple hosts exist
    host_id = os.environ.get("VICA_HOST_ID", socket.gethostname().replace(" ", "_"))
    DISCOVERY_REPLY_TOPIC = os.environ.get("VICA_DISCOVERY_REPLY_TOPIC", f"host/{host_id}/discovery_response")
    QUERY_REPLY_TOPIC = os.environ.get("VICA_QUERY_REPLY_TOPIC", f"host/{host_id}/query_response")

    print("=" * 70)
    print("VICA Host Main")
    print(f"Broker: {MQTT_BROKER_IP}:{MQTT_PORT}")
    print(f"Control topic: {CONTROL_TOPIC}")
    print(f"Discovery reply topic: {DISCOVERY_REPLY_TOPIC}")
    print(f"Query reply topic: {QUERY_REPLY_TOPIC}")
    print("=" * 70)

    # ---- Qt App + Windows ----
    app = QApplication(sys.argv)
    devices_window = AvailableDevicesWindow()
    devices_window.show()

    ui = UiDispatcher(devices_window)


    # ---- MQTT sender (existing class) ----
    sender = HostCommandSender(
        mqtt_broker=MQTT_BROKER_IP,
        mqtt_port=MQTT_PORT,
        control_topic=CONTROL_TOPIC,
        default_reply_topic=QUERY_REPLY_TOPIC,
        request_timeout_sec=10.0,
    )

    # ---- Live device updates from device_status (no discovery required) ----
    devices_by_name: Dict[str, Dict[str, Any]] = {}
    devices_lock = threading.Lock()

    def _status_to_gui_device(body: Dict[str, Any]) -> Dict[str, Any]:
        name = body.get("name") or "Unknown"
        strength = body.get("network_strength")
        if isinstance(strength, (int, float)):
            if strength >= -60:
                connection = "Strong"
            elif strength >= -75:
                connection = "Medium"
            else:
                connection = "Weak"
        else:
            connection = "Unknown"

        is_proc = body.get("isProcessing")
        meta_bits = []
        if isinstance(body.get("cpu"), (int, float)):
            meta_bits.append(f"CPU {body['cpu']:.1f}%")
        if isinstance(body.get("ram"), (int, float)):
            meta_bits.append(f"RAM {body['ram']:.1f}%")
        if isinstance(body.get("gpu"), (int, float)):
            meta_bits.append(f"GPU {body['gpu']:.1f}%")
        if is_proc is True:
            meta_bits.append("Processing")
        metadata = " • ".join(meta_bits) if meta_bits else "N/A"

        return {
            "name": name,
            "location": "IP: unknown",
            "status": "Online",
            "connection": connection,
            "metadata": metadata,
        }

    def _emit_full_device_list():
        with devices_lock:
            gui_devices = list(devices_by_name.values())
        ui.update_devices_signal.emit(gui_devices)

    def _on_packet(pkt: Dict[str, Any]) -> None:
        try:
            header = (pkt or {}).get("header", {}) if isinstance(pkt, dict) else {}
            msg_type = header.get("message_type")

            if msg_type == "discovery_response":
                raw = (pkt.get("body", {}) or {}).get("devices", [])
                if isinstance(raw, list):
                    with devices_lock:
                        for d in raw:
                            if not isinstance(d, dict):
                                continue
                            name = d.get("name") or "Unknown"
                            status = "Online" if (d.get("status") == "online") else "Offline"
                            strength = d.get("network_strength")
                            if isinstance(strength, (int, float)):
                                if strength >= -60:
                                    connection = "Strong"
                                elif strength >= -75:
                                    connection = "Medium"
                                else:
                                    connection = "Weak"
                            else:
                                connection = "Unknown"

                            meta_bits = []
                            if isinstance(d.get("cpu"), (int, float)):
                                meta_bits.append(f"CPU {d['cpu']:.1f}%")
                            if isinstance(d.get("ram"), (int, float)):
                                meta_bits.append(f"RAM {d['ram']:.1f}%")
                            if isinstance(d.get("gpu"), (int, float)):
                                meta_bits.append(f"GPU {d['gpu']:.1f}%")
                            if d.get("isProcessing") is True:
                                meta_bits.append("Processing")
                            metadata = " • ".join(meta_bits) if meta_bits else "N/A"

                            devices_by_name[name] = {
                                "name": name,
                                "location": "IP: unknown",
                                "status": status,
                                "connection": connection,
                                "metadata": metadata,
                            }
                    _emit_full_device_list()
                return

            if msg_type == "device_status":
                body = pkt.get("body", {}) if isinstance(pkt, dict) else {}
                if isinstance(body, dict):
                    gui_dev = _status_to_gui_device(body)
                    with devices_lock:
                        devices_by_name[gui_dev["name"]] = gui_dev
                    _emit_full_device_list()
                return
        except Exception as e:
            print(f"[HOST_MAIN] Packet handler error: {e!r}")

    # Register packet callback (supported by our compatibility shim)
    try:
        sender.set_on_packet(_on_packet)
    except Exception as e:
        print(f"[HOST_MAIN] Warning: could not register packet callback: {e!r}")

    # ---- GUI Handler (patched) wiring ----
    handler = GUIHandler(
        available_devices_window=devices_window,
        on_discover=None,  # set below
        on_query=None,     # set below
    )

    def on_discover_clicked():
        """
        Called when the GUI Discover button is clicked.
        Sends a discovery request and updates device list when response arrives.
        Runs in a background thread so the GUI never freezes.
        """
        def worker():
            try:
                # NOTE: This uses the *existing* host_client "command" format.
                cmd = {"command": "discover"}
                print(f"[HOST_MAIN] Sending discovery: {cmd}")
                resp = sender.send_command(cmd, reply_topic=DISCOVERY_REPLY_TOPIC, timeout=10.0)
                print(f"[HOST_MAIN] Discovery response: {json.dumps(resp, indent=2)}")

                raw_devices = _safe_extract_devices(resp)
            
                gui_devices = []
                for d in raw_devices:
                    gui_devices.append({
                        "name": d.get("name") or d.get("device_name") or d.get("device_id") or "Unknown",
                        "location": f"IP: {d.get('ip', '')}".strip() or "IP: unknown",
                        "status": "Online" if (str(d.get("status","")).lower() == "online") else "Offline",
                        "connection": "Strong",
                        "metadata": "v1 • Active",
                    })

                print(f"[HOST_MAIN] Updating GUI with {len(gui_devices)} device(s)")
                ui.update_devices_signal.emit(gui_devices)

            except Exception as e:
                print(f"[HOST_MAIN] Worker exception: {e!r}")
    
        threading.Thread(target=worker, daemon=True).start()

    def on_query_sent(query_text: str):
        """
        Called when the GUI Send button is clicked in the Query window.
        Sends a query request. For now, prints the response.
        (You can later route images/metadata back into GUIHandler methods.)
        """
        query_text = (query_text or "").strip()
        if not query_text:
            print("[HOST_MAIN] Query text empty — ignoring.")
            return

        def worker():
            try:
                cmd = {"command": "query", "query": query_text}
                print(f"[HOST_MAIN] Sending query: {cmd}")
                resp = sender.send_command(cmd, reply_topic=QUERY_REPLY_TOPIC, timeout=30.0)
                print(f"[HOST_MAIN] Query response: {json.dumps(resp, indent=2)[:4000]}")

                # TODO: If response contains images/metadata, forward into GUIHandler.
                # For now, you can extend this once edge publishes a proper query_response packet.

            except Exception as e:
                print(f"[HOST_MAIN] Query failed: {e}")

        threading.Thread(target=worker, daemon=True).start()

    # Tell the handler which functions to call for real user clicks
    handler.set_network_callbacks(on_discover=on_discover_clicked, on_query=on_query_sent)

    print("[HOST_MAIN] GUI is running. Use Discover to test MQTT path.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
