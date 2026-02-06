#!/usr/bin/env python3
"""
LAS-VICA GUI Test Runner
========================

Runs the GUI with a mock edge server for testing queries like:
"is there anyone behind the black car"

This script:
1. Generates test images (if not already present)
2. Starts a mock MQTT broker (if needed)
3. Starts the mock edge server
4. Launches the GUI application

Usage:
    python run_gui_test.py [--no-broker]
    
Options:
    --no-broker     Don't start local MQTT broker (use external broker)
    --broker IP     MQTT broker IP (default: localhost)
    --port PORT     MQTT broker port (default: 1883)
"""

import os
import sys
import time
import argparse
import subprocess
import threading
from pathlib import Path

# Add parent directories to path
current_dir = Path(__file__).parent
gui_dir = current_dir.parent
host_dir = gui_dir.parent
host_team_dir = host_dir.parent
project_root = host_team_dir.parent

for path in [str(current_dir), str(gui_dir), str(host_dir), str(host_team_dir), str(project_root)]:
    if path not in sys.path:
        sys.path.insert(0, path)


def check_dependencies():
    """Check and install required dependencies."""
    required = ["paho-mqtt", "Pillow", "PyQt6"]
    missing = []
    
    for pkg in required:
        try:
            __import__(pkg.replace("-", "_").lower().split("[")[0])
        except ImportError:
            # Handle special package names
            if pkg == "paho-mqtt":
                try:
                    import paho.mqtt.client
                except ImportError:
                    missing.append(pkg)
            elif pkg == "Pillow":
                try:
                    from PIL import Image
                except ImportError:
                    missing.append(pkg)
            else:
                missing.append(pkg)
    
    if missing:
        print(f"Missing dependencies: {missing}")
        print("Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
        print("Dependencies installed.\n")


def generate_test_images():
    """Generate test images if they don't exist."""
    test_images_dir = current_dir / "test_images"
    
    if test_images_dir.exists() and list(test_images_dir.glob("*.jpg")):
        print("[OK] Test images already exist")
        return True
    
    print("Generating test images...")
    try:
        from generate_test_images import main as generate_main
        generate_main()
        return True
    except Exception as e:
        print(f"Error generating test images: {e}")
        return False


def start_mock_server(broker_ip: str, broker_port: int):
    """Start the mock edge server in a subprocess."""
    mock_server_script = current_dir / "mock_edge_server.py"
    
    cmd = [
        sys.executable,
        str(mock_server_script),
        "--broker", broker_ip,
        "--port", str(broker_port)
    ]
    
    print(f"Starting mock edge server...")
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Print mock server output in a thread
    def print_output():
        for line in process.stdout:
            print(f"  {line.rstrip()}")
    
    output_thread = threading.Thread(target=print_output, daemon=True)
    output_thread.start()
    
    return process


def start_gui_application(broker_ip: str, broker_port: int):
    """Start the main GUI application."""
    # Set environment variables for MQTT configuration
    os.environ["VICA_MQTT_BROKER"] = broker_ip
    os.environ["VICA_MQTT_PORT"] = str(broker_port)
    
    print(f"\nStarting GUI application...")
    print(f"  MQTT Broker: {broker_ip}:{broker_port}")
    print()
    print("=" * 60)
    print("TEST INSTRUCTIONS:")
    print("=" * 60)
    print("1. Click 'Discover' to find mock edge devices")
    print("2. Click 'Query' to open the query window")
    print("3. Enter: 'is there anyone behind the black car'")
    print("4. Click 'Send' to see test images returned")
    print("=" * 60)
    print()
    
    # Import and run the GUI
    try:
        # Try the new file name first, then fall back
        try:
            from s1_start_app import main as gui_main
        except ImportError:
            from start_app import main as gui_main
        
        gui_main()
    except Exception as e:
        print(f"Error starting GUI: {e}")
        import traceback
        traceback.print_exc()


def run_standalone_test(broker_ip: str = "localhost", broker_port: int = 1883):
    """Run a standalone test without the full GUI."""
    print("\n" + "=" * 60)
    print("STANDALONE QUERY TEST")
    print("=" * 60)
    
    from mock_edge_server import MockEdgeServer, QueryMatcher
    
    # Test query matching
    test_queries = [
        "is there anyone behind the black car",
        "show me people behind the car",
        "where is the black car",
        "find all people in the scene"
    ]
    
    print("\nQuery Pattern Matching Test:")
    for query in test_queries:
        result = QueryMatcher.match_query(query)
        print(f"  Query: '{query}'")
        print(f"  → Images: {result['images']}")
        print(f"  → Response: {result['response_text'].format(count=2)}")
        print()
    
    print("[OK] Query matching test passed")


def main():
    parser = argparse.ArgumentParser(description="LAS-VICA GUI Test Runner")
    parser.add_argument("--broker", default="localhost", help="MQTT broker IP")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--standalone", action="store_true", help="Run standalone test only")
    parser.add_argument("--images-only", action="store_true", help="Only generate test images")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("LAS-VICA GUI Test Suite")
    print("=" * 60)
    print()
    
    # Check dependencies
    check_dependencies()
    
    # Generate test images
    if not generate_test_images():
        print("Failed to generate test images. Exiting.")
        return 1
    
    if args.images_only:
        print("\nTest images generated. Exiting.")
        return 0
    
    if args.standalone:
        run_standalone_test(args.broker, args.port)
        return 0
    
    # Start mock server
    mock_process = None
    try:
        mock_process = start_mock_server(args.broker, args.port)
        
        # Give the mock server time to connect
        time.sleep(2)
        
        # Start GUI
        start_gui_application(args.broker, args.port)
        
    except KeyboardInterrupt:
        print("\nTest interrupted.")
    finally:
        if mock_process:
            print("\nStopping mock server...")
            mock_process.terminate()
            mock_process.wait()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
