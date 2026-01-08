import queue
import threading
import requests
import paho.mqtt.client as mqtt
import time
import json
import sys
from Waylon_Handler import EdgeHandler  # EdgeHandler already updated to send status

# Status message sent in form {"status": status, "device": device name, "time": datetime}
class EdgeClient:
    def __init__(
        self,
        mqtt_broker="10.148.0.88",
        mqtt_port=1883,
        pi_server_url="http://raspberrypi.local:5000/upload",  # Send images + status
    ):
        # Communication setup
        self.pi_server_url = pi_server_url
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port

        # Thread-safe queue for messages (status/images/queries)
        self.update_queue = queue.Queue()

        # MQTT setup (use callback API v2 to avoid deprecation warning)
        try:
            # Try using VERSION2 (newer API)
            self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except AttributeError:
            # Fallback to VERSION1 if VERSION2 not available
            self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message

        # Handler for local model container, pass status callback
        self.edge_handler = EdgeHandler(on_update_callback=self._on_handler_update)

    # ------------------------------------------------------------
    # HANDLER CALLBACKS (status or inference frames)
    # ------------------------------------------------------------
    def _on_handler_update(self, update_type, data):
        """
        Callback from EdgeHandler whenever there's an update.
        update_type: "status" or "image"
        data: JSON dict for status or image bytes
        """
        if update_type == "status":
            # Forward status to queue for internal processing
            self.update_queue.put(("status", data))

            # Also send it to the Pi server
            self._send_status_to_pi(data)

        elif update_type == "image":
            # Image already in bytes
            self.update_queue.put(("image", data))
            self._send_image_to_pi(data)

    # ------------------------------------------------------------
    # MQTT RECEIVER (Network -> Edge)
    # ------------------------------------------------------------
    def _on_mqtt_connect(self, client, userdata, flags, rc, *args):
        """
        Callback when MQTT client connects to broker.
        Handles both VERSION1 (rc is 4th arg) and VERSION2 (rc is 4th arg, properties may be 5th).
        """
        # rc might be called reason_code in VERSION2, but it's the same position
        reason_code = rc if isinstance(rc, int) else (rc if hasattr(rc, 'value') else 0)
        
        if reason_code == 0 or (hasattr(rc, 'value') and rc.value == 0):
            print(f"[EdgeClient] ✅ Connected to MQTT broker")
            # Subscribe to control/inference topic
            client.subscribe("edge/control")
            print(f"[EdgeClient] ✅ Subscribed to topic: edge/control")
        else:
            print(f"[EdgeClient] ❌ Failed to connect to MQTT broker, return code: {reason_code}")
    
    def _on_mqtt_message(self, client, userdata, msg):
        payload = msg.payload.decode()
        print(f"[EdgeClient] Received MQTT message: {payload}")
        self.update_queue.put(("mqtt", payload))

        # Pass query to handler for VLM inference
        # Handler returns JSON string with image (base64) and results
        result_json_str = self.edge_handler.process_query(payload)

        if result_json_str:
            # Step 4: Check if this is a stop response (cancel_query_status) and exit if so
            try:
                result_data = json.loads(result_json_str)
                
                # Check new packet format (header/body structure)
                if isinstance(result_data, dict) and "header" in result_data:
                    message_type = result_data["header"].get("message_type")
                    if message_type == "cancel_query_status":
                        body = result_data.get("body", {})
                        query_id = body.get("query_id", "unknown")
                        status = body.get("status", "cancelled")
                        print(f"[EdgeClient] ✅ Container stopped (query_id={query_id}, status={status})")
                        print("[EdgeClient] Shutting down application...")
                        # Stop handler gracefully
                        if self.edge_handler:
                            self.edge_handler.stop()
                        # Disconnect MQTT
                        self.mqtt_client.loop_stop()
                        self.mqtt_client.disconnect()
                        # Exit application
                        sys.exit(0)
                # Legacy format check (backward compatibility)
                elif result_data.get("status") == "stopped":
                    print(f"[EdgeClient] ✅ {result_data.get('message', 'Container stopped')}")
                    print("[EdgeClient] Shutting down application...")
                    # Stop handler gracefully
                    if self.edge_handler:
                        self.edge_handler.stop()
                    # Disconnect MQTT
                    self.mqtt_client.loop_stop()
                    self.mqtt_client.disconnect()
                    # Exit application
                    sys.exit(0)
            except (json.JSONDecodeError, KeyError):
                # Not a stop response, continue normally
                pass
            
            print(f"[EdgeClient] Received JSON result from handler ({len(result_json_str)} chars)")
            # Send JSON payload to Pi server
            self._send_json_to_pi(result_json_str)
        else:
            print("[EdgeClient] No results returned from handler.")

    # ------------------------------------------------------------
    # SEND JSON (with image + results)
    # ------------------------------------------------------------
    def _send_json_to_pi(self, json_str):
        """
        Send JSON payload containing image (base64) and VLM results to Pi server.
        
        Args:
            json_str: JSON string containing inference results
        """
        try:
            # Parse JSON to validate it's valid
            json_data = json.loads(json_str)
            
            # Send as JSON payload
            response = requests.post(
                self.pi_server_url,
                json=json_data,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 200:
                print("[EdgeClient] ✅ JSON payload sent successfully to Raspberry Pi.")
            else:
                print(f"[EdgeClient] ⚠️ Failed to send JSON. Status: {response.status_code}")
                print(f"[EdgeClient] Response: {response.text[:200]}")
        except json.JSONDecodeError as e:
            print(f"[EdgeClient] ❌ Invalid JSON format: {e}")
        except Exception as e:
            print(f"[EdgeClient] ❌ Error sending JSON: {e}")
            import traceback
            traceback.print_exc()

    # ------------------------------------------------------------
    # SEND STATUS
    # ------------------------------------------------------------
    def _send_status_to_pi(self, status_json):
        """Send the device status JSON to the Pi server."""
        try:
            response = requests.post(self.pi_server_url, json=status_json, timeout=5)
            if response.status_code == 200:
                print(f"[EdgeClient] ✅ Status sent: {status_json}")
            else:
                print(f"[EdgeClient] ⚠️ Failed to send status. Status code: {response.status_code}")
        except Exception as e:
            print(f"[EdgeClient] ❌ Error sending status: {e}")

    # ------------------------------------------------------------
    # MAIN LOOP
    # ------------------------------------------------------------
    def start(self):
        """Start the EdgeClient — listens for handler updates and MQTT messages."""
        # Connect MQTT
        print(f"[EdgeClient] Connecting to MQTT broker at {self.mqtt_broker}:{self.mqtt_port}...")
        try:
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.mqtt_client.loop_start()
            print("[EdgeClient] MQTT loop started, waiting for connection...")
        except Exception as e:
            print(f"[EdgeClient] ❌ Failed to connect to MQTT broker: {e}")
            print("[EdgeClient] Continuing anyway (will retry)...")

        print("[EdgeClient] Listening for MQTT messages and handler updates...")

        while True:
            try:
                if not self.update_queue.empty():
                    msg_type, content = self.update_queue.get()

                    if msg_type == "status":
                        print(f"[EdgeClient] Handler status updated: {content}")

                    elif msg_type == "image":
                        print("[EdgeClient] Processed image queued for upload.")

                    elif msg_type == "mqtt":
                        print(f"[EdgeClient] Received query: {content}")

                time.sleep(0.05)

            except KeyboardInterrupt:
                print("[EdgeClient] Stopping client.")
                break
            except Exception as e:
                print(f"[EdgeClient] Error: {e}")


# ------------------------------------------------------------
# MAIN ENTRY POINT
# ------------------------------------------------------------
if __name__ == "__main__":
    client = EdgeClient()
    client.start()
