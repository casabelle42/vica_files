#!/usr/bin/env python3
"""
Host Main Entrypoint (production)
---------------------------------
Runs the PyQt GUI and wires GUI button clicks (Discover / Send Query) to MQTT
commands using the existing HostCommandSender class.

Code separation:
- GUI widgets          → Host/gui/s3_availableDevices.py, s4_query.py
- GUI command bus      → Host/gui/gui_handler.py
- MQTT request/response→ host_client.py
- This file            → wires them together for *production*
- Demo / offline mode  → demo_start_app.py (does not touch this file)

If you need a runnable that fakes all edge / server traffic for demos or
screenshots, run ``python demo_start_app.py`` instead. That script reuses
``run_app()`` from this module and supplies a ``DemoBackend`` in place of the
real ``MqttBackend`` — the GUI wiring is identical between the two paths.
"""

import os
import sys
import json
import base64
import hashlib
import socket
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal


# ---- Ensure project root is importable ----
current_dir = os.path.dirname(os.path.abspath(__file__))
host_dir = os.path.dirname(current_dir)        # Host/
host_team_dir = os.path.dirname(host_dir)      # Host_Team/
project_root = os.path.dirname(host_team_dir)  # project root

for path in [current_dir, host_dir, host_team_dir, project_root]:
    if path not in sys.path:
        sys.path.insert(0, path)

from s3_availableDevices import MainWindow as AvailableDevicesWindow  # noqa: E402
from gui_handler import GUIHandler  # noqa: E402
from host_client import HostCommandSender  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# HostBackend duck type
# ─────────────────────────────────────────────────────────────────────────────
@runtime_checkable
class HostBackend(Protocol):
    """Minimal contract that ``run_app`` requires from any backend.

    Both ``MqttBackend`` (production) and ``DemoBackend`` (offline demo)
    implement this. The method signatures deliberately mirror those of
    ``HostCommandSender`` in ``host_client.py`` so the production code path
    inside ``run_app`` is byte-identical to the pre-refactor version — it
    just calls ``backend.<method>`` instead of ``sender.<method>``.
    """

    def set_on_packet(self, callback: Callable[[Dict[str, Any]], None]) -> None: ...
    def send_command(self, cmd: dict,
                     reply_topic: Optional[str] = None,
                     timeout: Optional[float] = None) -> dict: ...
    def send_query_request(self, query_text: str,
                           target_devices: Optional[List[str]] = None) -> str: ...

    # Optional — backends may override; default no-op when absent.
    def close(self) -> None: ...


# ─────────────────────────────────────────────────────────────────────────────
# Production backend (real MQTT)
# ─────────────────────────────────────────────────────────────────────────────
class MqttBackend:
    """Production backend — wraps the existing ``HostCommandSender`` 1:1."""

    def __init__(self,
                 mqtt_broker: str,
                 mqtt_port: int,
                 control_topic: str,
                 default_reply_topic: str,
                 request_timeout_sec: float = 10.0) -> None:
        self._sender = HostCommandSender(
            mqtt_broker=mqtt_broker,
            mqtt_port=mqtt_port,
            control_topic=control_topic,
            default_reply_topic=default_reply_topic,
            request_timeout_sec=request_timeout_sec,
        )

    def set_on_packet(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self._sender.set_on_packet(callback)

    def send_command(self, cmd: dict,
                     reply_topic: Optional[str] = None,
                     timeout: Optional[float] = None) -> dict:
        """1:1 pass-through to ``HostCommandSender.send_command``."""
        return self._sender.send_command(cmd, reply_topic=reply_topic, timeout=timeout)

    def send_query_request(self, query_text: str,
                           target_devices: Optional[List[str]] = None) -> str:
        return self._sender.send_query_request(query_text, target_devices=target_devices)

    def close(self) -> None:
        try:
            self._sender.close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (legacy converters kept for any caller that still depends on them)
# ─────────────────────────────────────────────────────────────────────────────
def _safe_extract_devices(response: dict) -> list:
    if not isinstance(response, dict):
        return []
    if isinstance(response.get("devices"), list):
        return response["devices"]
    if isinstance(response.get("available_devices"), list):
        return response["available_devices"]
    body = response.get("body")
    if isinstance(body, dict):
        if isinstance(body.get("devices"), list):
            return body["devices"]
        if isinstance(body.get("available_devices"), list):
            return body["available_devices"]
    return []


def _to_gui_devices(raw_devices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert raw discovery device dicts into the schema expected by the GUI."""
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
            "connection": "Strong",
            "metadata": "v1 • Active",
        })
    return gui_devices


# ─────────────────────────────────────────────────────────────────────────────
# UI dispatcher (Qt-thread-safe routing for backend events)
# ─────────────────────────────────────────────────────────────────────────────
class UiDispatcher(QObject):
    update_devices_signal = pyqtSignal(list)
    process_query_packet_signal = pyqtSignal(dict, str)

    def __init__(self, window):
        super().__init__()
        self._window = window
        self.update_devices_signal.connect(self._window.update_devices)
        self._get_query_window = None
        self.process_query_packet_signal.connect(self._process_query_packet)

    def set_query_window_getter(self, getter):
        self._get_query_window = getter

    def _process_query_packet(self, pkt: Dict[str, Any], query_text: str) -> None:
        """Render query_response in QueryWindow on the Qt main thread."""
        qw = self._get_query_window() if callable(self._get_query_window) else None
        # Fallback: in some wiring paths, the GUI handler getter may not be set
        # yet. The devices window still holds the QueryWindow reference.
        if not qw:
            qw = getattr(self._window, "_query_window", None)
        if not qw:
            print("[HOST_MAIN] query_response received but query window is not open")
            return

        try:
            body = (pkt or {}).get("body", {}) if isinstance(pkt, dict) else {}
            meta = body.get("metadata", {}) if isinstance(body, dict) else {}
            frame = body.get("frame", {}) if isinstance(body, dict) else {}
            header = (pkt or {}).get("header", {}) if isinstance(pkt, dict) else {}
            detections = frame.get("detections") if isinstance(frame, dict) else []
            if not isinstance(detections, list):
                detections = []

            image_b64 = meta.get("image_base64") or ""
            image_fingerprint = ""
            if isinstance(image_b64, str) and image_b64:
                try:
                    image_bytes = base64.b64decode(image_b64, validate=False)
                    image_fingerprint = hashlib.sha1(image_bytes).hexdigest()[:10]
                except Exception:
                    image_b64 = ""

            answer_text = ""
            for key in ("answer", "response", "results", "results_text", "result"):
                v = body.get(key) if isinstance(body, dict) else None
                if isinstance(v, str) and v.strip():
                    answer_text = v.strip()
                    break
            if not answer_text and detections:
                d0 = detections[0] if isinstance(detections[0], dict) else None
                if isinstance(d0, dict):
                    dets0 = d0.get("dets")
                    if isinstance(dets0, list) and dets0 and isinstance(dets0[0], str):
                        answer_text = dets0[0].strip()

            det_labels = []
            max_conf = 0.0
            for det in detections:
                if not isinstance(det, dict):
                    continue
                lbl = det.get("label")
                if isinstance(lbl, str) and lbl.strip():
                    det_labels.append(lbl.strip())
                conf = det.get("confidence")
                if isinstance(conf, (int, float)):
                    max_conf = max(max_conf, float(conf))

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

            gui_metadata = {
                "image": f"Frame {chunk_index_i + 1}/{total_chunks_i}" + (f" • {image_fingerprint}" if image_fingerprint else ""),
                "edge_device": header.get("source_device", "Unknown"),
                "query": query_text or "User query",
                "response": answer_text or ", ".join(det_labels) or "No response text",
                "confidence_rate": f"{max_conf * 100:.1f}%",
                "time_processed": str(header.get("timestamp") or datetime.now().isoformat())[:19],
            }

            if image_b64 and hasattr(qw, "add_returned_image"):
                qw.add_returned_image(image_b64, metadata=gui_metadata)
            if hasattr(qw, "update_metadata"):
                qw.update_metadata(gui_metadata)
            if hasattr(qw, "set_query_pending"):
                qw.set_query_pending(False)
        except Exception as e:
            print(f"[HOST_MAIN] Failed to render query_response: {e!r}")


# ─────────────────────────────────────────────────────────────────────────────
# Generic GUI runner — the *only* place GUI wiring lives
# ─────────────────────────────────────────────────────────────────────────────
def run_app(backend: HostBackend,
            *,
            banner: Optional[str] = None,
            discovery_reply_topic: Optional[str] = None) -> int:
    """Build the Qt GUI and route every backend event through ``backend``.

    Both the production (``MqttBackend``) and demo (``DemoBackend``) entry
    points call this function. ``backend`` is the *only* surface through which
    network I/O happens, so a demo backend can fully simulate edge / server
    traffic without any code changes here.

    discovery_reply_topic is forwarded verbatim to ``backend.send_command``;
    the production sender currently ignores it, but we plumb it through so
    the production code path remains byte-identical to last week's behaviour.

    Returns the QApplication exit code.
    """
    if banner:
        print("=" * 70)
        for line in banner.splitlines():
            print(line)
        print("=" * 70)

    app = QApplication.instance() or QApplication(sys.argv)
    devices_window = AvailableDevicesWindow()
    devices_window.show()

    ui = UiDispatcher(devices_window)

    # ---- Live device state shared between discovery_response and device_status ----
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

    current_query_text_lock = threading.Lock()
    current_query_text = {"text": ""}
    current_query_id_lock = threading.Lock()
    current_query_id: Dict[str, Optional[str]] = {"id": None}
    inflight_lock = threading.Lock()
    inflight: Dict[str, Any] = {
        "qid": None,
        # When targeting specific devices, we track who we are still waiting on.
        # If None → broadcast / unknown fanout (we'll schedule after first response).
        "pending_devices": None,  # Optional[set[str]]
    }

    # Auto-resend control (driven by QueryWindow toggle).
    #
    # Key behavior:
    # - Never overlaps in-flight queries: the next send is only scheduled after a response arrives.
    # - Tries to maintain the requested cadence: if a response took longer than `interval_sec`,
    #   we resend immediately; otherwise we wait the remaining time.
    # - Duration is counted from the moment the user presses Send (not from when they toggle ON).
    _auto_resend = {
        "enabled": False,
        "interval_sec": 5,
        "duration_sec": 0,
        "started_ts": None,    # when the duration window begins (set on first response)
        "until_ts": None,      # started_ts + duration_sec, or None for indefinite
        "last_send_ts": None,  # when we last sent a query (set on Send / each tick)
        "last_targets": None,  # list[str] used for the run (captured on Send)
    }
    _auto_timer = {"t": None}

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

            # query_response arriving via the general results stream — handle directly.
            if msg_type == "query_response":
                body = pkt.get("body", {}) if isinstance(pkt, dict) else {}
                pkt_qid = body.get("query_id") if isinstance(body, dict) else None
                with current_query_id_lock:
                    active_qid = current_query_id.get("id")
                if active_qid and pkt_qid and str(pkt_qid) != str(active_qid):
                    return

                with current_query_text_lock:
                    qt = current_query_text.get("text", "")
                ui.process_query_packet_signal.emit(pkt, qt)

                # Enforce duration stop on *every* response.
                # Without this, multi-device gating (wait-for-all) can delay scheduling and the
                # duration check might not run, making auto-resend appear to "last longer".
                try:
                    if _auto_resend.get("enabled"):
                        until_ts_stop = _auto_resend.get("until_ts")
                        if isinstance(until_ts_stop, (int, float)) and time.time() >= float(until_ts_stop):
                            _auto_resend["enabled"] = False
                            try:
                                tprev = _auto_timer.get("t")
                                if tprev is not None:
                                    tprev.cancel()
                            except Exception:
                                pass
                            return
                except Exception:
                    pass

                # If the query was targeted to multiple devices, don't auto-resend until all
                # targeted devices have responded for this query_id; otherwise slower devices
                # will be "masked" by rapid resends (their later responses have old query_id).
                src_dev = (header or {}).get("source_device")
                can_schedule = True
                try:
                    with inflight_lock:
                        pending = inflight.get("pending_devices")
                        inflight_qid = inflight.get("qid")
                        if inflight_qid and pkt_qid and str(pkt_qid) == str(inflight_qid) and isinstance(pending, set) and pending:
                            if isinstance(src_dev, str) and src_dev in pending:
                                pending.discard(src_dev)
                            can_schedule = (len(pending) == 0)
                except Exception:
                    can_schedule = True

                # Schedule next auto-resend tick (sequential: only after the previous response(s) arrive).
                try:
                    if can_schedule and _auto_resend.get("enabled"):
                        interval = int(_auto_resend.get("interval_sec") or 0)
                        interval = max(0, interval)
                        until_ts = _auto_resend.get("until_ts")
                        now_ts = time.time()
                        # Duration semantics: start the duration window after the first response arrives
                        # (so latency doesn't "consume" the requested duration).
                        if _auto_resend.get("started_ts") is None:
                            try:
                                dur0 = int(_auto_resend.get("duration_sec") or 0)
                            except Exception:
                                dur0 = 0
                            if dur0 > 0:
                                _auto_resend["started_ts"] = now_ts
                                _auto_resend["until_ts"] = now_ts + float(dur0)
                                until_ts = _auto_resend.get("until_ts")
                        if isinstance(until_ts, (int, float)) and now_ts >= float(until_ts):
                            _auto_resend["enabled"] = False
                            return
                        # Cancel previous timer if any.
                        try:
                            tprev = _auto_timer.get("t")
                            if tprev is not None:
                                tprev.cancel()
                        except Exception:
                            pass

                        # Keep cadence: wait the remaining time since the last send.
                        last_send_ts = _auto_resend.get("last_send_ts")
                        delay = float(interval)
                        if isinstance(last_send_ts, (int, float)):
                            elapsed = max(0.0, now_ts - float(last_send_ts))
                            delay = max(0.0, float(interval) - elapsed)

                        def _tick():
                            try:
                                qw_local = handler._get_query_window()
                                # If user disabled since scheduling, skip.
                                if not _auto_resend.get("enabled"):
                                    return
                                until_ts2 = _auto_resend.get("until_ts")
                                now2 = time.time()
                                if isinstance(until_ts2, (int, float)) and now2 >= float(until_ts2):
                                    _auto_resend["enabled"] = False
                                    return
                                # Re-send using current query text + current targets.
                                with current_query_text_lock:
                                    qtxt = current_query_text.get("text", "")
                                if not qtxt:
                                    return
                                # Use the target list captured when the user pressed Send
                                # (avoid drifting to a single device if UI selection changes).
                                tgs = _auto_resend.get("last_targets")
                                if not isinstance(tgs, list):
                                    tgs = []
                                _auto_resend["last_send_ts"] = time.time()
                                on_query_sent(qtxt, target_devices=tgs)
                                if qw_local and hasattr(qw_local, "set_query_pending"):
                                    qw_local.set_query_pending(True, f"Auto resend in {interval}s…")
                            except Exception as e:
                                print(f"[HOST_MAIN] Auto resend tick failed: {e!r}")

                        _auto_timer["t"] = threading.Timer(max(0.0, float(delay)), _tick)
                        _auto_timer["t"].daemon = True
                        _auto_timer["t"].start()
                except Exception:
                    pass
                return

        except Exception as e:
            print(f"[HOST_MAIN] Packet handler error: {e!r}")

    # Register the packet callback with whichever backend was supplied.
    try:
        backend.set_on_packet(_on_packet)
    except Exception as e:
        print(f"[HOST_MAIN] Warning: could not register packet callback: {e!r}")

    # ---- GUI Handler wiring ----
    handler = GUIHandler(
        available_devices_window=devices_window,
        on_discover=None,  # set below
        on_query=None,     # set below
    )
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
                resp = backend.send_command(cmd, reply_topic=discovery_reply_topic, timeout=10.0)
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

    def on_query_sent(query_text: str, target_devices: Optional[List[str]] = None):
        query_text = (query_text or "").strip()
        if not query_text:
            print("[HOST_MAIN] Query text empty — ignoring.")
            return

        targets = [str(t).strip() for t in (target_devices or [])
                   if isinstance(t, str) and t.strip()]
        targets_str = (", ".join(targets) if targets else "broadcast (all devices)")

        with current_query_text_lock:
            current_query_text["text"] = query_text

        # If auto-resend is enabled, capture the targets for the run and reset duration
        # so it starts after the first response arrives (latency doesn't consume it).
        if _auto_resend.get("enabled"):
            try:
                _auto_resend["duration_sec"] = int(_auto_resend.get("duration_sec") or 0)
            except Exception:
                _auto_resend["duration_sec"] = 0
            started = time.time()
            _auto_resend["started_ts"] = None
            _auto_resend["until_ts"] = None
            _auto_resend["last_send_ts"] = started
            _auto_resend["last_targets"] = list(targets)

        try:
            qw = handler._get_query_window()
            if qw and hasattr(qw, "set_query_pending"):
                pending_msg = (
                    f"Pending response from {targets[0]}…" if len(targets) == 1
                    else f"Pending response from {len(targets)} devices…" if targets
                    else "Pending response..."
                )
                qw.set_query_pending(True, pending_msg)
        except Exception:
            pass

        try:
            qid = backend.send_query_request(query_text, target_devices=targets)
            with current_query_id_lock:
                current_query_id["id"] = qid
            # Track fanout for auto-resend gating.
            try:
                with inflight_lock:
                    inflight["qid"] = qid
                    inflight["pending_devices"] = set(targets) if targets else None
            except Exception:
                pass
            try:
                qw = handler._get_query_window()
                if qw and hasattr(qw, "set_last_query_id"):
                    qw.set_last_query_id(qid)
            except Exception:
                pass
            print(f"[HOST_MAIN] Query request sent (query_id={qid}, targets={targets_str})")
        except Exception as e:
            print(f"[HOST_MAIN] Failed to send query_request: {e!r}")
            try:
                qw = handler._get_query_window()
                if qw and hasattr(qw, "set_query_pending"):
                    qw.set_query_pending(False)
            except Exception:
                pass

    def on_auto_resend_changed(enabled: bool, interval_sec: int, duration_sec: int) -> None:
        _auto_resend["enabled"] = bool(enabled)
        try:
            _auto_resend["interval_sec"] = int(interval_sec)
        except Exception:
            _auto_resend["interval_sec"] = 5
        try:
            _auto_resend["duration_sec"] = int(duration_sec)
        except Exception:
            _auto_resend["duration_sec"] = 0
        # Duration window begins on the next Send (not immediately on toggle).
        if not _auto_resend["enabled"]:
            _auto_resend["started_ts"] = None
            _auto_resend["until_ts"] = None
            _auto_resend["last_send_ts"] = None
            _auto_resend["last_targets"] = None
        # Cancel any pending timer when turned off.
        if not _auto_resend["enabled"]:
            try:
                tprev = _auto_timer.get("t")
                if tprev is not None:
                    tprev.cancel()
            except Exception:
                pass

    handler.set_network_callbacks(on_discover=on_discover_clicked, on_query=on_query_sent)
    # Wire QueryWindow auto-resend toggle (if present).
    try:
        if hasattr(devices_window, "set_auto_resend_changed_callback"):
            devices_window.set_auto_resend_changed_callback(on_auto_resend_changed)
    except Exception:
        pass

    print("[HOST_MAIN] GUI is running.")
    try:
        return app.exec()
    finally:
        try:
            backend.close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Production entry point
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    MQTT_BROKER_IP = os.environ.get("VICA_MQTT_BROKER", "10.148.0.95")
    MQTT_PORT = int(os.environ.get("VICA_MQTT_PORT", "1883"))
    CONTROL_TOPIC = os.environ.get("VICA_CONTROL_TOPIC", "edge/control")

    host_id = os.environ.get("VICA_HOST_ID", socket.gethostname().replace(" ", "_"))
    DISCOVERY_REPLY_TOPIC = os.environ.get(
        "VICA_DISCOVERY_REPLY_TOPIC", f"host/{host_id}/discovery_response"
    )
    QUERY_REPLY_TOPIC = os.environ.get(
        "VICA_QUERY_REPLY_TOPIC", f"host/{host_id}/query_response"
    )

    banner = "\n".join([
        "VICA Host Main",
        f"Broker: {MQTT_BROKER_IP}:{MQTT_PORT}",
        f"Control topic: {CONTROL_TOPIC}",
        f"Discovery reply topic: {DISCOVERY_REPLY_TOPIC}",
        f"Query reply topic: {QUERY_REPLY_TOPIC}",
    ])

    backend = MqttBackend(
        mqtt_broker=MQTT_BROKER_IP,
        mqtt_port=MQTT_PORT,
        control_topic=CONTROL_TOPIC,
        default_reply_topic=QUERY_REPLY_TOPIC,
        request_timeout_sec=10.0,
    )
    return run_app(backend, banner=banner,
                   discovery_reply_topic=DISCOVERY_REPLY_TOPIC)


if __name__ == "__main__":
    sys.exit(main())
