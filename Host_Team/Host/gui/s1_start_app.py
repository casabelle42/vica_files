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
import base64
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
    # Current discovery_response schema: { "body": { "devices": [ ... ] } }
    if isinstance(body, dict) and isinstance(body.get("devices"), list):
        return body["devices"]
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
    process_query_packet_signal = pyqtSignal(dict, str)

    def __init__(self, window):
        super().__init__()
        self._window = window
        self.update_devices_signal.connect(self._window.update_devices)

        # Query window is created lazily; handler will provide it when available.
        self._get_query_window = None  # Callable[[], Any] | None
        self.process_query_packet_signal.connect(self._process_query_packet)

    def set_query_window_getter(self, getter):
        self._get_query_window = getter

    def _process_query_packet(self, pkt: Dict[str, Any], query_text: str) -> None:
        """
        Runs on the Qt main thread (signal/slot), so it can safely update widgets.
        """
        qw = self._get_query_window() if callable(self._get_query_window) else None
        if not qw:
            print("[HOST_MAIN] query_response received but query window is not open")
            return

        try:
            body = (pkt or {}).get("body", {}) if isinstance(pkt, dict) else {}
            meta = body.get("metadata", {}) if isinstance(body, dict) else {}
            frame = body.get("frame", {}) if isinstance(body, dict) else {}

            image_b64 = meta.get("image_base64") or ""
            if not isinstance(image_b64, str) or not image_b64:
                print("[HOST_MAIN] query_response has no image_base64")
                return

            # Validate base64 early so add_returned_image doesn't silently no-op.
            try:
                base64.b64decode(image_b64, validate=False)
            except Exception:
                pass

            header = (pkt or {}).get("header", {}) if isinstance(pkt, dict) else {}
            detections = frame.get("detections") if isinstance(frame, dict) else None
            if not isinstance(detections, list):
                detections = []

            # Prefer a real text answer if the edge provides one.
            answer_text = ""
            if isinstance(body, dict):
                for key in ("answer", "response", "results", "results_text"):
                    v = body.get(key)
                    if isinstance(v, str) and v.strip():
                        answer_text = v.strip()
                        break

            # Fall back to detections summary (common in current schema).
            det_labels = []
            for d in detections[:3]:
                if isinstance(d, dict):
                    lbl = d.get("label")
                    if isinstance(lbl, str) and lbl.strip():
                        det_labels.append(lbl.strip())
            det_summary = ", ".join(det_labels)
            max_conf = 0.0
            for d in detections:
                if isinstance(d, dict) and isinstance(d.get("confidence"), (int, float)):
                    max_conf = max(max_conf, float(d["confidence"]))

            chunk_index = meta.get("chunk_index", 0)
            total_chunks = meta.get("total_chunks", 1)
            try:
                chunk_index_i = int(chunk_index)
            except Exception:
                chunk_index_i = 0
            try:
                total_chunks_i = int(total_chunks)
            except Exception:
                total_chunks_i = 1

            image_metadata = {
                "image": f"Frame {chunk_index_i + 1}/{total_chunks_i}",
                "edge_device": header.get("source_device", "Unknown"),
                "query": query_text or "User query",
                "response": answer_text or det_summary or "No response text",
                "confidence_rate": f"{max_conf * 100:.1f}%",
                "time_processed": str(header.get("timestamp") or datetime.now().isoformat())[:19],
            }

            # Add thumbnail/image
            if hasattr(qw, "add_returned_image"):
                qw.add_returned_image(image_b64, metadata=image_metadata)
            # Update metadata panel to latest image
            if hasattr(qw, "update_metadata"):
                qw.update_metadata(image_metadata)
        except Exception as e:
            print(f"[HOST_MAIN] Failed to render query_response: {e!r}")

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

    # Track latest query text/id so query_response rendering can label + filter it.
    # MUST be defined before we register the MQTT on_packet callback, because packets
    # can arrive immediately after connect/subscribe.
    current_query_text_lock = threading.Lock()
    current_query_text = {"text": ""}
    current_query_id_lock = threading.Lock()
    current_query_id = {"id": None}

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

            if msg_type == "query_response":
                # Filter out stale query_response packets from previous queries.
                body = pkt.get("body", {}) if isinstance(pkt, dict) else {}
                pkt_qid = body.get("query_id") if isinstance(body, dict) else None
                with current_query_id_lock:
                    active_qid = current_query_id.get("id")
                if active_qid and pkt_qid and str(pkt_qid) != str(active_qid):
                    return

                with current_query_text_lock:
                    qt = current_query_text.get("text", "")
                # Update GUI on Qt thread (thread-safe)
                ui.process_query_packet_signal.emit(pkt, qt)
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

    # Let UI dispatcher find the active query window when packets arrive
    ui.set_query_window_getter(handler._get_query_window)

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

        with current_query_text_lock:
            current_query_text["text"] = query_text

        # Clear previous images when starting a new query (if query window exists)
        try:
            qw = handler._get_query_window()
            if qw and hasattr(qw, "clear_returned_images"):
                qw.clear_returned_images()
        except Exception:
            pass

        # Send query_request async and remember query_id for filtering.
        try:
            qid = sender.send_query_request(query_text)
            with current_query_id_lock:
                current_query_id["id"] = qid
        except Exception as e:
            print(f"[HOST_MAIN] Failed to send query_request: {e!r}")
            return

        def worker():
            try:
                print("[HOST_MAIN] Query request sent (async); waiting for query_response packets...")

            except Exception as e:
                print(f"[HOST_MAIN] Query failed: {e}")

        threading.Thread(target=worker, daemon=True).start()

    # Tell the handler which functions to call for real user clicks
    handler.set_network_callbacks(on_discover=on_discover_clicked, on_query=on_query_sent)

    print("[HOST_MAIN] GUI is running. Use Discover to test MQTT path.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
