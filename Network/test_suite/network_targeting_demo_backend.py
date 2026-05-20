import base64
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


# 1x1 PNG so GUI can render an image without external files.
_IMAGE_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WmY4lUAAAAASUVORK5CYII="
)


class NetworkTargetingDemoBackend:
    """
    Offline backend for GUI testing of target_devices routing semantics.

    - No MQTT broker required.
    - Discovery returns a fixed edge fleet.
    - Query responses are emitted only for selected target_devices.
    - If target_devices is empty/None, behaves as broadcast to all demo edges.
    """

    def __init__(self):
        self._on_packet: Optional[Callable[[Dict[str, Any]], None]] = None
        self._devices = [
            {
                "name": "Edge-Cam-01",
                "status": "online",
                "cpu": 15.0,
                "ram": 31.0,
                "gpu": 7.0,
                "network_strength": -58,
                "isProcessing": False,
                "available_models": ["dino-v2"],
                "active_model": "dino-v2",
            },
            {
                "name": "Edge-Cam-02",
                "status": "online",
                "cpu": 17.0,
                "ram": 33.0,
                "gpu": 8.0,
                "network_strength": -62,
                "isProcessing": False,
                "available_models": ["dino-v2"],
                "active_model": "dino-v2",
            },
            {
                "name": "Edge-Cam-03",
                "status": "online",
                "cpu": 19.0,
                "ram": 36.0,
                "gpu": 9.0,
                "network_strength": -67,
                "isProcessing": False,
                "available_models": ["dino-v2"],
                "active_model": "dino-v2",
            },
        ]

    def set_on_packet(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self._on_packet = callback

    def send_command(
        self,
        cmd: dict,
        reply_topic: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        command = (cmd or {}).get("command")
        if command == "discover":
            pkt = self._build_discovery_packet()
            self._emit(pkt)
            return pkt
        return {}

    def send_query_request(
        self,
        query_text: str,
        target_devices: Optional[List[str]] = None,
    ) -> str:
        query_id = str(uuid.uuid4())

        all_names = [d["name"] for d in self._devices]
        targets = [
            str(t).strip()
            for t in (target_devices or [])
            if isinstance(t, str) and str(t).strip()
        ]
        targets = [t for t in targets if t in all_names]

        if not targets:
            targets = list(all_names)
            print(f"[NetworkDemo] Broadcast query (qid={query_id}) -> {', '.join(targets)}")
        else:
            print(f"[NetworkDemo] Targeted query (qid={query_id}) -> {', '.join(targets)}")

        for idx, device_name in enumerate(targets):
            delay = 0.35 + (idx * 0.2)
            timer = threading.Timer(
                delay,
                self._emit_query_response,
                args=(device_name, query_id, query_text),
            )
            timer.daemon = True
            timer.start()

        return query_id

    def close(self) -> None:
        self._on_packet = None

    def _emit(self, pkt: Dict[str, Any]) -> None:
        cb = self._on_packet
        if cb:
            try:
                cb(pkt)
            except Exception as exc:
                print(f"[NetworkDemo] callback error: {exc!r}")

    def _build_discovery_packet(self) -> Dict[str, Any]:
        return {
            "header": {
                "timestamp": datetime.now().isoformat()[:19],
                "source_device": "Network-Demo",
                "message_type": "discovery_response",
                "message_id": str(uuid.uuid4()),
            },
            "body": {
                "devices": [dict(d) for d in self._devices],
            },
        }

    def _emit_query_response(self, source_device: str, query_id: str, query_text: str) -> None:
        pkt = {
            "header": {
                "timestamp": datetime.now().isoformat()[:19],
                "source_device": source_device,
                "message_type": "query_response",
                "message_id": str(uuid.uuid4()),
            },
            "body": {
                "query_id": query_id,
                "status": "success",
                "model_used": "dino-v2",
                "error": None,
                "answer": f"{source_device} handled query: {query_text}",
                "metadata": {
                    "image_width": 1,
                    "image_height": 1,
                    "format": "png",
                    "image_base64": _IMAGE_B64,
                    "chunk_index": 0,
                    "total_chunks": 1,
                },
                "frame": {
                    "frame_id": 0,
                    "timestamp": datetime.now().isoformat()[:19],
                    "detections": [
                        {
                            "label": "mock_object",
                            "confidence": 0.99,
                            "dets": [f"demo_det_{source_device}"],
                        }
                    ],
                },
            },
        }
        self._emit(pkt)


def demo_sleep(seconds: float) -> None:
    # Utility retained for quick local script experiments.
    time.sleep(max(0.0, float(seconds)))
