#!/usr/bin/env python3
"""
Host MQTT Client to request Jetson Nano system information via Raspberry Pi.

Protocol (compatible with Edge MQTT client expectations):
  - Host publishes on 'edge/control' a JSON command:
      {
        "command": "get_system_info",
        "request_id": "<uuid>",
        "reply_topic": "edge/system_info"
      }
  - Edge device (Nano) responds on 'edge/system_info' with:
      {
        "type": "system_info",
        "request_id": "<same uuid>",
        "timestamp": <epoch_seconds>,
        "cpu": {"percent": <float>},
        "ram": {"total_mb": <int>, "used_mb": <int>, "percent": <float>},
        "cuda_available": <true|false>
      }
"""

import json
import uuid
import threading
from datetime import datetime

import paho.mqtt.client as mqtt


class HostSystemInfoRequester:
    def __init__(self, mqtt_broker: str, mqtt_port: int = 1883,
                 control_topic: str = "edge/control",
                 reply_topic: str = "edge/system_info",
                 request_timeout_sec: float = 10.0):
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.control_topic = control_topic
        self.reply_topic = reply_topic
        self.request_timeout_sec = request_timeout_sec

        self._client = mqtt.Client()
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

        self._response_event = threading.Event()
        self._response_payload = None
        self._expected_request_id = None

    def _on_connect(self, _client, _userdata, _flags, rc):
        status = "connected" if rc == 0 else f"connect_failed(rc={rc})"
        print(f"[HOST] MQTT {status} to {self.mqtt_broker}:{self.mqtt_port}")
        _client.subscribe(self.reply_topic)
        print(f"[HOST] Subscribed to reply topic: {self.reply_topic}")

    def _on_message(self, _client, _userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
        except Exception:
            print(f"[HOST] Non-JSON message on {msg.topic}: {msg.payload!r}")
            return

        if msg.topic != self.reply_topic:
            return

        if not isinstance(data, dict):
            return

        if data.get("type") != "system_info":
            return

        if self._expected_request_id and data.get("request_id") != self._expected_request_id:
            # Not for this request
            return

        self._response_payload = data
        self._response_event.set()

    def request_system_info(self) -> dict:
        self._client.connect(self.mqtt_broker, self.mqtt_port, 60)
        self._client.loop_start()

        self._expected_request_id = str(uuid.uuid4())
        command = {
            "command": "get_system_info",
            "request_id": self._expected_request_id,
            "reply_topic": self.reply_topic,
        }

        print(f"[HOST] Publishing system info request to {self.control_topic}: {command}")
        self._client.publish(self.control_topic, json.dumps(command))

        got = self._response_event.wait(self.request_timeout_sec)

        self._client.loop_stop()
        self._client.disconnect()

        if not got:
            raise TimeoutError(f"No system_info response within {self.request_timeout_sec}s")

        return self._response_payload or {}


def main():
    print("="*60)
    print("Host to Pi to Nano: System Info Request")
    print("="*60)

    # Set the NUC MQTT broker IP here
    MQTT_BROKER_IP = "10.148.0.95"  

    requester = HostSystemInfoRequester(mqtt_broker=MQTT_BROKER_IP)

    try:
        started_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{started_at}] Requesting Nano system info...")
        response = requester.request_system_info()
        
        print("\n" + "="*60)
        print("[HOST] Successfully received system info from Nano")
        print("="*60)
        
        # Format timestamp
        timestamp = response.get("timestamp", 0)
        if timestamp:
            dt = datetime.fromtimestamp(timestamp)
            print(f"📅 Timestamp: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Format CPU info
        cpu = response.get("cpu", {})
        if cpu:
            print(f"🖥️  CPU Usage: {cpu.get('percent', 0):.2f}%")
        
        # Format RAM info
        ram = response.get("ram", {})
        if ram:
            total_mb = ram.get("total_mb", 0)
            used_mb = ram.get("used_mb", 0)
            percent = ram.get("percent", 0)
            print(f"💾 RAM: {used_mb:,} MB / {total_mb:,} MB ({percent:.2f}% used)")
        
        # Format CUDA info
        cuda_available = response.get("cuda_available", False)
        cuda_status = "Available" if cuda_available else "Not Available"
        print(f"🎮 CUDA: {cuda_status}")
        
        # Print full JSON for reference
        print("\n" + "-"*60)
        print("[HOST] Full JSON Response:")
        print("-"*60)
        print(json.dumps(response, indent=2, sort_keys=True))
        print("="*60 + "\n")
        
    except TimeoutError as te:
        print(f"\n[HOST] ❌ Timeout: {te}")
        print("Make sure:")
        print("  1. Edge client is running on the Nano")
        print("  2. MQTT broker is running on the Pi")
        print("  3. All devices are on the same network")
    except Exception as e:
        print(f"\n[HOST] ❌ Error: {e}")
        import traceback
        traceback.print_exc()


class HostCommandSender:
    """
    Generic MQTT client to send commands to edge device and receive responses.
    """
    def __init__(self, mqtt_broker: str, mqtt_port: int = 1883,
                 control_topic: str = "edge/control",
                 default_reply_topic: str = "edge/handler_response",
                 request_timeout_sec: float = 10.0):
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port
        self.control_topic = control_topic
        self.default_reply_topic = default_reply_topic
        self.request_timeout_sec = request_timeout_sec

        self._client = mqtt.Client()
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

        self._response_event = threading.Event()
        self._response_payload = None
        self._expected_request_id = None
        self._current_reply_topic = None

    def _on_connect(self, _client, _userdata, _flags, rc):
        status = "connected" if rc == 0 else f"connect_failed(rc={rc})"
        print(f"[HOST] MQTT {status} to {self.mqtt_broker}:{self.mqtt_port}")

    def _on_message(self, _client, _userdata, msg):
        try:
            data = json.loads(msg.payload.decode())
        except Exception:
            print(f"[HOST] Non-JSON message on {msg.topic}: {msg.payload!r}")
            return

        print(f"[HOST] Received message on topic: {msg.topic}")
        print(f"[HOST] Message data: {json.dumps(data, indent=2)}")
        print(f"[HOST] Expected topic: {self._current_reply_topic}")
        print(f"[HOST] Expected request_id: {self._expected_request_id}")
        print(f"[HOST] Received request_id: {data.get('request_id')}")

        # Check if this is the reply topic we're waiting for
        if self._current_reply_topic and msg.topic != self._current_reply_topic:
            print(f"[HOST] Topic mismatch, ignoring message")
            return

        if not isinstance(data, dict):
            print(f"[HOST] Message is not a dict, ignoring")
            return

        # Check request_id if we're expecting one
        if self._expected_request_id and data.get("request_id") != self._expected_request_id:
            print(f"[HOST] Request ID mismatch, ignoring message")
            return

        print("[HOST] Message matches! Setting response payload")
        self._response_payload = data
        self._response_event.set()

    def send_command(self, command: dict, reply_topic: str = None, timeout: float = None) -> dict:
        """
        Send a command to the edge device and wait for response.
        
        Args:
            command: Dictionary containing the command to send
            reply_topic: Optional reply topic (defaults to default_reply_topic)
            timeout: Optional timeout in seconds (defaults to request_timeout_sec)
            
        Returns:
            Response dictionary from edge device
        """
        reply_topic = reply_topic or self.default_reply_topic
        timeout = timeout or self.request_timeout_sec
        
        # Reset response state
        self._response_event.clear()
        self._response_payload = None
        
        self._client.connect(self.mqtt_broker, self.mqtt_port, 60)
        self._client.loop_start()
        
        # Wait a moment for connection to establish
        import time
        time.sleep(0.5)
        
        # Subscribe to reply topic
        self._current_reply_topic = reply_topic
        self._client.subscribe(reply_topic)
        print(f"[HOST] Subscribed to reply topic: {reply_topic}")
        
        # Wait a moment for subscription to be active
        time.sleep(0.2)

        # Generate request ID and add to command
        self._expected_request_id = str(uuid.uuid4())
        command_with_metadata = {
            **command,
            "request_id": self._expected_request_id,
            "reply_topic": reply_topic
        }

        print(f"[HOST] Publishing command to {self.control_topic}: {json.dumps(command_with_metadata)}")
        self._client.publish(self.control_topic, json.dumps(command_with_metadata))

        # Wait for response
        got = self._response_event.wait(timeout)

        self._client.loop_stop()
        self._client.disconnect()

        if not got:
            raise TimeoutError(f"No response within {timeout}s")

        return self._response_payload or {}


if __name__ == '__main__':
    main()

