#!/usr/bin/env python3
import json
import queue
import threading
import time
import uuid
import paho.mqtt.client as mqtt


class MQTTHostClient:

    def __init__(self, mqtt_broker="localhost", mqtt_port=1883, auto_discover_on_connect: bool = False):
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.auto_discover_on_connect = bool(auto_discover_on_connect)
        self.device_status_cache = {}

        self.outgoing_queue = queue.Queue()
        self.incoming_queue = queue.Queue()

        # Non-destructive "latest packet" cache for request/response style usage.
        self._last_by_type = {}
        self._last_lock = threading.Lock()
        self._last_cv = threading.Condition(self._last_lock)

        # Optional hook for consumers (e.g., GUI thread bridge).
        self.on_packet = None  # Callable[[dict], None] | None

        # Background publisher loop management
        self._publisher_stop = threading.Event()
        self._publisher_thread = None

        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            print(f"[MQTTHostClient] Connected to {self.mqtt_broker}:{self.mqtt_port}")
            client.subscribe("host/results")
            print("[MQTTHostClient] Subscribed to host/results")
            if self.auto_discover_on_connect:
                # Optional: send discovery immediately after subscription is active.
                self._publish_direct("host/control", {
                    "header": {
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "source_device": "host",
                        "message_id": str(uuid.uuid4()),
                        "message_type": "discovery"
                    },
                    "body": {}
                })
                print("[MQTTHostClient] Sent discovery request (auto)")
        else:
            print(f"[MQTTHostClient] Connection failed rc={rc}")

    def _on_mqtt_message(self, client, userdata, msg):
        try:
            payload_str = msg.payload.decode()
            print(f"[MQTTHostClient] Received on {msg.topic}: {payload_str[:300]}")
            pkt = json.loads(payload_str)
            self.incoming_queue.put(pkt)
            self._handle_incoming(pkt)
        except Exception as e:
            print(f"[MQTTHostClient] Error handling message: {e}")

    def _handle_incoming(self, pkt):
        if not isinstance(pkt, dict):
            return
        msg_type = pkt.get("header", {}).get("message_type")

        # Update non-destructive cache and notify waiters.
        if msg_type:
            with self._last_cv:
                self._last_by_type[msg_type] = pkt
                self._last_cv.notify_all()

        # Optional consumer hook (best-effort; keep MQTT thread resilient).
        cb = getattr(self, "on_packet", None)
        if callable(cb):
            try:
                cb(pkt)
            except Exception as e:
                print(f"[MQTTHostClient] on_packet callback error: {e}")

        if msg_type == "discovery_response":
            devices = pkt.get("body", {}).get("devices", [])
            print(f"\n[MQTTHostClient] Discovery response - {len(devices)} device(s):")
            for d in devices:
                icon = "[ONLINE]" if d.get("status") == "online" else "[OFFLINE]"
                print(f"  {icon} {d.get('name')} | CPU: {d.get('cpu', 0):.1f}% | "
                    f"RAM: {d.get('ram', 0):.1f}% | GPU: {d.get('gpu', 0):.1f}%")

        elif msg_type == "device_status":
            body = pkt.get("body", {})
            name = body.get("name", "unknown")
            # Store latest status per device, don't print every single one
            self.device_status_cache[name] = {
                "body": body,
                "last_seen": time.time()
            }

        else:
            print(f"[MQTTHostClient] Result: {json.dumps(pkt, indent=2)}")

    def _make_header(self, message_type: str) -> dict:
        return {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source_device": "host",
            "message_id": str(uuid.uuid4()),
            "message_type": message_type
        }

    def get_last(self, message_type: str):
        """Get the most recent packet for a message_type (non-destructive)."""
        with self._last_lock:
            return self._last_by_type.get(message_type)

    def wait_for_message_type(self, message_type: str, timeout: float = 10.0):
        """Wait for a packet with given message_type (non-destructive)."""
        deadline = time.time() + float(timeout)
        with self._last_cv:
            existing = self._last_by_type.get(message_type)
            if existing is not None:
                return existing

            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                self._last_cv.wait(timeout=min(0.25, remaining))
                pkt = self._last_by_type.get(message_type)
                if pkt is not None:
                    return pkt

    def _publish_direct(self, topic: str, pkt: dict):
        """Publish immediately — use only from on_connect or the main loop thread."""
        payload = json.dumps(pkt, separators=(",", ":"), ensure_ascii=False)
        self.mqtt_client.publish(topic, payload)

    def send_discovery(self):
        pkt = {"header": self._make_header("discovery"), "body": {}}
        self.outgoing_queue.put(("host/control", pkt))
        print("[MQTTHostClient] Queued discovery request")

    def send_query_request(self, query: str, query_id: str | None = None):
        query_id = str(query_id or uuid.uuid4())
        pkt = {
            "header": self._make_header("query_request"),
            "body": {
                "query_id": query_id,
                "query": str(query or ""),
            },
        }
        self.outgoing_queue.put(("host/control", pkt))
        print(f"[MQTTHostClient] Queued query_request id={query_id}")
        return query_id

    def send_cancel_query_request(self, query_id: str):
        pkt = {
            "header": self._make_header("cancel_query_request"),
            "body": {"query_id": str(query_id)},
        }
        self.outgoing_queue.put(("host/control", pkt))
        print(f"[MQTTHostClient] Queued cancel_query_request id={query_id}")

    def send_command(self, command: str, params: dict = None):
        pkt = {
            "header": self._make_header("command"),
            "body": {"command": command, "params": params or {}}
        }
        self.outgoing_queue.put(("host/control", pkt))
        print(f"[MQTTHostClient] Queued command: {command}")

    def _publish_outgoing(self):
        while not self.outgoing_queue.empty():
            topic, packet = self.outgoing_queue.get()
            try:
                payload = json.dumps(packet, separators=(",", ":"), ensure_ascii=False)
                self.mqtt_client.publish(topic, payload)
                print(f"[MQTTHostClient] Published to {topic}: {payload[:200]}")
            except Exception as e:
                print(f"[MQTTHostClient] Error publishing: {e}")

    def start_background(self):
        """Connect and run publish loop in a background thread (Qt-friendly)."""
        self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
        self.mqtt_client.loop_start()

        if self._publisher_thread and self._publisher_thread.is_alive():
            return

        self._publisher_stop.clear()

        def publisher_loop():
            while not self._publisher_stop.is_set():
                try:
                    self._publish_outgoing()
                except Exception as e:
                    print(f"[MQTTHostClient] Publisher loop error: {e}")
                time.sleep(0.05)

        self._publisher_thread = threading.Thread(target=publisher_loop, daemon=True)
        self._publisher_thread.start()
        print("[MQTTHostClient] Background publisher started.")

    def stop_background(self):
        """Stop background publisher loop (MQTT loop keeps running)."""
        self._publisher_stop.set()

    def start(self):
        """Single entry point — connect once, loop forever."""
        self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
        self.mqtt_client.loop_start()
        print("[MQTTHostClient] Listening for messages...")
        try:
            while True:
                self._publish_outgoing()
                time.sleep(0.05)
        except KeyboardInterrupt:
            print("[MQTTHostClient] Stopped.")


class HostCommandSender:
    """Compatibility shim for older GUI code (e.g., s1_start_app.py).

    This wrapper provides a request/response style API on top of MQTTHostClient
    without consuming/destroying packets from the inbound queue.
    """

    def __init__(
        self,
        mqtt_broker="localhost",
        mqtt_port=1883,
        control_topic="host/control",  # accepted for compatibility; not used
        default_reply_topic=None,       # accepted for compatibility; not used
        request_timeout_sec=10.0,
    ):
        self._timeout = float(request_timeout_sec or 10.0)
        # GUI flow should only discover on button click, not on connect.
        self._client = MQTTHostClient(
            mqtt_broker=mqtt_broker,
            mqtt_port=mqtt_port,
            auto_discover_on_connect=False,
        )
        self._client.start_background()

    def set_on_packet(self, callback):
        """Register a callback invoked for every received MQTT packet."""
        self._client.on_packet = callback

    def send_command(self, cmd: dict, reply_topic=None, timeout: float = None):
        """Send a legacy-style command dict and wait for a response when possible."""
        timeout = self._timeout if timeout is None else float(timeout)
        command = (cmd or {}).get("command")

        if command == "discover":
            self._client.send_discovery()
            resp = self._client.wait_for_message_type("discovery_response", timeout=timeout)
            return resp or {}

        if command == "query":
            query_text = (cmd or {}).get("query", "")
            self._client.send_query_request(query_text)
            # Edge/NUC query response message_type may vary; default to query_response.
            resp = self._client.wait_for_message_type("query_response", timeout=timeout)
            return resp or {}

        # Fallback: send as a generic command (no guaranteed response type).
        self._client.send_command(str(command or "command"), params=(cmd or {}))
        return {}

    def send_query_request(self, query_text: str, query_id: str | None = None):
        """
        Send a query_request packet and return the query_id immediately.
        Use this for async UI flows that render query_response packets via on_packet.
        """
        return self._client.send_query_request(query_text, query_id=query_id)

    def close(self):
        self._client.stop_background()


if __name__ == "__main__":
    NUC_BROKER_IP = "10.148.0.95"
    NUC_BROKER_PORT = 1883

    # Standalone mode: auto-discover is convenient.
    host = MQTTHostClient(mqtt_broker=NUC_BROKER_IP, mqtt_port=NUC_BROKER_PORT, auto_discover_on_connect=True)
    host.start()  # single call — connects once, handles everything