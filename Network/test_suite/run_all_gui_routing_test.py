import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


def terminate_process(proc: subprocess.Popen, name: str) -> None:
    if proc.poll() is not None:
        return

    try:
        if os.name == "nt":
            proc.terminate()
        else:
            proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def wait_for_broker(host: str, port: int, timeout_sec: float) -> bool:
    deadline = time.time() + max(0.1, float(timeout_sec))
    while time.time() < deadline:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        try:
            sock.connect((host, int(port)))
            return True
        except Exception:
            time.sleep(0.25)
        finally:
            try:
                sock.close()
            except Exception:
                pass
    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Start relay + mock edges + GUI routing test in one command."
    )
    parser.add_argument("--broker", default="localhost", help="MQTT broker host")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--edge-count", type=int, default=3, help="Number of mock edge devices")
    parser.add_argument("--python", default=sys.executable, help="Python executable to use")
    parser.add_argument("--startup-delay", type=float, default=1.5, help="Delay between startup steps")
    parser.add_argument("--broker-wait", type=float, default=5.0, help="Seconds to wait for broker readiness")
    args = parser.parse_args()

    test_suite_dir = Path(__file__).resolve().parent
    network_dir = test_suite_dir.parent
    repo_root = network_dir.parent

    server_path = network_dir / "server.py"
    mock_path = test_suite_dir / "mock_edge_fleet.py"
    gui_path = test_suite_dir / "run_gui_routing_test.py"

    env = os.environ.copy()
    env["VICA_MQTT_BROKER"] = str(args.broker)
    env["VICA_MQTT_PORT"] = str(args.port)
    env["VICA_TEST_EDGE_COUNT"] = str(args.edge_count)

    server_proc = None
    mock_proc = None

    try:
        print(f"[TEST_SUITE] Checking MQTT broker at {args.broker}:{args.port}...")
        if not wait_for_broker(args.broker, args.port, args.broker_wait):
            print(
                "[TEST_SUITE] ERROR: MQTT broker is not reachable. "
                "Start your broker first, then rerun this command."
            )
            return 2

        print("[TEST_SUITE] Starting Network relay...")
        server_proc = subprocess.Popen(
            [args.python, str(server_path)],
            cwd=str(repo_root),
            env=env,
        )
        time.sleep(max(0.0, args.startup_delay))
        if server_proc.poll() is not None:
            print(f"[TEST_SUITE] ERROR: Network relay exited early with code {server_proc.returncode}")
            return int(server_proc.returncode or 1)

        print("[TEST_SUITE] Starting mock edge fleet...")
        mock_proc = subprocess.Popen(
            [args.python, str(mock_path)],
            cwd=str(repo_root),
            env=env,
        )
        time.sleep(max(0.0, args.startup_delay))
        if mock_proc.poll() is not None:
            print(f"[TEST_SUITE] ERROR: mock_edge_fleet exited early with code {mock_proc.returncode}")
            return int(mock_proc.returncode or 1)

        print("[TEST_SUITE] Launching GUI routing test app...")
        gui_rc = subprocess.call(
            [args.python, str(gui_path)],
            cwd=str(repo_root),
            env=env,
        )
        print(f"[TEST_SUITE] GUI exited with code {gui_rc}")
        return int(gui_rc)

    finally:
        print("[TEST_SUITE] Cleaning up child processes...")
        if mock_proc is not None:
            terminate_process(mock_proc, "mock_edge_fleet")
        if server_proc is not None:
            terminate_process(server_proc, "network_server")


if __name__ == "__main__":
    raise SystemExit(main())
