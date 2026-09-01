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

try:
    from PyQt6 import sip
except ImportError:
    sip = None


def _qt_object_alive(obj: Optional[QObject]) -> bool:
    if obj is None:
        return False
    if sip is not None:
        try:
            return not sip.isdeleted(obj)
        except Exception:
            return True
    return True


def _safe_emit_signal(owner: Optional[QObject], sig, *args) -> bool:
    """Emit from a non-Qt thread only if owner still exists (avoids deleted UiDispatcher)."""
    if owner is None or not _qt_object_alive(owner):
        return False
    try:
        sig.emit(*args)
        return True
    except RuntimeError:
        return False


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
                           target_devices: Optional[List[str]] = None,
                           model: Optional[str] = None,
                           query_id: Optional[str] = None,
                           video: Optional[str] = None) -> str: ...

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
                           target_devices: Optional[List[str]] = None,
                           model: Optional[str] = None,
                           query_id: Optional[str] = None,
                           video: Optional[str] = None) -> str:
        return self._sender.send_query_request(
            query_text,
            target_devices=target_devices,
            model=model,
            query_id=query_id,
            video=video,
        )

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


def _copy_video_fields(src: Dict[str, Any], dst: Dict[str, Any]) -> None:
    """Carry an edge's video directory report into the GUI device dict.

    Emitted by the edge in every device_status packet; the Query window turns
    these into the video picker and its two prompts.
    """
    videos = src.get("available_videos")
    if isinstance(videos, list):
        dst["available_videos"] = [str(v) for v in videos if str(v).strip()]
    vdir = src.get("video_dir")
    if isinstance(vdir, str) and vdir.strip():
        dst["video_dir"] = vdir.strip()
    if "video_dir_created" in src:
        dst["video_dir_created"] = bool(src.get("video_dir_created"))


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
    process_query_packet_signal = pyqtSignal(dict, str, bool)
    auto_resend_session_deadline_signal = pyqtSignal(object)
    # Fired from the background auto-resend timer; slot runs on the Qt main thread.
    auto_resend_due_signal = pyqtSignal()
    # Sync Query UI when the host ends a timed auto-resend session (do not re-enter host callback).
    auto_resend_force_off_signal = pyqtSignal()

    def __init__(self, window):
        super().__init__()
        self._window = window
        self.update_devices_signal.connect(self._window.update_devices)
        self._get_query_window = None
        self.process_query_packet_signal.connect(self._process_query_packet)

    def set_query_window_getter(self, getter):
        self._get_query_window = getter

    def _process_query_packet(self, pkt: Dict[str, Any], query_text: str, is_stale: bool = False) -> None:
        """Render query_response in QueryWindow on the Qt main thread.

        ``is_stale`` is True when the packet's query_id no longer matches the latest
        send — still show the answer, but do not clear the pending spinner for the
        current in-flight query.
        """
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

            qid_short = ""
            if isinstance(body, dict):
                q = body.get("query_id")
                if isinstance(q, str) and q:
                    qid_short = q[:8]

            stale_note = ""
            if is_stale and qid_short:
                stale_note = f" • reply for query …{qid_short}"
            elif is_stale:
                stale_note = " • earlier query"

            # Which source produced this frame — the edge echoes back the video
            # name it actually used (absent when it fell back to the camera).
            source_video = meta.get("video") if isinstance(meta, dict) else None
            source_note = (
                f" • {source_video}" if isinstance(source_video, str) and source_video.strip()
                else " • live camera"
            )

            gui_metadata = {
                "image": f"Frame {chunk_index_i + 1}/{total_chunks_i}"
                         + (f" • {image_fingerprint}" if image_fingerprint else "")
                         + source_note,
                "edge_device": header.get("source_device", "Unknown"),
                "query": (query_text or "User query") + stale_note,
                "response": answer_text or ", ".join(det_labels) or "No response text",
                "confidence_rate": f"{max_conf * 100:.1f}%",
                "time_processed": str(header.get("timestamp") or datetime.now().isoformat())[:19],
            }

            has_answer = bool(answer_text or det_labels)
            if hasattr(qw, "add_returned_image") and (image_b64 or has_answer):
                qw.add_returned_image(image_b64 or "", metadata=gui_metadata)
            if hasattr(qw, "update_metadata"):
                qw.update_metadata(gui_metadata)
            if hasattr(qw, "set_query_pending") and not is_stale:
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
    ui.setParent(app)

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
        if body.get("camera_open") is False:
            meta_bits.append("Camera OFF")
            cam_err = body.get("camera_error")
            if isinstance(cam_err, str) and cam_err.strip():
                meta_bits.append(cam_err.strip()[:48])
        elif body.get("camera_open") is True:
            meta_bits.append("Camera OK")
        metadata = " • ".join(meta_bits) if meta_bits else "N/A"

        gui_dev = {
            "name": name,
            "location": "IP: unknown",
            "status": "Online",
            "connection": connection,
            "metadata": metadata,
        }
        if isinstance(body.get("available_models"), list):
            gui_dev["available_models"] = body["available_models"]
        active = body.get("active_model")
        if isinstance(active, str) and active.strip():
            gui_dev["active_model"] = active.strip()
        _copy_video_fields(body, gui_dev)
        return gui_dev

    def _emit_full_device_list():
        with devices_lock:
            gui_devices = list(devices_by_name.values())
        _safe_emit_signal(ui, ui.update_devices_signal, gui_devices)

    current_query_text_lock = threading.Lock()
    current_query_text = {"text": ""}
    current_query_id_lock = threading.Lock()
    current_query_id: Dict[str, Optional[str]] = {"id": None}
    inflight_lock = threading.Lock()
    inflight: Dict[str, Any] = {"qid": None}

    # Auto-resend: optional wall-clock session from Send (until_ts). Cadence is send-paced: after each
    # successful send, a timer fires once per interval_sec (not on every MQTT reply), so a fast edge
    # cannot starve a slower one. Late replies (older query_id) still update the UI.
    _auto_resend = {
        "enabled": False,
        "interval_sec": 5,
        "duration_sec": 0,
        "until_ts": None,
        "last_send_ts": None,
        "last_targets": None,
    }
    _auto_timer = {"t": None}
    _auto_was_enabled = False

    def _cancel_auto_timer() -> None:
        try:
            tprev = _auto_timer.get("t")
            if tprev is not None:
                tprev.cancel()
        except Exception:
            pass
        _auto_timer["t"] = None

    def _arm_auto_resend_session(anchor_ts: Optional[float] = None) -> None:
        """Start or refresh the wall-clock session window from duration_sec."""
        try:
            dur = int(_auto_resend.get("duration_sec") or 0)
        except Exception:
            dur = 0
        if dur <= 0:
            _auto_resend["until_ts"] = None
        else:
            started = float(anchor_ts if anchor_ts is not None else time.time())
            _auto_resend["until_ts"] = started + float(dur)
        _safe_emit_signal(
            ui,
            ui.auto_resend_session_deadline_signal,
            _auto_resend.get("until_ts"),
        )

    def _auto_resend_expired(now_ts: Optional[float] = None) -> bool:
        until_ts = _auto_resend.get("until_ts")
        if not isinstance(until_ts, (int, float)):
            return False
        now = time.time() if now_ts is None else float(now_ts)
        return now >= float(until_ts)

    def _stop_auto_resend_session() -> None:
        """End timed auto-resend: cancel timer, clear state, sync Query UI toggle."""
        _auto_resend["enabled"] = False
        nonlocal _auto_was_enabled
        _auto_was_enabled = False
        _cancel_auto_timer()
        _auto_resend["until_ts"] = None
        _auto_resend["last_targets"] = None
        _auto_resend["last_send_ts"] = None
        _safe_emit_signal(ui, ui.auto_resend_session_deadline_signal, None)
        _safe_emit_signal(ui, ui.auto_resend_force_off_signal)

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
                            if d.get("camera_open") is False:
                                meta_bits.append("Camera OFF")
                            elif d.get("camera_open") is True:
                                meta_bits.append("Camera OK")
                            metadata = " • ".join(meta_bits) if meta_bits else "N/A"

                            dev_entry = {
                                "name": name,
                                "location": "IP: unknown",
                                "status": status,
                                "connection": connection,
                                "metadata": metadata,
                            }
                            if isinstance(d.get("available_models"), list):
                                dev_entry["available_models"] = d["available_models"]
                            active = d.get("active_model")
                            if isinstance(active, str) and active.strip():
                                dev_entry["active_model"] = active.strip()
                            _copy_video_fields(d, dev_entry)
                            devices_by_name[name] = dev_entry
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
                is_stale = bool(active_qid and pkt_qid and str(pkt_qid) != str(active_qid))

                with current_query_text_lock:
                    qt = current_query_text.get("text", "")
                if not _safe_emit_signal(ui, ui.process_query_packet_signal, pkt, qt, is_stale):
                    return

                # Wall-clock session end (checked on every reply, including late ones).
                try:
                    if _auto_resend.get("enabled") and _auto_resend_expired():
                        _stop_auto_resend_session()
                        return
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
                _safe_emit_signal(ui, ui.update_devices_signal, gui_devices)

            except Exception as e:
                print(f"[HOST_MAIN] Worker exception: {e!r}")

        threading.Thread(target=worker, daemon=True).start()

    def _schedule_auto_resend_after_send() -> None:
        """Arm one-shot timer for the next auto query: interval_sec after last successful send.

        Not driven by MQTT replies — avoids a fast edge resetting the timer so a slower edge
        rarely sees a fresh query_id before the next broadcast.
        """
        if not _auto_resend.get("enabled"):
            return
        now_ts = time.time()
        # Timed session with no deadline yet (e.g. armed only on toggle) — anchor now.
        try:
            dur = int(_auto_resend.get("duration_sec") or 0)
        except Exception:
            dur = 0
        if dur > 0 and _auto_resend.get("until_ts") is None:
            _arm_auto_resend_session(now_ts)
        if _auto_resend_expired(now_ts):
            _stop_auto_resend_session()
            return
        _cancel_auto_timer()
        interval = int(_auto_resend.get("interval_sec") or 5)
        interval = max(1, interval)

        def _tick() -> None:
            _safe_emit_signal(ui, ui.auto_resend_due_signal)

        _auto_timer["t"] = threading.Timer(float(interval), _tick)
        _auto_timer["t"].daemon = True
        _auto_timer["t"].start()

    def on_query_sent(
        query_text: str,
        target_devices: Optional[List[str]] = None,
        *,
        anchor_session: bool = True,
    ):
        query_text = (query_text or "").strip()
        if not query_text:
            print("[HOST_MAIN] Query text empty — ignoring.")
            return

        targets = [str(t).strip() for t in (target_devices or [])
                   if isinstance(t, str) and t.strip()]
        targets_str = (", ".join(targets) if targets else "broadcast (all devices)")

        with current_query_text_lock:
            current_query_text["text"] = query_text

        # Keep auto-resend fanout aligned with the actual target list on every send while auto is on
        # (not only the user's first anchor Send), so chip / checkbox changes apply to subsequent ticks.
        if _auto_resend.get("enabled"):
            _auto_resend["last_targets"] = list(targets)

        # User Send resets the wall-clock window; auto ticks keep the existing until_ts.
        if _auto_resend.get("enabled") and anchor_session:
            _arm_auto_resend_session(time.time())

        try:
            qw = handler._get_query_window()
            if qw and hasattr(qw, "set_query_pending"):
                pending_msg = (
                    f"Pending response from {targets[0]}…" if len(targets) == 1
                    else f"Pending response from {len(targets)} devices…" if targets
                    else "Pending response (broadcast)…"
                )
                qw.set_query_pending(True, pending_msg)
        except Exception:
            pass

        try:
            model_groups: List[tuple] = [(targets, None)]
            qw_models = handler._get_query_window()
            try:
                if qw_models and hasattr(qw_models, "resolve_query_model_groups"):
                    model_groups = qw_models.resolve_query_model_groups(targets)
                elif hasattr(devices_window, "resolve_query_model_groups"):
                    model_groups = devices_window.resolve_query_model_groups(targets)
            except Exception:
                model_groups = [(targets, None)]

            # Video source picked in the Query window (None = live camera).
            selected_video: Optional[str] = None
            try:
                qw_video = handler._get_query_window()
                if qw_video and hasattr(qw_video, "selected_video"):
                    selected_video = qw_video.selected_video()
            except Exception:
                selected_video = None

            qid: Optional[str] = None
            for group_targets, group_model in model_groups:
                qid = backend.send_query_request(
                    query_text,
                    target_devices=group_targets or None,
                    model=group_model,
                    query_id=qid,
                    video=selected_video,
                )

            with current_query_id_lock:
                current_query_id["id"] = qid
            try:
                with inflight_lock:
                    inflight["qid"] = qid
            except Exception:
                pass
            _auto_resend["last_send_ts"] = time.time()
            try:
                qw = handler._get_query_window()
                if qw and hasattr(qw, "set_last_query_id"):
                    qw.set_last_query_id(qid or "")
            except Exception:
                pass
            model_bits = [
                f"{m or 'default'}→{', '.join(tg) if tg else 'broadcast'}"
                for tg, m in model_groups
            ]
            print(
                f"[HOST_MAIN] Query request sent (query_id={qid}, targets={targets_str}"
                f", source={selected_video or 'live camera'}"
                f"{', models: ' + '; '.join(model_bits) if any(m for _, m in model_groups) else ''})"
            )
            if _auto_resend.get("enabled"):
                _schedule_auto_resend_after_send()
        except Exception as e:
            print(f"[HOST_MAIN] Failed to send query_request: {e!r}")
            try:
                qw = handler._get_query_window()
                if qw and hasattr(qw, "set_query_pending"):
                    qw.set_query_pending(False)
            except Exception:
                pass

    def _do_automated_resend_on_main_thread() -> None:
        """Runs on the Qt main thread (invoked via auto_resend_due_signal from the timer thread)."""
        try:
            if not _auto_resend.get("enabled"):
                return
            if _auto_resend_expired():
                _stop_auto_resend_session()
                return
            with current_query_text_lock:
                qtxt = current_query_text.get("text", "")
            if not qtxt:
                return
            tgs: list[str] = []
            qw = handler._get_query_window()
            if qw and hasattr(qw, "target_devices"):
                try:
                    tgs = list(qw.target_devices())
                except Exception:
                    tgs = []
            on_query_sent(qtxt, target_devices=tgs, anchor_session=False)
        except Exception as e:
            print(f"[HOST_MAIN] Auto resend tick failed: {e!r}")

    ui.auto_resend_due_signal.connect(_do_automated_resend_on_main_thread)

    def on_auto_resend_changed(enabled: bool, interval_sec: int, duration_sec: int) -> None:
        nonlocal _auto_was_enabled
        was_enabled = _auto_was_enabled
        _auto_resend["enabled"] = bool(enabled)
        try:
            _auto_resend["interval_sec"] = max(1, int(interval_sec))
        except Exception:
            _auto_resend["interval_sec"] = 5
        try:
            _auto_resend["duration_sec"] = int(duration_sec)
        except Exception:
            _auto_resend["duration_sec"] = 0
        # Duration window is applied on the next Send.
        if not _auto_resend["enabled"]:
            _stop_auto_resend_session()
            return

        _auto_was_enabled = True
        # Start wall-clock window as soon as Auto Resend is turned on (not only after Send).
        try:
            dur_on = int(_auto_resend.get("duration_sec") or 0)
        except Exception:
            dur_on = 0
        if dur_on > 0:
            _arm_auto_resend_session(time.time())
        # First transition to ON: arm cadence if there is already query text (no extra Send needed).
        if not was_enabled:
            try:
                with current_query_text_lock:
                    has_txt = bool((current_query_text.get("text") or "").strip())
                if has_txt:
                    _schedule_auto_resend_after_send()
            except Exception:
                pass

    handler.set_network_callbacks(on_discover=on_discover_clicked, on_query=on_query_sent)

    def _forward_auto_resend_session_deadline(ts: object) -> None:
        qw = handler._get_query_window()
        if qw and hasattr(qw, "set_auto_resend_session_deadline"):
            qw.set_auto_resend_session_deadline(ts if isinstance(ts, (int, float)) else None)

    ui.auto_resend_session_deadline_signal.connect(_forward_auto_resend_session_deadline)

    def _sync_query_auto_resend_off() -> None:
        try:
            qw = handler._get_query_window()
            if qw and hasattr(qw, "sync_auto_resend_off"):
                qw.sync_auto_resend_off()
        except Exception:
            pass

    ui.auto_resend_force_off_signal.connect(_sync_query_auto_resend_off)

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
    MQTT_BROKER_IP = os.environ.get("VICA_MQTT_BROKER", "10.148.1.35")
    MQTT_PORT = int(os.environ.get("VICA_MQTT_PORT", "1884"))
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
