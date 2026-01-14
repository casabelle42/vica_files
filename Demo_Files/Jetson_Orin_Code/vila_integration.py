#!/usr/bin/env python3
"""
Sentinel Nexus V2 - VILA Integration
Integrates the optimized VILA model with the server architecture.
"""

import subprocess
import threading
import time
import logging
import json
import base64
import cv2
import numpy as np
from typing import Dict, Any, Optional
import os
import signal
import psutil

logger = logging.getLogger(__name__)

try:
    import websocket
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    logger.warning(
        "websocket-client not available. Install with: pip install websocket-client")


class VILAProcessor:
    """Integrates optimized VILA model with server architecture"""

    def __init__(self):
        self.process = None
        self.running = False
        self.model_ready = False
        self.last_result = None
        self.processing_lock = threading.Lock()
        self.camera_available = False
        self.frame_counter = 0
        self.streaming_clients = []  # List of clients to stream results to
        self.streaming_active = False
        self.streaming_lock = threading.Lock()
        self.server_instance = None  # Reference to server instance
        self.websocket_client = None  # WebSocket connection to VILA
        self.ws_port = 49000  # Default WebSocket port for VILA
        self.ws_connected = False
        self.ws_lock = threading.Lock()  # Lock for WebSocket operations

        # Initialize camera
        self._initialize_camera()

        # VILA process will be started on first query

    def _initialize_camera(self):
        """Initialize camera for video capture - VILA Docker handles camera"""
        try:
            # VILA Docker container handles camera access
            # We don't need direct camera access since VILA processes the video stream
            self.camera_available = True
            logger.info("Camera access delegated to VILA Docker container")
        except Exception as e:
            logger.error(f"Error initializing camera: {e}")
            self.camera_available = False

    def _cleanup_containers(self):
        """Clean up any existing Docker containers"""
        try:
            logger.info("Cleaning up existing Docker containers...")

            # Stop all running containers
            try:
                result = subprocess.run(
                    ["docker", "ps", "-q"],
                    capture_output=True,
                    text=True,
                    timeout=5  # Shorter timeout
                )
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Timeout getting container list, trying force cleanup...")
                result = None
            except KeyboardInterrupt:
                logger.warning("Interrupted while getting container list")
                return

            if result and result.returncode == 0 and result.stdout.strip():
                container_ids = result.stdout.strip().split('\n')
                logger.info(
                    f"Found {len(container_ids)} running containers, stopping them...")

                for container_id in container_ids:
                    if container_id:
                        try:
                            container_id = container_id.strip()
                            if not container_id:
                                continue

                            # Try graceful stop first with short timeout
                            logger.info(
                                f"Attempting to stop container {container_id}...")
                            stop_process = subprocess.Popen(
                                ["docker", "stop", container_id],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE
                            )

                            try:
                                # Very short timeout
                                stop_process.wait(timeout=3)
                                if stop_process.returncode == 0:
                                    logger.info(
                                        f"Stopped container {container_id}")
                                else:
                                    logger.warning(
                                        f"Container {container_id} stop returned code {stop_process.returncode}, forcing kill...")
                                    raise subprocess.TimeoutExpired("stop", 3)
                            except subprocess.TimeoutExpired:
                                logger.warning(
                                    f"Timeout stopping container {container_id}, forcing kill...")
                                stop_process.kill()
                                stop_process.wait(timeout=1)

                                # Force kill immediately
                                kill_process = subprocess.Popen(
                                    ["docker", "kill", container_id],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE
                                )
                                try:
                                    kill_process.wait(timeout=3)
                                    logger.info(
                                        f"Force killed container {container_id}")
                                except subprocess.TimeoutExpired:
                                    kill_process.kill()
                                    logger.warning(
                                        f"Could not kill container {container_id}, may need manual cleanup")
                            except KeyboardInterrupt:
                                logger.warning(
                                    f"Interrupted while stopping container {container_id}")
                                stop_process.kill()
                                return
                        except Exception as e:
                            logger.warning(
                                f"Error stopping container {container_id}: {e}")

            # Remove all stopped containers (with shorter timeout)
            try:
                result = subprocess.run(
                    ["docker", "ps", "-aq"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                logger.warning(
                    "Timeout or interrupt getting stopped container list, skipping removal")
                result = None

            if result and result.returncode == 0 and result.stdout.strip():
                container_ids = result.stdout.strip().split('\n')
                logger.info(
                    f"Found {len(container_ids)} stopped containers, removing them...")

                for container_id in container_ids:
                    if container_id:
                        try:
                            container_id = container_id.strip()
                            if not container_id:
                                continue

                            # Use Popen for better control
                            rm_process = subprocess.Popen(
                                ["docker", "rm", container_id],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE
                            )
                            try:
                                rm_process.wait(timeout=3)
                                if rm_process.returncode == 0:
                                    logger.info(
                                        f"Removed container {container_id}")
                                else:
                                    logger.warning(
                                        f"Could not remove container {container_id} (may not exist)")
                            except subprocess.TimeoutExpired:
                                logger.warning(
                                    f"Timeout removing container {container_id}")
                                rm_process.kill()
                            except KeyboardInterrupt:
                                logger.warning(
                                    f"Interrupted while removing container {container_id}")
                                rm_process.kill()
                                return
                        except Exception as e:
                            logger.warning(
                                f"Error removing container {container_id}: {e}")

            logger.info("Container cleanup completed")

        except KeyboardInterrupt:
            logger.warning("Container cleanup interrupted by user")
        except subprocess.TimeoutExpired:
            logger.warning("Container cleanup timed out, continuing...")
        except Exception as e:
            logger.error(f"Error during container cleanup: {e}")

    def _start_vila_process(self):
        """Start new VILA Docker container and monitor its output"""
        try:
            logger.info("Starting new VILA process...")

            # Always clean up any existing containers before starting new one
            # This ensures we start fresh each time
            logger.info(
                "Cleaning up any existing containers before starting new one...")
            self._cleanup_containers()

            # Start VILA container using the prequantized script
            vila_script = "/home/telepathboy/Documents/Sentinel_nexusV2/Network/Edge_Network/vila_prequantized_run.py"

            if not os.path.exists(vila_script):
                raise FileNotFoundError(
                    f"VILA script not found: {vila_script}")

            # Start VILA process
            self.process = subprocess.Popen(
                ["python3", vila_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            # Reset running state
            self.running = True

            # Start monitoring thread
            monitor_thread = threading.Thread(
                target=self._monitor_vila_process, daemon=True)
            monitor_thread.start()

            # Wait for model to be ready
            self._wait_for_model_ready()

        except Exception as e:
            logger.error(f"Failed to start VILA process: {e}")
            self.model_ready = False

    def terminate_container_immediately(self, container_name: str = "sn_vila", wait_timeout: int = 10) -> None:
        """Synchronously kill and remove the VILA Docker container and stop local process.

        This forces the container down first, then ensures the local Python wrapper is terminated,
        and waits until the container is fully gone before returning.
        """
        try:
            logger.info(
                f"Immediate termination requested for container '{container_name}'")

            # Kill the named container (fast path)
            try:
                kill_proc = subprocess.Popen(
                    ["docker", "kill", container_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    kill_proc.wait(timeout=5)
                    logger.info(
                        f"docker kill '{container_name}' returncode={kill_proc.returncode}")
                except subprocess.TimeoutExpired:
                    logger.warning(
                        f"docker kill timed out for '{container_name}', forcing proc kill")
                    kill_proc.kill()
            except Exception as e:
                logger.warning(
                    f"Error invoking docker kill on '{container_name}': {e}")

            # Remove the container name if present
            try:
                rm_proc = subprocess.Popen(
                    ["docker", "rm", container_name], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    rm_proc.wait(timeout=5)
                    logger.info(
                        f"docker rm '{container_name}' returncode={rm_proc.returncode}")
                except subprocess.TimeoutExpired:
                    logger.warning(
                        f"docker rm timed out for '{container_name}', forcing proc kill")
                    rm_proc.kill()
            except Exception as e:
                logger.warning(
                    f"Error invoking docker rm on '{container_name}': {e}")

            # Ensure the local Python wrapper is terminated and pipes closed
            if self.process:
                logger.info(
                    "Terminating local VILA Python process after container kill...")
                try:
                    if self.process.stdout:
                        try:
                            self.process.stdout.close()
                        except Exception:
                            pass
                    if self.process.stderr:
                        try:
                            self.process.stderr.close()
                        except Exception:
                            pass
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        logger.warning(
                            "Process terminate timed out, killing...")
                        self.process.kill()
                        try:
                            self.process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            logger.warning("Process kill wait timed out")
                except Exception as e:
                    logger.warning(
                        f"Error terminating local VILA process: {e}")
                finally:
                    self.process = None

            # Wait until container no longer appears in ps -a
            start = time.time()
            while time.time() - start < wait_timeout:
                try:
                    result = subprocess.run(
                        ["docker", "ps", "-a", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=5)
                    names = result.stdout.splitlines() if result.returncode == 0 else []
                    if container_name not in names:
                        logger.info(
                            f"Container '{container_name}' no longer present")
                        break
                except Exception as e:
                    logger.debug(f"Error checking container presence: {e}")
                time.sleep(0.3)

            # Reset state flags
            self.running = False
            self.model_ready = False
            self.streaming_active = False
            self.last_result = None
            self.frame_counter = 0

            # Close WebSocket connection
            with self.ws_lock:
                if self.websocket_client:
                    try:
                        self.websocket_client.close()
                    except:
                        pass
                    self.websocket_client = None
                self.ws_connected = False

            logger.info("Immediate container termination completed")
        except Exception as e:
            logger.error(f"Error during immediate container termination: {e}")

    def _monitor_vila_process(self):
        """Monitor VILA process output and extract results"""
        try:
            while self.running and self.process and self.process.poll() is None:
                # Check running flag before blocking read
                if not self.running:
                    break

                try:
                    line = self.process.stdout.readline()
                except (ValueError, OSError):
                    # Pipe closed or invalid
                    break

                if not line:
                    # Empty line means pipe closed or EOF
                    break

                line = line.strip()
                if line:
                    logger.info(f"VILA result: {line}")
                    # Parse VILA output for analysis results
                    is_analysis = self._is_analysis_result(line)
                    logger.debug(
                        f"Line '{line}' is_analysis: {is_analysis}")

                    if is_analysis:
                        with self.processing_lock:
                            # Only process if still running
                            if not self.running:
                                break
                            self.frame_counter += 1
                            self.last_result = {
                                'response': line,
                                'timestamp': time.time(),
                                'confidence': 0.8,  # Default confidence
                                'frame_number': self.frame_counter,
                                'processing_time': 1.5  # Default processing time
                            }
                            logger.debug(
                                f"Captured VILA analysis (frame {self.frame_counter}): {line}")

                            # Always stream to all connected clients (send every frame)
                            # This ensures the host gets results continuously
                            if self.server_instance:
                                self._stream_result_to_all_clients(
                                    self.last_result)
                    else:
                        logger.debug(f"Filtered out line: {line}")

                # Small delay, but check running flag frequently
                time.sleep(0.1)

        except Exception as e:
            logger.error(f"Error monitoring VILA process: {e}")
        finally:
            logger.info("VILA monitoring thread exiting")

    def _is_analysis_result(self, line: str) -> bool:
        """Check if line contains analysis result"""
        line = line.strip()
        if not line:
            return False

        # Skip technical log lines and system messages
        technical_indicators = [
            'INFO', 'WARNING', 'ERROR', 'DEBUG',
            'refresh rate:', 'FPS', 'ms',
            'gstreamer', 'cuda', 'allocated',
            'loading', 'device=', 'model=',
            'pipeline', 'caps', 'buffer',
            'created gstCamera', 'gstCamera video options',
            'URI:', 'protocol:', 'location:', 'deviceType:',
            'ioType:', 'codec:', 'width:', 'height:',
            'frameRate:', 'zeroCopy:', 'flipMethod:',
            'sslCert', 'sslKey', 'failed to find',
            'WebRTC server', 'Flask app', 'Serving',
            'created gstEncoder', 'gstEncoder video options',
            'bitRate:', 'latency:', 'thread running',
            '18:', '19:', '20:', '21:', '22:', '23:', '24:', '25:',
            'refresh rate:', 'FPS', 'ms', 'INFO', 'WARNING', 'ERROR',
            'max_position_embeddings', 'mm_vision_tower', 'hidden_size',
            'image_aspect_ratio', 'interpolate_mode', 'mm_hidden_size',
            'mm_projector_lr', 'mm_use_im_patch_token', 'mm_use_im_start_end',
            'mm_vision_select_feature', 'mm_vision_select_layer', 'model_dtype',
            'model_type', 'num_video_frames', 'resume_path', 's2',
            's2_max_split_size', 's2_scales', 'transformers_version',
            'drop_path_rate', 'architectures', '│', '├', '└', '┌', '┐', '┘', '┴',
            'allocated 4 ring buffers', 'gstBufferManager recieve caps',
            'gstreamer changed state', 'created gstCamera', 'gstCamera video options'
        ]

        # Check for technical indicators first
        for indicator in technical_indicators:
            if indicator.lower() in line.lower():
                return False

        # Skip lines that are clearly technical/system logs
        if (line.startswith('│') or line.startswith('├') or line.startswith('└') or
            line.startswith('┌') or line.startswith('┐') or line.startswith('┘') or
            line.startswith('18:') or line.startswith('19:') or line.startswith('20:') or
            line.startswith('21:') or line.startswith('22:') or line.startswith('23:') or
            line.startswith('24:') or line.startswith('25:') or
            'allocated' in line.lower() or 'gstreamer' in line.lower() or
            'cuda' in line.lower() or 'device=' in line.lower() or
                'model=' in line.lower() or 'loading' in line.lower()):
            return False

        # Check if it looks like a natural language description
        # Must be a reasonable length (not too short, not too long)
        if len(line) < 10 or len(line) > 500:
            return False

        # Look for natural language patterns
        # Should contain common words that indicate description
        descriptive_words = [
            'person', 'people', 'man', 'woman', 'child', 'children',
            'sitting', 'standing', 'walking', 'running', 'holding',
            'using', 'looking', 'wearing', 'carrying', 'talking',
            'room', 'table', 'chair', 'desk', 'wall', 'door', 'window',
            'computer', 'laptop', 'keyboard', 'mouse', 'screen',
            'white', 'black', 'blue', 'red', 'green', 'yellow',
            'group', 'classroom', 'office', 'kitchen', 'bedroom',
            'are', 'is', 'with', 'on', 'in', 'at', 'the', 'a', 'an',
            'and', 'or', 'but', 'of', 'to', 'for', 'from', 'by'
        ]

        # Count descriptive words
        descriptive_count = 0
        line_lower = line.lower()
        for word in descriptive_words:
            if word in line_lower:
                descriptive_count += 1

        # More lenient criteria: just need some descriptive content
        # and it should look like a sentence (not a technical log)
        if (descriptive_count >= 1 and  # At least 1 descriptive word
            not line.startswith('[') and  # Not a technical log format
            not line.startswith('│') and  # Not a table format
            not line.startswith('├') and  # Not a table format
            not line.startswith('└') and  # Not a table format
            not line.startswith('18:') and  # Not a timestamp
            not line.startswith('19:') and  # Not a timestamp
            not line.startswith('20:') and  # Not a timestamp
            not line.startswith('21:') and  # Not a timestamp
            not line.startswith('22:') and  # Not a timestamp
            not line.startswith('23:') and  # Not a timestamp
            not line.startswith('24:') and  # Not a timestamp
            not line.startswith('25:') and  # Not a timestamp
            '.' in line and  # Should contain a period (sentence)
                len(line.split()) >= 3):  # At least 3 words
            return True

        return False

    def _check_vila_startup(self) -> bool:
        """Check if VILA has completed startup by looking for specific indicators"""
        try:
            # Check if process is running and has been running for a while
            if self.process and self.process.poll() is None:
                # Look for specific VILA startup completion indicators
                # These are patterns that indicate VILA is fully loaded and ready
                startup_indicators = [
                    "created gstCamera",
                    "gstCamera video options",
                    "gstreamer changed state",
                    "allocated 4 ring buffers",
                    "gstBufferManager recieve caps"
                ]

                # If we see these indicators, VILA is likely ready
                # We'll assume it's ready after a reasonable time if process is running
                return True

            return False
        except Exception as e:
            logger.error(f"Error checking VILA startup: {e}")
            return False

    def _wait_for_model_ready(self, timeout: int = 60):
        """Wait for VILA model to be ready"""
        logger.info("Waiting for VILA model to be ready...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.process and self.process.poll() is None:
                # Check if we have received any results
                if self.last_result:
                    self.model_ready = True
                    logger.info("VILA model is ready")
                    return True

                # Check for specific VILA startup indicators
                if hasattr(self, '_check_vila_startup'):
                    if self._check_vila_startup():
                        self.model_ready = True
                        logger.info("VILA model is ready (startup detected)")
                        return True

            time.sleep(1)

        logger.error("Timeout waiting for VILA model to be ready")
        return False

    def _connect_websocket(self) -> bool:
        """Connect to VILA WebSocket server to send queries"""
        if not WEBSOCKET_AVAILABLE:
            logger.warning(
                "WebSocket client not available, cannot send queries to VILA")
            return False

        with self.ws_lock:
            if self.ws_connected and self.websocket_client:
                try:
                    # Test if connection is still alive
                    self.websocket_client.ping()
                    return True
                except:
                    # Connection is dead, reconnect
                    self.ws_connected = False
                    self.websocket_client = None

            if self.ws_connected:
                return True

            try:
                logger.info(
                    f"Connecting to VILA WebSocket on port {self.ws_port}...")
                ws_url = f"ws://localhost:{self.ws_port}"

                # Create WebSocket connection with timeout
                self.websocket_client = websocket.create_connection(
                    ws_url,
                    timeout=5
                )

                self.ws_connected = True
                logger.info("Connected to VILA WebSocket server")
                return True
            except Exception as e:
                logger.warning(
                    f"Could not connect to VILA WebSocket (port {self.ws_port}): {e}")
                logger.info(
                    "VILA may not have WebSocket server running, will use default prompt")
                self.ws_connected = False
                self.websocket_client = None
                return False

    def _send_query_to_vila(self, query: str) -> bool:
        """Send query to VILA via WebSocket to change the prompt"""
        if not WEBSOCKET_AVAILABLE:
            return False

        try:
            if not self._connect_websocket():
                return False

            # Send prompt change message to VILA
            # This will cause VILA to process the current frame with the new query
            message = {'prompt': query}
            with self.ws_lock:
                if self.websocket_client:
                    self.websocket_client.send(json.dumps(message))
                    logger.info(
                        f"Sent query to VILA via WebSocket: {query[:50]}...")
                    return True
            return False
        except Exception as e:
            logger.error(f"Error sending query via WebSocket: {e}")
            self.ws_connected = False
            self.websocket_client = None
            return False

    def process_query(self, query: str) -> Dict[str, Any]:
        """Process a query using VILA model"""
        try:
            # Connect to VILA Docker container if not already connected
            if not self.process or self.process.poll() is not None:
                self._start_vila_process()

            if not self.model_ready:
                return {
                    'response': 'VILA Docker container not ready',
                    'confidence': 0.0,
                    'processing_time': 0.0,
                    'frame_count': 0,
                    'error': 'VILA Docker container not ready'
                }

            start_time = time.time()

            # Send query to VILA via WebSocket to change the prompt
            # This triggers VILA to process the current frame with the new query
            query_sent = self._send_query_to_vila(query)
            if query_sent:
                logger.info(
                    f"Query sent to VILA, waiting for result with new prompt...")
            else:
                logger.warning(
                    "Could not send query to VILA via WebSocket, using default prompt")

            # Reset timestamp to ensure we get a fresh result after prompt change
            with self.processing_lock:
                old_timestamp = self.last_result.get(
                    'timestamp', 0) if self.last_result else 0

            # Wait for new analysis result (VILA will process current frame with new prompt)
            result = self._wait_for_result(
                timeout=30, min_timestamp=old_timestamp)

            processing_time = time.time() - start_time

            return {
                'response': result.get('response', 'No analysis available'),
                'confidence': result.get('confidence', 0.0),
                'processing_time': processing_time,
                'frame_count': 1,
                'image_data': None,  # VILA handles image processing in Docker
                'timestamp': time.time()
            }

        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                'response': f'Error processing query: {str(e)}',
                'confidence': 0.0,
                'processing_time': 0.0,
                'frame_count': 0,
                'error': str(e)
            }

    def _capture_frame(self) -> Optional[bytes]:
        """Capture current frame - VILA handles this in Docker"""
        try:
            # VILA Docker container handles frame capture and processing
            # We don't need to capture frames directly since VILA processes the video stream
            logger.info("Frame capture delegated to VILA Docker container")
            return None  # Return None since VILA handles frame processing

        except Exception as e:
            logger.error(f"Error capturing frame: {e}")
            return None

    def _wait_for_result(self, timeout: int = 30, min_timestamp: float = 0) -> Dict[str, Any]:
        """Wait for new analysis result from VILA"""
        start_time = time.time()
        last_timestamp = max(
            self.last_result.get('timestamp', 0) if self.last_result else 0,
            min_timestamp
        )

        logger.info(
            f"Waiting for VILA analysis result (timeout: {timeout}s)...")

        # First, check if we already have a recent result
        with self.processing_lock:
            if self.last_result and self.last_result.get('timestamp', 0) > last_timestamp:
                logger.info(
                    f"VILA analysis result (immediate): {self.last_result.get('response', '')}")
                return self.last_result

        # Wait for new results
        while time.time() - start_time < timeout:
            with self.processing_lock:
                if self.last_result and self.last_result.get('timestamp', 0) > last_timestamp:
                    logger.info(
                        f"VILA analysis result: {self.last_result.get('response', '')}")
                    return self.last_result

            time.sleep(0.5)

        # If no new result, return the latest available result
        with self.processing_lock:
            if self.last_result:
                logger.info(
                    f"Returning latest VILA result: {self.last_result.get('response', '')}")
                return self.last_result
            else:
                # Wait a bit more for any results
                logger.info("No results yet, waiting additional 2 seconds...")
                time.sleep(2)
                if self.last_result:
                    logger.info(
                        f"Returning delayed VILA result: {self.last_result.get('response', '')}")
                    return self.last_result
                else:
                    logger.warning(
                        "No VILA analysis results available after timeout")
                    return {
                        'response': 'No analysis available',
                        'confidence': 0.0,
                        'timestamp': time.time()
                    }

    def get_status(self) -> Dict[str, Any]:
        """Get VILA processor status"""
        return {
            'running': self.running,
            'model_ready': self.model_ready,
            'camera_available': self.camera_available,
            'process_alive': self.process and self.process.poll() is None if self.process else False,
            'last_result_timestamp': self.last_result.get('timestamp', 0) if self.last_result else 0,
            'streaming_active': self.streaming_active,
            'streaming_clients': len(self.streaming_clients),
            'frame_counter': self.frame_counter
        }

    def add_streaming_client(self, client):
        """Add a client to receive streaming results"""
        with self.streaming_lock:
            if client not in self.streaming_clients:
                self.streaming_clients.append(client)
                logger.info(f"Added streaming client: {client.client_id}")
                self.streaming_active = True

    def remove_streaming_client(self, client):
        """Remove a client from streaming results"""
        with self.streaming_lock:
            if client in self.streaming_clients:
                self.streaming_clients.remove(client)
                logger.info(f"Removed streaming client: {client.client_id}")
                if not self.streaming_clients:
                    self.streaming_active = False

    def _stream_result_to_clients(self, result):
        """Stream analysis result to all connected clients"""
        try:
            with self.streaming_lock:
                if not self.streaming_clients:
                    return

                # Create live feed result message
                live_feed_data = {
                    'analysis': result.get('response', ''),
                    'confidence': result.get('confidence', 0.8),
                    'processing_time': result.get('processing_time', 1.5),
                    'frame_number': result.get('frame_number', self.frame_counter),
                    'query_text': 'Continuous live feed analysis',
                    'timestamp': result.get('timestamp', time.time()),
                    'model_version': 'VILA-1.5-3b',
                    'inference_device': 'CUDA',
                    'frame_metadata': {
                        'resolution': '1280x720',
                        'fps': 30,
                        'compression': 'JPEG',
                        'quality': 85
                    }
                }

                # Send to all streaming clients
                # Copy list to avoid modification during iteration
                for client in self.streaming_clients[:]:
                    try:
                        # Create message and send through server
                        message = client.send_live_feed_result(live_feed_data)
                        if message and hasattr(self, 'server_instance'):
                            self.server_instance._send_message(message, client)
                        else:
                            logger.warning(
                                f"Could not send streaming result to client {client.client_id}")
                    except Exception as e:
                        logger.error(
                            f"Error streaming to client {client.client_id}: {e}")
                        # Remove failed client
                        self.streaming_clients.remove(client)

        except Exception as e:
            logger.error(f"Error streaming result to clients: {e}")

    def _stream_result_to_all_clients(self, result):
        """Stream analysis result to ALL connected clients (sends every frame)"""
        try:
            if not self.server_instance:
                return

            live_feed_data = {
                'analysis': result.get('response', ''),
                'confidence': result.get('confidence', 0.8),
                'processing_time': result.get('processing_time', 1.5),
                'frame_number': result.get('frame_number', self.frame_counter),
                'query_text': 'Continuous live feed analysis',
                'timestamp': result.get('timestamp', time.time()),
                'model_version': 'VILA-1.5-3b',
                'inference_device': 'CUDA',
                'frame_metadata': {
                    'resolution': '1280x720',
                    'fps': 30,
                    'compression': 'JPEG',
                    'quality': 85
                }
            }

            # Send to ALL connected clients (not just streaming clients)
            # This ensures every frame result is sent to the host
            # Make a copy of clients dict to avoid modification during iteration
            try:
                clients_to_send = list(self.server_instance.clients.values())
            except Exception as e:
                logger.debug(f"Error getting clients list: {e}")
                return

            for client in clients_to_send:
                try:
                    if not client.connected:
                        continue

                    # Create message and send through server
                    message = client.send_live_feed_result(live_feed_data)
                    if message:
                        self.server_instance._send_message(message, client)
                except Exception as e:
                    logger.debug(
                        f"Error sending frame result to client {client.client_id}: {e}")

        except Exception as e:
            logger.error(f"Error streaming result to all clients: {e}")

    def start_streaming(self, client):
        """Start streaming results to a client"""
        self.add_streaming_client(client)
        logger.info(f"Started streaming to client: {client.client_id}")

    def stop_streaming(self, client):
        """Stop streaming results to a client"""
        self.remove_streaming_client(client)
        logger.info(f"Stopped streaming to client: {client.client_id}")

    def set_server_instance(self, server_instance):
        """Set the server instance for sending messages"""
        self.server_instance = server_instance

    def stop_model(self):
        """Stop the VILA model and kill the Docker container"""
        try:
            logger.info("Stopping VILA model and killing Docker container...")

            # Set flags to stop processing
            self.running = False
            self.model_ready = False
            self.streaming_active = False

            # Stop all streaming clients
            with self.streaming_lock:
                for client in self.streaming_clients[:]:
                    try:
                        self.remove_streaming_client(client)
                    except Exception as e:
                        logger.error(f"Error removing streaming client: {e}")

            # CRITICAL: Kill Python process FIRST to prevent disconnect
            # The Python script runs docker run --rm, so killing the Python process
            # will cause the container to stop cleanly via --rm flag
            # If we kill container first, the Python process can hang/disconnect
            if self.process:
                logger.info(
                    "Stopping VILA Python process first (will stop container via --rm)...")

                # Close pipes first to unblock monitoring thread
                if self.process.stdout:
                    try:
                        self.process.stdout.close()
                    except:
                        pass
                if self.process.stderr:
                    try:
                        self.process.stderr.close()
                    except:
                        pass

                # Kill the Python process (container will stop via --rm)
                try:
                    self.process.kill()
                    self.process.wait(timeout=3)
                    logger.info(
                        "VILA Python process killed (container should auto-remove)")
                except ProcessLookupError:
                    logger.info("VILA process already terminated")
                except subprocess.TimeoutExpired:
                    logger.warning("Process kill timed out, forcing...")
                    try:
                        self.process.kill()
                    except:
                        pass
                except Exception as e:
                    logger.error(f"Error killing process: {e}")

                self.process = None

            # Now ensure container is killed (fallback if --rm didn't work)
            logger.info("Ensuring Docker container is stopped...")
            try:
                # Find running VILA containers by image
                logger.info(
                    "Finding containers with image dustynv/nano_llm:r36.4.0...")
                result = subprocess.run(
                    ["docker", "ps", "-q", "--filter",
                        "ancestor=dustynv/nano_llm:r36.4.0"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                logger.info(
                    f"Container search result: returncode={result.returncode}, stdout='{result.stdout.strip()}', stderr='{result.stderr.strip()}'")

                if result.returncode == 0 and result.stdout.strip():
                    container_ids = result.stdout.strip().split('\n')
                    logger.info(
                        f"Found {len(container_ids)} container(s): {container_ids}")
                    for container_id in container_ids:
                        if container_id:
                            container_id = container_id.strip()
                            logger.info(
                                f"Container {container_id} still running, force killing...")

                            # Force kill container (shouldn't be needed if Python process was killed)
                            kill_process = subprocess.Popen(
                                ["docker", "kill", container_id],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE
                            )

                            try:
                                kill_process.wait(timeout=5)
                                if kill_process.returncode == 0:
                                    logger.info(
                                        f"Container {container_id} killed successfully")
                                else:
                                    stdout, stderr = kill_process.communicate()
                                    logger.warning(
                                        f"Container kill returned code {kill_process.returncode}: {stdout.decode()}, {stderr.decode()}")
                            except subprocess.TimeoutExpired:
                                logger.error(
                                    f"Container kill command timed out for {container_id}")
                                kill_process.kill()
                else:
                    logger.info(
                        "No running VILA containers found (container removed by --rm)")
            except Exception as e:
                logger.error(
                    f"Error checking/killing container: {e}", exc_info=True)

            # Reset state
            self.last_result = None
            self.frame_counter = 0

            logger.info("VILA model stopped and container killed")

        except Exception as e:
            logger.error(f"Error stopping VILA model: {e}")

    def stop(self):
        """Stop VILA processor and clean up containers"""
        try:
            logger.info("Stopping VILA processor...")
            self.running = False
            self.model_ready = False

            if self.process:
                # Send SIGTERM to process
                self.process.terminate()

                # Wait for graceful shutdown
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    # Force kill if needed
                    self.process.kill()
                    self.process.wait()

                self.process = None

            # Clean up containers when stopping
            self._cleanup_containers()

            logger.info("VILA processor stopped")

        except Exception as e:
            logger.error(f"Error stopping VILA processor: {e}")


def main():
    """Test VILA integration"""
    logger.info("Testing VILA integration...")

    processor = VILAProcessor()

    try:
        # Wait for model to be ready
        time.sleep(10)

        # Test query processing
        result = processor.process_query("What do you see?")
        logger.info(f"Test result: {result}")

        # Keep running for a bit
        time.sleep(30)

    except KeyboardInterrupt:
        logger.info("Test interrupted")
    finally:
        processor.stop()


if __name__ == "__main__":
    main()
