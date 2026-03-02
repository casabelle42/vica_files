#!/opt/miniconda3/envs/handler-script/bin/python

# This is the handler for the Edge Device
import subprocess
import threading
import time
import logging
import psutil
import os
import json
import uuid
from datetime import datetime
import platform
from model_init import ModelService, CFG
import requests

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

    # ------------------------------------------------------------
    # Packet Structure Helpers
    # ------------------------------------------------------------
    def _create_packet(self, message_type: str, body: dict):
        """
        Create a standardized packet with header/body structure.
        
        Args:
            message_type: Type of message (e.g., "query_response", "device_status")
            body: Body content as dictionary
            
        Returns:
            Dictionary with header and body structure
        """
        return {
            "header": {
                "timestamp": datetime.now().isoformat(),
                "source_device": platform.node(),
                "message_type": message_type
            },
            "body": body
        }

    def _parse_incoming_packet(self, packet_str: str):
        """
        Parse incoming packet string and extract message_type and body.
        Handles both new packet format and legacy format for backward compatibility.
        
        Args:
            packet_str: JSON string or plain string
            
        Returns:
            Tuple of (message_type, body_dict, is_legacy_format)
            Returns (None, None, True) if parsing fails
        """
        # Try to parse as JSON
        try:
            packet = json.loads(packet_str)
            
            # Check if it's new packet format (has header/body)
            if isinstance(packet, dict) and "header" in packet and "body" in packet:
                message_type = packet["header"].get("message_type")
                body = packet["body"]
                return message_type, body, False
            
            # Legacy format: check if it's a stop command
            elif isinstance(packet, dict):
                command = packet.get("command", "").lower()
                action = packet.get("action", "").lower()
                if command == "stop" or action == "stop":
                    return "cancel_query_request", {"query_id": packet.get("query_id", str(uuid.uuid4()))}, True
            
            # Legacy format: plain dict, treat as query_request
            return "query_request", {"query": packet_str, "query_id": str(uuid.uuid4())}, True
            
        except json.JSONDecodeError:
            # Not JSON - could be plain string
            # Check if it's a stop command
            if packet_str.strip().lower() == "stop":
                return "cancel_query_request", {"query_id": str(uuid.uuid4())}, True
            
            # Plain string query - treat as query_request
            return "query_request", {"query": packet_str, "query_id": str(uuid.uuid4())}, True

    def _check_container_exists(self, container_name):
        """
        Check if a Docker container exists (running or stopped).
        Returns True if container exists, False otherwise.
        """
        try:
            result = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return container_name in result.stdout.strip().split('\n')
        except Exception as e:
            self.logger.warning(f"Error checking container existence: {e}")
            return False

    def _stop_and_remove_container(self, container_name):
        """
        Stop and remove a Docker container if it exists.
        Uses docker kill if docker stop fails or times out.
        Returns True if successful, False otherwise.
        """
        try:
            # First try graceful stop
            try:
                stop_result = subprocess.run(
                    ["docker", "stop", container_name],
                    capture_output=True,
                    text=True,
                    timeout=5  # Reduced timeout, will use kill if this fails
                )
                if stop_result.returncode == 0:
                    self.logger.info(f"Stopped container: {container_name}")
                elif "No such container" not in stop_result.stderr:
                    # Stop failed, try kill
                    self.logger.warning(f"Stop failed, trying kill: {stop_result.stderr}")
                    raise subprocess.TimeoutExpired("docker stop", 5)
            except subprocess.TimeoutExpired:
                # Stop timed out or failed, use kill for forceful shutdown
                self.logger.info(f"Stop timed out, using kill for container: {container_name}")
                kill_result = subprocess.run(
                    ["docker", "kill", container_name],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if kill_result.returncode == 0:
                    self.logger.info(f"Killed container: {container_name}")
                elif "No such container" not in kill_result.stderr:
                    self.logger.warning(f"Container kill result: {kill_result.stderr}")
            
            # Remove the container (force remove if needed)
            remove_result = subprocess.run(
                ["docker", "rm", "-f", container_name],  # -f flag forces removal
                capture_output=True,
                text=True,
                timeout=5
            )
            if remove_result.returncode == 0:
                self.logger.info(f"Removed container: {container_name}")
                return True
            elif "No such container" not in remove_result.stderr:
                self.logger.warning(f"Container remove result: {remove_result.stderr}")
            return False
        except Exception as e:
            self.logger.error(f"Error stopping/removing container: {e}")
            # Try force remove as last resort
            try:
                subprocess.run(
                    ["docker", "rm", "-f", container_name],
                    capture_output=True,
                    timeout=5
                )
            except:
                pass
            return False

    def _start_model_container(self):
        """
        Start the model container and ModelService (from model_init.py)
        in a background thread, and update readiness when initialized.
        """
        # Step 1: Check if container exists and clean it up before starting
        container_name = CFG.CONTAINER_NAME
        if self._check_container_exists(container_name):
            self.logger.info(f"Found existing container '{container_name}'. Cleaning up...")
            self._stop_and_remove_container(container_name)
            time.sleep(1)  # Give Docker time to clean up
        
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
        """Send periodic status updates every 1.5 seconds using packet structure."""
        def _status_loop():
            while not self._stop_event.is_set():
                try:
                    # Get system metrics
                    cpu_percent = psutil.cpu_percent(interval=None)
                    vm = psutil.virtual_memory()
                    ram_percent = vm.percent
                    
                    # Determine container status
                    if not self._ready:
                        container_status_str = "stopped"
                        current_operation = "idle"
                    elif self.model_service and not self.model_service.paused:
                        container_status_str = "running"
                        current_operation = "processing"
                    else:
                        container_status_str = "running"
                        current_operation = "idle"

                    # Create device_status packet
                    device_status_body = {
                        "name": platform.node(),
                        "cpu": round(cpu_percent, 2),
                        "ram": round(ram_percent, 2),
                        "gpu": 0.0,  # GPU metrics not available via psutil
                        "network_strength": -60,  # Placeholder
                        "isProcessing": (self.model_service and not self.model_service.paused) if self.model_service else False
                    }
                    device_status_packet = self._create_packet("device_status", device_status_body)

                    # Create container_status packet
                    container_status_body = {
                        "status": container_status_str,
                        "uptime_seconds": int(time.time() - (getattr(self, '_start_time', time.time()))),
                        "current_operation": current_operation
                    }
                    container_status_packet = self._create_packet("container_status", container_status_body)

                    # Notify local callback (send both statuses)
                    if self.on_update_callback:
                        self.on_update_callback("status", device_status_packet)
                        self.on_update_callback("status", container_status_packet)

                    # Send to network if URL is provided
                    if self.status_url:
                        try:
                            requests.post(self.status_url, json=device_status_packet, timeout=5)
                            requests.post(self.status_url, json=container_status_packet, timeout=5)
                        except Exception as e:
                            self.logger.warning(f"Failed to send status: {e}")

                except Exception as e:
                    self.logger.warning(f"Status thread error: {e}")

                time.sleep(1.5)

        self._status_thread = threading.Thread(target=_status_loop, daemon=True)
        self._status_thread.start()
        self._start_time = time.time()  # Track start time for uptime calculation

    # ------------------------------------------------------------
    # Model query
    # ------------------------------------------------------------

    def process_query(self, packet_str: str):
        """
        Handle an incoming packet from server.py.
        Parses packet structure and processes based on message_type.
        Returns JSON packet string with standardized header/body structure.
        """
        # Parse incoming packet
        message_type, body, is_legacy = self._parse_incoming_packet(packet_str)
        
        if message_type is None:
            self.logger.warning(f"Failed to parse incoming packet: {packet_str}")
            return None

        self.logger.info(f"Received packet: message_type={message_type}, is_legacy={is_legacy}")

        # Handle cancel_query_request (stop command)
        if message_type == "cancel_query_request":
            query_id = body.get("query_id", str(uuid.uuid4()))
            self.logger.info(f"Received cancel_query_request (query_id={query_id}). Handling container shutdown...")
            
            # Stop and remove the container
            container_name = CFG.CONTAINER_NAME
            if self._check_container_exists(container_name):
                self.logger.info(f"Stopping and removing container: {container_name}")
                self._stop_and_remove_container(container_name)
            else:
                self.logger.info(f"Container {container_name} does not exist.")
            
            # Stop ModelService if it exists
            if self.model_service:
                try:
                    self.model_service.paused = True
                    self.logger.info("ModelService paused.")
                except Exception as e:
                    self.logger.warning(f"Error pausing ModelService: {e}")
            
            # Mark as not ready
            self._ready = False
            
            # Return cancel_query_status packet
            cancel_status_body = {
                "query_id": query_id,
                "status": "cancelled"
            }
            cancel_status_packet = self._create_packet("cancel_query_status", cancel_status_body)
            self.logger.info("Container shutdown complete.")
            return json.dumps(cancel_status_packet)

        # Handle query_request
        if message_type == "query_request":
            query_id = body.get("query_id", str(uuid.uuid4()))
            query_text = body.get("query", "")
            
            if not query_text:
                self.logger.warning("Query request missing query text.")
                return None
            
            if not self._ready or not self.model_service:
                self.logger.warning("Model service not ready yet. Cannot process query.")
                return None

            self.logger.info(f"Processing query_request (query_id={query_id}): {query_text}")
            self.model_service.paused = False  # resume inference

            try:
                # Run VLM inference - returns dict with image and results
                result_dict = self.model_service.run_inference(query_text)
                
                # Check if we got a valid result (dict with keys)
                if not isinstance(result_dict, dict) or not result_dict:
                    self.logger.warning("No valid results from inference.")
                    return None
                
                # Extract image and results from model output
                image_base64 = result_dict.get("image", "")
                results_text = result_dict.get("results", "")
                frame_timestamp = datetime.now().isoformat()
                
                # Get image dimensions (if available) - placeholder for now
                image_width = 0
                image_height = 0
                if image_base64:
                    # Could decode base64 to get dimensions, but for now use placeholder
                    image_width = 640  # Placeholder
                    image_height = 480  # Placeholder
                
                # Create query_response packet
                query_response_body = {
                    "query_id": query_id,
                    "metadata": {
                        "image_width": image_width,
                        "image_height": image_height,
                        "format": "jpeg",
                        "image_base64": image_base64,
                        "chunk_index": 0,
                        "total_chunks": 1
                    },
                    "frame": {
                        "frame_id": 0,
                        "timestamp": frame_timestamp,
                        "detections": [
                            {
                                "label": results_text[:100] if results_text else "no_results",  # VLM results as label
                                "confidence": 1.0,
                                "dets": [results_text] if results_text else []
                            }
                        ]
                    }
                }
                query_response_packet = self._create_packet("query_response", query_response_body)
                
                result_json = json.dumps(query_response_packet)
                self.logger.info(f"Packed inference results into query_response packet ({len(result_json)} chars)")
                
                return result_json
                
            except Exception as e:
                self.logger.error(f"Error processing query: {e}")
                import traceback
                traceback.print_exc()
                # Return error in query_response format
                error_body = {
                    "query_id": query_id,
                    "metadata": {},
                    "frame": {
                        "frame_id": 0,
                        "timestamp": datetime.now().isoformat(),
                        "detections": [
                            {
                                "label": f"Error: {str(e)}",
                                "confidence": 0.0,
                                "dets": []
                            }
                        ]
                    }
                }
                error_packet = self._create_packet("query_response", error_body)
                return json.dumps(error_packet)
        
        # Unknown message type
        self.logger.warning(f"Unknown message_type: {message_type}")
        return None

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


# ------------------------------------------------------------
# Standalone testing
# ------------------------------------------------------------
if __name__ == "__main__":
    handler = EdgeHandler()
    print("Handler initialized. Type queries to test:")

    try:
        while True:
            q = input("> ")
            if q.lower() in ["exit", "quit"]:
                break
            handler.process_query(q)
    except KeyboardInterrupt:
        pass
    finally:
        handler.stop()
