#!/usr/bin/env python3
"""
Model_Init.py — Jetson container + model lifecycle + per-frame inference.

Responsibilities:
- Start/verify Jetson Docker container for the VLM stack
- Load model weights; emit INIT -> MODEL_READY state via callback
- Accept inference requests, run per-frame inference, return results to handler
- Support pause/resume without unloading model
"""

import os, time, base64, threading, queue, subprocess, platform
from dataclasses import dataclass
from typing import Optional, Dict, Any, Callable
import psutil
import cv2

# ========= Configuration =========

@dataclass
class Config:
    # Camera
    CAMERA_INDEX: int = int(os.getenv("CAMERA_INDEX", "0"))
    # Optional: GStreamer pipeline string (useful for Jetson CSI cameras that don't expose /dev/video*)
    # Example:
    # export CAMERA_GSTREAMER="nvarguscamerasrc sensor-id=0 ! video/x-raw(memory:NVMM), width=1280, height=720, framerate=30/1 ! nvvidconv ! video/x-raw, format=BGRx ! videoconvert ! video/x-raw, format=BGR ! appsink drop=true"
    CAMERA_GSTREAMER: str = os.getenv("CAMERA_GSTREAMER", "").strip()
    FRAME_INTERVAL_SEC: float = float(os.getenv("FRAME_INTERVAL_SEC", "0.05"))  # ~20 FPS
    # Results
    # How many frames to return per query (as chunked query_response packets).
    RETURN_FRAMES: int = int(os.getenv("RETURN_FRAMES", "3"))
    # Container/Model
    CONTAINER_NAME: str = os.getenv("CONTAINER_NAME", "nano-vlm")
    DOCKER_IMAGE: str = os.getenv("DOCKER_IMAGE", "yourrepo/nano-vlm:jetson")
    AUTO_START_CONTAINER: bool = os.getenv("AUTO_START_CONTAINER", "1") == "1"
    # Identity
    MACHINE_NAME: str = os.getenv("MACHINE_NAME", platform.node())

CFG = Config()

# ========= Container helpers =========

def ensure_container_running() -> None:
    """
    Ensures the inference container is up. You can:
    - use `docker SDK for Python`, or
    - shell out to `docker`.
    """
    if not CFG.AUTO_START_CONTAINER:
        return
    try:
        # Check if running
        status = subprocess.run(
            ["bash", "-lc", f"docker ps --filter name={CFG.CONTAINER_NAME} --format '{{{{.Names}}}}'"],
            capture_output=True, text=True
        )
        names = [n.strip() for n in status.stdout.splitlines() if n.strip()]
        if CFG.CONTAINER_NAME in names:
            return

        # Try to start existing
        subprocess.run(["bash", "-lc", f"docker start {CFG.CONTAINER_NAME}"], check=False)

        # If still not running, run a new one (mounts/env as needed)
        status = subprocess.run(
            ["bash", "-lc", f"docker ps --filter name={CFG.CONTAINER_NAME} --format '{{{{.Names}}}}'"],
            capture_output=True, text=True
        )
        if CFG.CONTAINER_NAME not in [n.strip() for n in status.stdout.splitlines()]:
            run_cmd = (
                f"docker run -d --rm --gpus all "
                f"--name {CFG.CONTAINER_NAME} "
                f"-e NVIDIA_DRIVER_CAPABILITIES=compute,utility,video "
                f"-v /data/models:/models "
                f"{CFG.DOCKER_IMAGE} sleep infinity"
            )
            subprocess.run(["bash", "-lc", run_cmd], check=True)
    except Exception as e:
        print(f"[container] warn: {e}")

# ========= Model scaffold =========

class NanoVLM:
    """
    Placeholder for your quantized VILA / LLaVA stack.
    Replace TODOs with real loads/inference on Jetson.
    """
    def __init__(self):
        self.loaded = False
        self.paused = False
        self.current_query: Optional[str] = None

    def load(self):
        # TODO: import torch/transformers; warm up CUDA; load quantized weights
        # e.g., torch.set_default_dtype(...); model = AutoModel.from_pretrained(..., device_map="cuda")
        # NOTE: first load may take ~1–2 minutes on Jetson (per docs)
        time.sleep(3)  # simulate load
        self.loaded = True

    def set_query(self, q: Optional[str]):
        self.current_query = q

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def infer(self, frame_bgr) -> Dict[str, Any]:
        """
        Run per-frame inference. Return *structured* results.
        """
        # TODO: Live LLaVA → candidate frames → Nano VLM classification
        # Minimal stub result:
        h, w = frame_bgr.shape[:2]
        return {
            "summary": f"Stub result for query='{self.current_query or ''}' on frame {w}x{h}",
            "detections": [
                # Example: {"label": "white_car", "conf": 0.42, "bbox": [x1,y1,x2,y2]}
            ]
        }

# ========= Camera worker =========

class CameraWorker(threading.Thread):
    def __init__(self, cam_index: int, out_q: queue.Queue):
        super().__init__(daemon=True)
        self.cam_index = cam_index
        self.out_q = out_q
        self.stop_ev = threading.Event()
        self.cap = None
        self._frame_id = 0

    def run(self):
        if CFG.CAMERA_GSTREAMER:
            # Prefer explicit pipeline when provided (common for Jetson CSI cameras)
            self.cap = cv2.VideoCapture(CFG.CAMERA_GSTREAMER, cv2.CAP_GSTREAMER)
        else:
            self.cap = cv2.VideoCapture(self.cam_index)
        if not self.cap.isOpened():
            src = "gstreamer pipeline" if CFG.CAMERA_GSTREAMER else f"index {self.cam_index}"
            print(f"[camera] failed to open camera ({src}).")
            return
        while not self.stop_ev.is_set():
            ok, frame = self.cap.read()
            if ok:
                self._frame_id += 1
                frame_ts = time.time()
                # Keep only the most recent frame to avoid stale frames being reused
                # across multiple queries when the consumer is slower than the camera.
                while not self.out_q.empty():
                    try:
                        self.out_q.get_nowait()
                    except Exception:
                        break
                try:
                    # Store (frame_id, timestamp, frame_bgr)
                    self.out_q.put_nowait((self._frame_id, frame_ts, frame))
                except Exception:
                    pass
            time.sleep(CFG.FRAME_INTERVAL_SEC)

    def stop(self):
        self.stop_ev.set()
        if self.cap:
            self.cap.release()

# ========= Utility =========

def encode_jpeg_b64(frame_bgr) -> str:
    ok, buf = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if not ok:
        return ""
    return base64.b64encode(buf.tobytes()).decode("ascii")

def sys_metrics() -> Dict[str, Any]:
    vm = psutil.virtual_memory()
    return {
        "cpu_pct": psutil.cpu_percent(interval=None),
        "ram_used_mb": int((vm.total - vm.available) / (1024*1024)),
        "ram_total_mb": int(vm.total / (1024*1024)),
    }

# ========= Model service =========

class ModelService:
    """
    Manages the VLM container and model lifecycle.
    Accepts inference requests from handler.py and returns results via callback.
    Has no network connections — all I/O is handled by client.py.
    """

    def __init__(self, on_status_update: Optional[Callable] = None):
        self._on_status_update = on_status_update
        self.model = NanoVLM()
        self.frames: queue.Queue = queue.Queue(maxsize=5)
        self.cam_worker = CameraWorker(CFG.CAMERA_INDEX, self.frames)

    # -------------------------
    # Pause / resume
    # -------------------------

    @property
    def paused(self) -> bool:
        return self.model.paused

    @paused.setter
    def paused(self, value: bool):
        if value:
            self.model.pause()
        else:
            self.model.resume()

    # -------------------------
    # Internal status emit
    # -------------------------

    def _emit_status(self, state: str, extra: Optional[Dict[str, Any]] = None):
        if self._on_status_update:
            self._on_status_update("status", {
                "state": state,
                "machine": CFG.MACHINE_NAME,
                "metrics": sys_metrics(),
                "extra": extra or {},
                "ts": time.time(),
            })

    # -------------------------
    # Lifecycle
    # -------------------------

    def start(self) -> bool:
        """
        Ensure the container is running, load the model, and start the camera.
        Called by handler.py in a background thread. Returns True on success.
        """
        ensure_container_running()
        self._emit_status("INIT")
        self.model.load()
        self._emit_status("MODEL_READY")
        self.cam_worker.start()
        return True

    def shutdown(self):
        """Stop the camera. Container and model weights stay loaded by design."""
        self.cam_worker.stop()

    # -------------------------
    # Inference
    # -------------------------

    def run_inference(self, query_text: str) -> Dict[str, Any]:
        """
        Run inference for query_text on the next available camera frame.
        Returns {"image": base64_jpeg_str, "results": str}.
        Returns {} if no frame is available within the timeout.
        """
        results = self.run_inference_many(query_text, num_frames=1, timeout_sec=2.0)
        return results[0] if results else {}

    def run_inference_many(self, query_text: str, num_frames: int, timeout_sec: float = 2.0) -> list[Dict[str, Any]]:
        """
        Run inference for query_text on up to num_frames camera frames.
        Returns a list of {"frame_id","frame_ts","image","results"} dicts.
        """
        # Guardrails
        try:
            n = int(num_frames)
        except Exception:
            n = 1
        n = max(1, min(n, 10))  # keep it reasonable

        self.model.set_query(query_text)

        out: list[Dict[str, Any]] = []
        deadline = time.time() + float(timeout_sec)

        while len(out) < n and time.time() < deadline:
            try:
                remaining = max(0.01, deadline - time.time())
                frame_id, frame_ts, frame = self.frames.get(timeout=remaining)
            except queue.Empty:
                break

            result = self.model.infer(frame)
            out.append(
                {
                    "frame_id": frame_id,
                    "frame_ts": frame_ts,
                    "image": encode_jpeg_b64(frame),
                    "results": result.get("summary", ""),
                }
            )

        return out
