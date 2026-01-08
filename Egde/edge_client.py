import threading
import time
import logging
import psutil
import json
from datetime import datetime
import platform
import os
import sys
import requests
import queue
import paho.mqtt.client as mqtt

# Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Now import local modules - make ModelService optional
try:
    from model_init import ModelService
    MODEL_SERVICE_AVAILABLE = True
except ImportError:
    MODEL_SERVICE_AVAILABLE = False
    ModelService = None
    print("[EdgeClient] Warning: model_init not available. ModelService features disabled.")

try:
    import torch
    CUDA_CHECK_AVAILABLE = True
except ImportError:
    CUDA_CHECK_AVAILABLE = False
    print("[EdgeClient] Warning: PyTorch not available. CUDA check will be False.")

# Make Edge_Handler optional too
try:
    from handler import Edge_Handler
    EDGE_HANDLER_AVAILABLE = True
except ImportError:
    EDGE_HANDLER_AVAILABLE = False
    Edge_Handler = None
    print("[EdgeClient] Warning: handler not available. Edge_Handler features disabled.")

# Import Waylon_Handler and create adapter
try:
    from Waylon_Handler import EdgeHandler as WaylonEdgeHandler
    WAYLON_HANDLER_AVAILABLE = True
except ImportError:
    WAYLON_HANDLER_AVAILABLE = False
    WaylonEdgeHandler = None
    print("[EdgeClient] Warning: Waylon_Handler not available.")

# Adapter function to bridge command dict interface to Waylon_Handler
def waylon_handler_adapter(command_data):
    """
    Adapter function that converts command dict to Waylon_Handler interface.
    Handles "take images" command separately since Waylon_Handler doesn't support it.
    """
    if not WAYLON_HANDLER_AVAILABLE or not WaylonEdgeHandler:
        return {"return": "Waylon_Handler not available", "error": "import failed"}
    
    # Check if command is "take images" - handle separately
    if command_data.get("command") == "take images" or command_data.get("take_images"):
        # Import image capture functionality (same as Edge_Handler_Test)
        try:
            import cv2
            import base64
            import time
            CV2_AVAILABLE = True
        except ImportError:
            CV2_AVAILABLE = False
            return {
                "command": "take images",
                "status": "error",
                "error": "cv2 not available for image capture",
                "num_images": 0,
                "images": [],
                "request_id": command_data.get("request_id", ""),
                "reply_topic": command_data.get("reply_topic", "edge/handler_response")
            }
        
        # Capture images from camera
        images = []
        cap = None
        num_images = 3
        camera_device = "/dev/video0"
        
        try:
            cap = cv2.VideoCapture(camera_device)
            if not cap.isOpened():
                return {
                    "command": "take images",
                    "status": "error",
                    "error": f"Could not open camera {camera_device}",
                    "num_images": 0,
                    "images": [],
                    "request_id": command_data.get("request_id", ""),
                    "reply_topic": command_data.get("reply_topic", "edge/handler_response")
                }
            
            print(f"[Waylon_Handler_Adapter] Camera opened: {camera_device}")
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
            for i in range(num_images):
                ret, frame = cap.read()
                if not ret:
                    print(f"[Waylon_Handler_Adapter] Warning: Failed to capture image {i+1}")
                    continue
                
                success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if success:
                    img_base64 = base64.b64encode(buffer.tobytes()).decode('utf-8')
                    images.append(img_base64)
                    print(f"[Waylon_Handler_Adapter] Captured image {i+1}/{num_images}")
                
                if i < num_images - 1:
                    time.sleep(0.5)
        
        except Exception as e:
            print(f"[Waylon_Handler_Adapter] Error capturing images: {e}")
            import traceback
            traceback.print_exc()
            return {
                "command": "take images",
                "status": "error",
                "error": str(e),
                "num_images": 0,
                "images": [],
                "request_id": command_data.get("request_id", ""),
                "reply_topic": command_data.get("reply_topic", "edge/handler_response")
            }
        finally:
            if cap is not None:
                cap.release()
        
        if images:
            return {
                "command": "take images",
                "status": "success",
                "num_images": len(images),
                "images": images,
                "request_id": command_data.get("request_id", ""),
                "reply_topic": command_data.get("reply_topic", "edge/handler_response")
            }
        else:
            return {
                "command": "take images",
                "status": "error",
                "error": "Failed to capture images",
                "num_images": 0,
                "images": [],
                "request_id": command_data.get("request_id", ""),
                "reply_topic": command_data.get("reply_topic", "edge/handler_response")
            }
    
    # For other commands, try to use Waylon_Handler
    # Extract query from command dict
    query = None
    if isinstance(command_data, dict):
        query = command_data.get("question") or command_data.get("prompt") or command_data.get("query") or command_data.get("text")
        # If command is "run": "model", treat as a query
        if command_data.get("run") == "model":
            query = "model"
    
    if query:
        # Create Waylon_Handler instance if not already created
        # Store it as a module-level variable to persist across calls
        if not hasattr(waylon_handler_adapter, '_handler_instance'):
            print("[Waylon_Handler_Adapter] Creating Waylon_Handler instance...")
            waylon_handler_adapter._handler_instance = WaylonEdgeHandler(
                on_update_callback=None  # No callback needed for command-based usage
            )
            # Give it a moment to initialize
            time.sleep(2)
        
        # Call process_query
        print(f"[Waylon_Handler_Adapter] Processing query: {query}")
        result_json = waylon_handler_adapter._handler_instance.process_query(query)
        
        if result_json:
            # Parse JSON string back to dict
            try:
                result_dict = json.loads(result_json)
                result_dict["request_id"] = command_data.get("request_id", "")
                result_dict["reply_topic"] = command_data.get("reply_topic", "edge/handler_response")
                return result_dict
            except json.JSONDecodeError:
                return {
                    "return": result_json,
                    "request_id": command_data.get("request_id", ""),
                    "reply_topic": command_data.get("reply_topic", "edge/handler_response")
                }
        else:
            return {
                "return": "No response from Waylon_Handler",
                "request_id": command_data.get("request_id", ""),
                "reply_topic": command_data.get("reply_topic", "edge/handler_response")
            }
    
    # Unknown command
    return {
        "return": "unknown command",
        "request_id": command_data.get("request_id", ""),
        "reply_topic": command_data.get("reply_topic", "edge/handler_response")
    }

class EdgeHandler:
    """
    Manages model container lifecycle and inference requests.
    Sends periodic device status updates in JSON to a configured URL.
    """

    def __init__(self, on_update_callback=None, status_url=None):
        """
        Initialize the EdgeHandler, start the model container, and prepare for inference.
        """
        self.logger = self._init_logger()
        self.on_update_callback = on_update_callback
        self.status_url = status_url  # where to POST device status
        self.model_service = None
        self.model_thread = None
        self._stop_event = threading.Event()
        self._ready = False
        self._status_thread = None

        self.logger.info("Initializing EdgeHandler...")
        self._start_model_container()
        self._start_status_thread()

    # ------------------------------------------------------------
    # Setup and Lifecycle
    # ------------------------------------------------------------
    def _init_logger(self):
        logging.basicConfig(
            level=logging.INFO,
            format='[%(asctime)s] [EdgeHandler] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        )
        return logging.getLogger("EdgeHandler")

    def _start_model_container(self):
        """
        Start the model container and ModelService (from model_init.py)
        in a background thread, and update readiness when initialized.
        """
        if not MODEL_SERVICE_AVAILABLE or not ModelService:
            self.logger.warning("ModelService not available, skipping model container startup")
            self._ready = False
            return
            
        def _run_model_service():
            try:
                self.model_service = ModelService(on_status_update=self._on_model_status)
                success = self.model_service.start()

                if success is None or success is True:
                    self._ready = True
                    self.logger.info("ModelService started successfully.")
                else:
                    self._ready = False
                    self.logger.error("ModelService failed to start.")
            except Exception as e:
                self.logger.error(f"Error starting ModelService: {e}")
                self._ready = False

        self.model_thread = threading.Thread(target=_run_model_service, daemon=True)
        self.model_thread.start()
        time.sleep(3)  # allow startup

    # ------------------------------------------------------------
    # Status thread
    # ------------------------------------------------------------
    def _start_status_thread(self):
        """Send periodic status updates every 1.5 seconds."""
        def _status_loop():
            while not self._stop_event.is_set():
                try:
                    # Determine status
                    if not self._ready:
                        status_str = "NOT_READY"
                    elif self.model_service and not self.model_service.paused:
                        status_str = "RUNNING"
                    else:
                        status_str = "READY"

                    # JSON payload
                    payload = {
                        "status": status_str,
                        "device": platform.node(),
                        "time": datetime.now().isoformat(),
                    }

                    # Notify local callback
                    if self.on_update_callback:
                        self.on_update_callback("status", payload)

                    # Send to network if URL is provided
                    if self.status_url:
                        try:
                            requests.post(self.status_url, json=payload, timeout=5)
                        except Exception as e:
                            self.logger.warning(f"Failed to send status: {e}")

                except Exception as e:
                    self.logger.warning(f"Status thread error: {e}")

                time.sleep(1.5)

        self._status_thread = threading.Thread(target=_status_loop, daemon=True)
        self._status_thread.start()

    # ------------------------------------------------------------
    # Model query
    # ------------------------------------------------------------
    def process_query(self, query: str):
        """
        Handle an incoming query message from server.py.
        Calls model service for VLM inference and returns JSON with image and results.
        """
        if not self._ready or not self.model_service:
            self.logger.warning("Model service not ready yet. Cannot process query.")
            return None

        self.logger.info(f"Received query: {query}")
        self.model_service.paused = False  # resume inference

        try:
            # Run VLM inference - returns dict with image and results
            result_dict = self.model_service.run_inference(query)
            
            # Check if we got a valid result (dict with keys)
            if not isinstance(result_dict, dict) or not result_dict:
                self.logger.warning("No valid results from inference.")
                return None
            
            # Add additional metadata to the result
            result_dict["device"] = platform.node()
            result_dict["status"] = "success"
            
            # Convert to JSON string
            result_json = json.dumps(result_dict)
            self.logger.info(f"Packed inference results into JSON ({len(result_json)} chars)")
            
            return result_json
            
        except Exception as e:
            self.logger.error(f"Error processing query: {e}")
            import traceback
            traceback.print_exc()
            # Return error JSON
            error_json = json.dumps({
                "status": "error",
                "error": str(e),
                "query": query,
                "device": platform.node(),
                "timestamp": time.time()
            })
            return error_json

    # ------------------------------------------------------------
    # Model status callback
    # ------------------------------------------------------------
    def _on_model_status(self, update_type, data):
        """Forward model internal status to handler callback if set."""
        if self.on_update_callback:
            self.on_update_callback(update_type, data)

    # ------------------------------------------------------------
    # Shutdown and Cleanup
    # ------------------------------------------------------------
    def stop(self):
        """Stop the model and clean up resources."""
        self.logger.info("Stopping EdgeHandler...")
        self._stop_event.set()

        if self.model_service:
            try:
                self.model_service.paused = True
                self.logger.info("Model paused successfully.")
            except Exception as e:
                self.logger.warning(f"Error while stopping model: {e}")

        if self.model_thread and self.model_thread.is_alive():
            self.model_thread.join(timeout=3)

        if self._status_thread and self._status_thread.is_alive():
            self._status_thread.join(timeout=3)

        self.logger.info("EdgeHandler stopped.")


# ============================================================
# EdgeClient - MQTT Client for Network Communication
# ============================================================

class EdgeClient:
    """
    MQTT client that handles communication with the Raspberry Pi broker.
    Receives commands and routes them to Edge_Handler, sends responses back.
    """
    
    def __init__(self, mqtt_broker="localhost", mqtt_port=1883, server_url="http://localhost:5000/upload"):
        # Communication setup
        self.server_url = server_url
        self.mqtt_broker = mqtt_broker
        self.mqtt_port = mqtt_port

        # Thread-safe queue for messages
        self.update_queue = queue.Queue()

        # State tracking
        self.status = "idle"  # can be "idle" or "processing"

        # MQTT setup
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message

        # Initialize Edge_Handler only if available (optional for simple tests)
        if EDGE_HANDLER_AVAILABLE and Edge_Handler:
            self.edge_handler = Edge_Handler(self._on_handler_update)
        else:
            self.edge_handler = None
            print("[EdgeClient] Edge_Handler not available - only basic MQTT commands will work")

    def _on_handler_update(self, update_type, data):
        """
        Callback from Edge_Handler whenever there's an update.
        update_type: "status" or "image"
        data: message string (status or JSON result) or image bytes
        """
        if update_type == "status":
            # Check if this is a status string or a JSON result dict
            if isinstance(data, dict):
                # This is a JSON result from handler, send it back to server
                if "data" in data or "status" in data:
                    print(f"[EdgeClient] Received JSON result from handler")
                    self._send_json_result_to_server(data)
                    # Update status if it's in the result
                    if "status" in data:
                        self.status = data["status"]
                else:
                    # Regular status update
                    self.status = str(data.get("status", data))
                    self.update_queue.put(("status", data))
            elif isinstance(data, str):
                # Try to parse as JSON to see if it's a result
                try:
                    result_json = json.loads(data)
                    if isinstance(result_json, dict) and "data" in result_json:
                        self._send_json_result_to_server(result_json)
                        if "status" in result_json:
                            self.status = result_json["status"]
                    else:
                        self.status = data
                        self.update_queue.put(("status", data))
                except json.JSONDecodeError:
                    # Not JSON, treat as regular status string
                    self.status = data
                    self.update_queue.put(("status", data))
            else:
                self.status = str(data)
                self.update_queue.put(("status", data))

        elif update_type == "image":
            self.update_queue.put(("image", data))
            self._send_image_to_server(data)

    def _on_mqtt_connect(self, _client, _userdata, _flags, rc):
        """Called when MQTT client connects to broker."""
        if rc == 0:
            print(f"[EdgeClient] ✅ MQTT connected to {self.mqtt_broker}:{self.mqtt_port}")
            _client.subscribe("edge/control")
            print("[EdgeClient] Subscribed to topic: edge/control")
        else:
            print(f"[EdgeClient] ❌ MQTT connection failed with code {rc}")

    def _on_mqtt_message(self, _client, _userdata, msg):
        """
        Handle incoming MQTT messages (if the network sends instructions).
        Validates JSON and routes commands to Handler for processing.
        """
        try:
            payload_str = msg.payload.decode()
            print(f"[EdgeClient] Received MQTT message on {msg.topic}: {payload_str}")
            
            # Try to parse as JSON
            try:
                payload = json.loads(payload_str)
                
                # Handle special system info request (local task, doesn't need handler)
                if isinstance(payload, dict) and payload.get("command") == "get_system_info":
                    self._handle_system_info_request(payload)
                    return
                
                # Validate it's a proper command structure
                if not isinstance(payload, dict):
                    print(f"[EdgeClient] Invalid command: payload is not a dictionary")
                    return
                
                # Check if this is a command for Edge_Handler_Test (has "run" key, "take images", or other handler test commands)
                if "run" in payload or "handler_test" in payload or payload.get("command") == "take images" or "take_images" in payload:
                    # Route to Edge_Handler_Test
                    print(f"[EdgeClient] Routing command to Edge_Handler_Test: {list(payload.keys())}")
                    self._handle_handler_test_command(payload)
                    return
                
                # Check if this is a model-related task (has question/prompt/query)
                has_task = any(key in payload for key in ["question", "prompt", "query", "task_type"])
                
                if has_task:
                    # This is a command for the handler - route it
                    if self.edge_handler:
                        print(f"[EdgeClient] Routing command to handler: {list(payload.keys())}")
                        self.edge_handler.process_command(payload)
                    else:
                        print(f"[EdgeClient] Handler not available, cannot process task command")
                        self.update_queue.put(("mqtt", payload_str))
                else:
                    # Unknown command format
                    print(f"[EdgeClient] Received unknown command format, queueing for manual handling")
                    self.update_queue.put(("mqtt", payload_str))
                    
            except json.JSONDecodeError as e:
                # Not valid JSON
                print(f"[EdgeClient] Invalid JSON in MQTT message: {e}")
                print(f"[EdgeClient] Raw payload: {payload_str[:100]}")
                
        except Exception as e:
            print(f"[EdgeClient] Error processing MQTT message: {e}")
            import traceback
            traceback.print_exc()

    def _send_image_to_server(self, image_bytes):
        """Send image to central server using HTTP."""
        try:
            files = {'file': ('frame.jpg', image_bytes, 'image/jpeg')}
            response = requests.post(self.server_url, files=files, timeout=10)
            if response.status_code == 200:
                print("[EdgeClient] Image uploaded successfully.")
            else:
                print(f"[EdgeClient] Failed to upload image. Status: {response.status_code}")
        except Exception as e:
            print(f"[EdgeClient] Error uploading image: {e}")

    def _send_json_result_to_server(self, result_json):
        """
        Send JSON result back to server via MQTT.
        Publishes to 'edge/results' topic with the JSON result.
        """
        try:
            result_str = json.dumps(result_json, separators=(",", ":"), ensure_ascii=False)
            result_topic = "edge/results"
            
            # Publish result to MQTT
            self.mqtt_client.publish(result_topic, result_str)
            print(f"[EdgeClient] Published JSON result to {result_topic}")
            print(f"[EdgeClient] Result: {result_str[:200]}...")  # Log first 200 chars
            
        except Exception as e:
            print(f"[EdgeClient] Error sending JSON result to server: {e}")
            import traceback
            traceback.print_exc()

    def _get_system_info(self):
        """
        Collect system information: CPU, RAM, time, CUDA availability.
        Returns dict matching the expected format.
        """
        info = {
            "type": "system_info",
            "timestamp": time.time(),
            "cpu": {"percent": 0.0},
            "ram": {"total_mb": 0, "used_mb": 0, "percent": 0.0},
            "cuda_available": False
        }
        
        # CPU usage
        if psutil:
            try:
                cpu_percent = psutil.cpu_percent(interval=0.1)
                info["cpu"]["percent"] = round(cpu_percent, 2)
            except Exception as e:
                print(f"[EdgeClient] Error getting CPU: {e}")
        
        # RAM usage
        if psutil:
            try:
                vm = psutil.virtual_memory()
                info["ram"]["total_mb"] = int(vm.total / (1024 * 1024))
                info["ram"]["used_mb"] = int((vm.total - vm.available) / (1024 * 1024))
                info["ram"]["percent"] = round(vm.percent, 2)
            except Exception as e:
                print(f"[EdgeClient] Error getting RAM: {e}")
        
        # CUDA availability
        if CUDA_CHECK_AVAILABLE:
            try:
                info["cuda_available"] = torch.cuda.is_available()
            except Exception as e:
                print(f"[EdgeClient] Error checking CUDA: {e}")
                info["cuda_available"] = False
        else:
            info["cuda_available"] = False
        
        return info
    
    def _handle_handler_test_command(self, command_payload):
        """
        Handle commands for Waylon_Handler (via adapter).
        Forwards command to Waylon_Handler adapter and sends response back.
        """
        request_id = command_payload.get("request_id", "")
        reply_topic = command_payload.get("reply_topic", "edge/handler_response")
        
        print(f"[EdgeClient] Forwarding command to Waylon_Handler adapter (id: {request_id})")
        
        try:
            # Call Waylon_Handler adapter
            response = waylon_handler_adapter(command_payload)
            
            # Ensure response has request_id and reply_topic
            if isinstance(response, dict):
                response["request_id"] = request_id
                response["reply_topic"] = reply_topic
                
                # Publish response
                response_json = json.dumps(response, separators=(',', ':'))
                result = self.mqtt_client.publish(reply_topic, response_json, qos=0)
                
                if hasattr(result, 'rc') and result.rc == 0:
                    print(f"[EdgeClient] ✅ Published Waylon_Handler response to {reply_topic}")
                    print(f"[EdgeClient] Response preview: {response_json[:200]}...")
                else:
                    print(f"[EdgeClient] ⚠️  Publish result: {result}")
            else:
                print(f"[EdgeClient] ⚠️  Waylon_Handler adapter returned non-dict response: {response}")
                
        except Exception as e:
            print(f"[EdgeClient] ❌ Error handling handler test command: {e}")
            import traceback
            traceback.print_exc()
            
            # Send error response
            error_response = {
                "return": f"error: {str(e)}",
                "request_id": request_id,
                "reply_topic": reply_topic
            }
            try:
                self.mqtt_client.publish(reply_topic, json.dumps(error_response), qos=0)
            except Exception:
                pass
    
    def _handle_system_info_request(self, command_payload):
        """
        Handle 'get_system_info' command from host.
        Collects system info and publishes response on the reply topic.
        """
        request_id = command_payload.get("request_id", "")
        reply_topic = command_payload.get("reply_topic", "edge/system_info")
        
        print(f"[EdgeClient] Received system info request (id: {request_id})")
        
        # Collect system info
        system_info = self._get_system_info()
        system_info["request_id"] = request_id
        
        # Publish response
        try:
            # Ensure proper JSON formatting
            response_json = json.dumps(system_info, separators=(',', ':'))
            result = self.mqtt_client.publish(reply_topic, response_json, qos=0)
            
            # Check publish result (result.rc == 0 means success)
            if hasattr(result, 'rc') and result.rc == 0:
                print(f"[EdgeClient] ✅ Published system info to {reply_topic}")
                print(f"[EdgeClient] Response preview: {json.dumps(system_info, indent=2)[:200]}...")
            else:
                print(f"[EdgeClient] ⚠️  Publish result: {result}")
        except Exception as e:
            print(f"[EdgeClient] ❌ Error publishing system info: {e}")
            import traceback
            traceback.print_exc()
    
    def get_status(self):
        """Return current device status (idle or processing)."""
        return self.status

    def start(self):
        """
        Start the EdgeClient — listens for handler updates and MQTT messages.
        """
        # Connect MQTT (subscription happens in on_connect callback)
        print(f"[EdgeClient] Connecting to MQTT broker at {self.mqtt_broker}:{self.mqtt_port}...")
        try:
            self.mqtt_client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.mqtt_client.loop_start()
        except Exception as e:
            print(f"[EdgeClient] ❌ Failed to connect to MQTT broker: {e}")
            print(f"[EdgeClient] Make sure the MQTT broker is running on {self.mqtt_broker}")
            return

        print("[EdgeClient] Listening for updates...")

        while True:
            try:
                # process queue items if any
                if not self.update_queue.empty():
                    msg_type, content = self.update_queue.get()

                    if msg_type == "status":
                        print(f"[EdgeClient] Handler status updated: {content}")
                        # Log completion when status returns to idle
                        if isinstance(content, dict) and content.get("status") == "idle":
                            print("[EdgeClient] ✓ Task completed, ready for next command")
                        elif isinstance(content, str) and content == "idle":
                            print("[EdgeClient] ✓ Task completed, ready for next command")

                    elif msg_type == "image":
                        print("[EdgeClient] Processed image received.")

                    elif msg_type == "mqtt":
                        print(f"[EdgeClient] Network message (queued): {content}")

                time.sleep(0.05)  # lightweight wait loop

            except KeyboardInterrupt:
                print("[EdgeClient] Stopping client.")
                break
            except Exception as e:
                print(f"[EdgeClient] Error: {e}")


# ------------------------------------------------------------
# Standalone testing
# ------------------------------------------------------------
if __name__ == "__main__":
    # Set the Raspberry Pi MQTT broker IP here
    MQTT_BROKER_IP = "10.148.0.94"  # ← update to your Pi's broker IP (same as host_client.py)
    
    print("="*60)
    print("Edge Client - System Info Responder & MQTT Handler")
    print("="*60)
    print(f"Connecting to MQTT broker: {MQTT_BROKER_IP}")
    print("="*60)
    
    client = EdgeClient(mqtt_broker=MQTT_BROKER_IP)
    client.start()
