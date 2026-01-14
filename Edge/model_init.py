#!/usr/bin/env python3
"""
Model_Init.py — Jetson container + model lifecycle + per-frame inference loop.

Responsibilities (Tyuss):
- Start/verify Jetson Docker container for the VLM stack
- Load model weights; emit INIT -> MODEL_READY state to server
- Receive queries/commands from server, run per-frame inference
- Stream JSON per frame: machine, CPU/RAM, question, results, image (b64)
- Support pause/resume without unloading model
"""

import os, json, time, base64, socket, threading, queue, subprocess, platform, signal
from dataclasses import dataclass
from typing import Optional, Dict, Any
import psutil
import cv2

# ========= Configuration =========

@dataclass
class Config:
    # Networking to Raspberry Pi server
    SERVER_HOST: str = os.getenv("SERVER_HOST", "192.168.1.100")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "5055"))
    # Camera
    CAMERA_INDEX: int = int(os.getenv("CAMERA_INDEX", "0"))
    FRAME_INTERVAL_SEC: float = float(os.getenv("FRAME_INTERVAL_SEC", "0.05"))  # ~20 FPS
    # Container/Model
    CONTAINER_NAME: str = os.getenv("CONTAINER_NAME", "nano-vlm")
    DOCKER_IMAGE: str = os.getenv("DOCKER_IMAGE", "yourrepo/nano-vlm:jetson")
    AUTO_START_CONTAINER: bool = os.getenv("AUTO_START_CONTAINER", "1") == "1"
    # Protocol
    MACHINE_NAME: str = os.getenv("MACHINE_NAME", platform.node())
    RECONNECT_DELAY_SEC: float = float(os.getenv("RECONNECT_DELAY_SEC", "2.0"))
    # Control
    LOG_EVERY_N_FRAMES: int = int(os.getenv("LOG_EVERY_N_FRAMES", "60"))

CFG = Config()

# ========= Simple TCP client (replace with websockets/ZeroMQ if you prefer) =========

class PiClient:
    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self.sock: Optional[socket.socket] = None
        self.lock = threading.Lock()

    def connect(self):
        while True:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((self.host, self.port))
                with self.lock:
                    self.sock = s
                return
            except Exception:
                time.sleep(CFG.RECONNECT_DELAY_SEC)

    def send_json(self, payload: Dict[str, Any]):
        data = (json.dumps(payload) + "\n").encode("utf-8")
        with self.lock:
            if not self.sock:
                raise RuntimeError("Socket not connected")
            try:
                self.sock.sendall(data)
            except Exception:
                # reconnect and retry once
                self.connect()
                self.sock.sendall(data)

    def recv_line(self, timeout: float = 0.1) -> Optional[str]:
        if not self.sock:
            return None
        self.sock.settimeout(timeout)
        try:
            buf = self.sock.recv(4096)
            if not buf:
                # server closed; force reconnect
                self.connect()
                return None
            return buf.decode("utf-8", errors="ignore")
        except socket.timeout:
            return None
        except Exception:
            self.connect()
            return None

# ========= Container helpers (simple) =========

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

    def run(self):
        self.cap = cv2.VideoCapture(self.cam_index)
        if not self.cap.isOpened():
            print(f"[camera] failed to open index {self.cam_index}")
            return
        while not self.stop_ev.is_set():
            ok, frame = self.cap.read()
            if ok:
                self.out_q.put(frame)
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

# ========= Main state machine =========

class ModelService:
    def __init__(self):
        self.client = PiClient(CFG.SERVER_HOST, CFG.SERVER_PORT)
        self.model = NanoVLM()
        self.frames = queue.Queue(maxsize=5)
        self.cam_worker = CameraWorker(CFG.CAMERA_INDEX, self.frames)
        self.frame_counter = 0
        self.running = True

    def send_status(self, state: str, extra: Optional[Dict[str, Any]] = None):
        payload = {
            "type": "status",
            "state": state,               # INIT, MODEL_READY, RUNNING, PAUSED
            "machine": CFG.MACHINE_NAME,
            "metrics": sys_metrics(),
            "extra": extra or {},
            "ts": time.time(),
        }
        self.client.send_json(payload)

    def send_frame_result(self, question: str, result: Dict[str, Any], frame_b64: str):
        payload = {
            "type": "frame_result",
            "machine": CFG.MACHINE_NAME,
            "metrics": sys_metrics(),
            "question": question,
            "result": result,
            "image_b64_jpg": frame_b64,
            "ts": time.time(),
        }
        self.client.send_json(payload)

    def handle_server_commands(self, text: str):
        """
        Expect newline-delimited JSON commands like:
        {"cmd":"set_query","question":"find white car"}
        {"cmd":"pause"} / {"cmd":"resume"} / {"cmd":"stop"}
        """
        for line in filter(None, text.splitlines()):
            try:
                msg = json.loads(line)
            except Exception:
                continue
            cmd = msg.get("cmd")
            if cmd == "set_query":
                q = msg.get("question", "")
                self.model.set_query(q)
                if self.model.paused:
                    self.model.resume()
                self.send_status("RUNNING", {"question": q})
            elif cmd == "pause":
                self.model.pause()
                self.send_status("PAUSED", {})
            elif cmd == "resume":
                self.model.resume()
                self.send_status("RUNNING", {"question": self.model.current_query})
            elif cmd == "stop":
                # stop sending results but keep model loaded (per docs)
                self.model.pause()
                self.send_status("PAUSED", {"reason": "stop command"})
            else:
                # no-op / unknown
                pass

    def run(self):
        # 1) Connect to server
        self.client.connect()

        # 2) Container lifecycle
        ensure_container_running()

        # 3) Emit INIT, then load model
        self.send_status("INIT", {})
        self.model.load()
        self.send_status("MODEL_READY", {})

        # 4) Start camera
        self.cam_worker.start()

        # 5) Main loop: read frames, poll server for commands, run inference if running
        try:
            last_cmd_poll = 0
            while self.running:
                now = time.time()
                if now - last_cmd_poll > 0.1:
                    resp = self.client.recv_line(timeout=0.01)
                    if resp:
                        self.handle_server_commands(resp)
                    last_cmd_poll = now

                if self.model.paused or not self.model.loaded or not self.model.current_query:
                    time.sleep(0.01)
                    continue

                try:
                    frame = self.frames.get(timeout=0.2)
                except queue.Empty:
                    continue

                result = self.model.infer(frame)
                img_b64 = encode_jpeg_b64(frame)
                self.send_frame_result(self.model.current_query, result, img_b64)

                self.frame_counter += 1
                if self.frame_counter % CFG.LOG_EVERY_N_FRAMES == 0:
                    print(f"[loop] sent {self.frame_counter} frames")
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    def shutdown(self):
        print("[shutdown] stopping camera + service")
        self.cam_worker.stop()
        self.running = False
        # keep container/model alive by design; just exit process

def main():
    svc = ModelService()
    def _sigterm(_a,_b):
        svc.shutdown()
        os._exit(0)
    signal.signal(signal.SIGTERM, _sigterm)
    signal.signal(signal.SIGINT, _sigterm)
    svc.run()

if __name__ == "__main__":
    main()
