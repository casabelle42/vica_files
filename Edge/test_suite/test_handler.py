"""
Unit tests for Edge/handler.py — EdgeHandler packet parsing and query
routing logic.

EdgeHandler.__init__ is not test-friendly by design: it spawns background
threads, shells out to `docker`, and blocks for a hardcoded time.sleep(3)
while "allowing startup" (see handler.py _start_model_container). None of
that is appropriate to run under pytest, so these tests build an
EdgeHandler via object.__new__ and set only the attributes __init__ would
have set before those side effects, letting us exercise the packet/query
logic in complete isolation. This mirrors how process_query is actually
invoked in production (already-initialized handler, called from the MQTT
worker thread).
"""

import queue
import threading
import time

import pytest

from handler import EdgeHandler, edge_device_name, inference_timeout_sec
from model_init import CFG


def make_handler(on_update_callback=None, ready=True, model_service=None, video_dir="/videos"):
    handler = object.__new__(EdgeHandler)
    handler.logger = EdgeHandler._init_logger(handler)
    handler.on_update_callback = on_update_callback
    handler.model_service = model_service
    handler.model_thread = None
    handler._stop_event = threading.Event()
    handler._ready = ready
    handler._status_thread = None
    handler.video_dir = video_dir
    handler.video_dir_created = False
    return handler


class FakeModelService:
    def __init__(self, results=None, raise_exc=None):
        self._results = results if results is not None else []
        self._raise_exc = raise_exc
        self.paused = False
        self.calls = []

    def run_inference_many(self, query_text, num_frames, timeout_sec, video_path=None):
        self.calls.append((query_text, num_frames, timeout_sec, video_path))
        if self._raise_exc:
            raise self._raise_exc
        return self._results

    def get_available_models(self):
        return ["dino-v2"]

    def get_active_model(self):
        return "dino-v2"


class TestEdgeDeviceName:
    def test_uses_vica_device_name_when_set(self, monkeypatch):
        monkeypatch.setenv("VICA_DEVICE_NAME", "Edge-Cam-07")
        assert edge_device_name() == "Edge-Cam-07"

    def test_falls_back_to_platform_node_when_unset(self, monkeypatch):
        monkeypatch.delenv("VICA_DEVICE_NAME", raising=False)
        monkeypatch.delenv("VICA_EDGE_NAME", raising=False)
        monkeypatch.delenv("HOSTNAME", raising=False)
        import platform

        assert edge_device_name() == platform.node()

    def test_prefers_vica_device_name_over_hostname(self, monkeypatch):
        monkeypatch.setenv("VICA_DEVICE_NAME", "primary")
        monkeypatch.setenv("HOSTNAME", "secondary")
        assert edge_device_name() == "primary"


class TestInferenceTimeoutSec:
    def test_default_is_60(self, monkeypatch):
        monkeypatch.delenv("VICA_INFERENCE_TIMEOUT_SEC", raising=False)
        assert inference_timeout_sec() == 60.0

    def test_reads_env_override(self, monkeypatch):
        monkeypatch.setenv("VICA_INFERENCE_TIMEOUT_SEC", "90")
        assert inference_timeout_sec() == 90.0

    def test_enforces_minimum_of_5(self, monkeypatch):
        monkeypatch.setenv("VICA_INFERENCE_TIMEOUT_SEC", "1")
        assert inference_timeout_sec() == 5.0

    def test_invalid_value_falls_back_to_60(self, monkeypatch):
        monkeypatch.setenv("VICA_INFERENCE_TIMEOUT_SEC", "not-a-number")
        assert inference_timeout_sec() == 60.0


class TestParseIncomingPacket:
    def test_new_format_packet_parses_header_and_body(self):
        handler = make_handler()
        packet_str = '{"header": {"message_type": "query_request"}, "body": {"query": "hi"}}'
        msg_type, body, is_legacy = handler._parse_incoming_packet(packet_str)
        assert msg_type == "query_request"
        assert body == {"query": "hi"}
        assert is_legacy is False

    def test_legacy_stop_command_maps_to_cancel(self):
        handler = make_handler()
        msg_type, body, is_legacy = handler._parse_incoming_packet('{"command": "stop"}')
        assert msg_type == "cancel_query_request"
        assert is_legacy is True
        assert "query_id" in body

    def test_legacy_stop_action_maps_to_cancel(self):
        handler = make_handler()
        msg_type, body, is_legacy = handler._parse_incoming_packet('{"action": "STOP"}')
        assert msg_type == "cancel_query_request"

    def test_legacy_plain_dict_treated_as_query_request(self):
        handler = make_handler()
        msg_type, body, is_legacy = handler._parse_incoming_packet('{"foo": "bar"}')
        assert msg_type == "query_request"
        assert is_legacy is True
        assert "query_id" in body

    def test_plain_string_stop_maps_to_cancel(self):
        handler = make_handler()
        msg_type, body, is_legacy = handler._parse_incoming_packet("stop")
        assert msg_type == "cancel_query_request"

    def test_plain_string_query_treated_as_query_request(self):
        handler = make_handler()
        msg_type, body, is_legacy = handler._parse_incoming_packet("find people")
        assert msg_type == "query_request"
        assert body["query"] == "find people"

    def test_malformed_json_falls_back_to_plain_string_query(self):
        handler = make_handler()
        msg_type, body, is_legacy = handler._parse_incoming_packet("{not valid json")
        assert msg_type == "query_request"
        assert is_legacy is True

    def test_empty_string_is_treated_as_query_request_with_empty_query(self):
        handler = make_handler()
        msg_type, body, is_legacy = handler._parse_incoming_packet("")
        assert msg_type == "query_request"
        assert body["query"] == ""


class TestCreatePacket:
    def test_wraps_body_with_header_fields(self, monkeypatch):
        monkeypatch.setenv("VICA_DEVICE_NAME", "Edge-Cam-01")
        handler = make_handler()
        pkt = handler._create_packet("device_status", {"cpu": 1.0})
        assert pkt["header"]["message_type"] == "device_status"
        assert pkt["header"]["source_device"] == "Edge-Cam-01"
        assert pkt["body"] == {"cpu": 1.0}
        assert "timestamp" in pkt["header"]


class TestProcessQueryUnknownAndEmpty:
    def test_unknown_message_type_returns_none(self):
        handler = make_handler()
        result = handler.process_query('{"header": {"message_type": "bogus"}, "body": {}}')
        assert result is None

    def test_missing_query_text_returns_none(self):
        handler = make_handler()
        packet = '{"header": {"message_type": "query_request"}, "body": {"query_id": "q1"}}'
        result = handler.process_query(packet)
        assert result is None

    def test_unparseable_packet_returns_none(self):
        handler = make_handler()
        # An empty string still parses as a query_request with query="" (falsy),
        # which handle_command's caller must handle as "no query text".
        result = handler.process_query('{"header": {}, "body": {}}')
        assert result is None


class TestProcessQueryNotReady:
    def test_emits_error_response_when_model_not_ready(self):
        captured = []
        handler = make_handler(on_update_callback=lambda t, p: captured.append((t, p)), ready=False)
        packet = '{"header": {"message_type": "query_request"}, "body": {"query": "hi", "query_id": "q1"}}'

        handler.process_query(packet)

        assert len(captured) == 1
        update_type, pkt = captured[0]
        assert update_type == "query_response"
        assert pkt["body"]["status"] == "error"
        assert "not ready" in pkt["body"]["answer"]


class TestProcessQueryTargeting:
    def _packet(self, targets=None, target=None):
        body = {"query": "find people", "query_id": "q1"}
        if targets is not None:
            body["target_devices"] = targets
        if target is not None:
            body["target_device"] = target
        import json

        return json.dumps({"header": {"message_type": "query_request"}, "body": body})

    def test_skips_query_when_this_device_not_targeted(self, monkeypatch):
        monkeypatch.setenv("VICA_DEVICE_NAME", "Edge-Cam-01")
        model_service = FakeModelService(results=[])
        handler = make_handler(model_service=model_service, ready=True)

        result = handler.process_query(self._packet(targets=["Edge-Cam-02"]))

        assert result is None
        assert model_service.calls == []  # never reached inference

    def test_processes_query_when_this_device_is_targeted(self, monkeypatch):
        monkeypatch.setenv("VICA_DEVICE_NAME", "Edge-Cam-01")
        model_service = FakeModelService(
            results=[{"image": "b64", "results": "found 2 people", "frame_id": 1, "frame_ts": None}]
        )
        captured = []
        handler = make_handler(
            on_update_callback=lambda t, p: captured.append((t, p)),
            model_service=model_service,
            ready=True,
        )

        handler.process_query(self._packet(targets=["Edge-Cam-01"]))

        assert len(model_service.calls) == 1
        assert len(captured) == 1
        assert captured[0][1]["body"]["answer"] == "found 2 people"

    def test_targeting_is_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("VICA_DEVICE_NAME", "Edge-Cam-01")
        model_service = FakeModelService(results=[{"image": "", "results": "ok", "frame_id": 1}])
        handler = make_handler(model_service=model_service, ready=True)

        handler.process_query(self._packet(targets=["edge-cam-01"]))

        assert len(model_service.calls) == 1

    def test_broadcast_with_no_targets_is_processed(self, monkeypatch):
        monkeypatch.setenv("VICA_DEVICE_NAME", "Edge-Cam-01")
        model_service = FakeModelService(results=[{"image": "", "results": "ok", "frame_id": 1}])
        handler = make_handler(model_service=model_service, ready=True)

        handler.process_query(self._packet(targets=[]))

        assert len(model_service.calls) == 1

    def test_single_target_device_field_is_honored(self, monkeypatch):
        monkeypatch.setenv("VICA_DEVICE_NAME", "Edge-Cam-01")
        model_service = FakeModelService(results=[])
        handler = make_handler(model_service=model_service, ready=True)

        result = handler.process_query(self._packet(target="Edge-Cam-99"))

        assert result is None
        assert model_service.calls == []


class TestProcessQueryResults:
    def test_no_results_emits_camera_unavailable_detail(self, monkeypatch):
        monkeypatch.setenv("VICA_DEVICE_NAME", "Edge-Cam-01")
        model_service = FakeModelService(results=[])
        model_service.camera_health = lambda: {
            "camera_open": False,
            "camera_error": "failed to open camera (index 0)",
        }
        captured = []
        handler = make_handler(
            on_update_callback=lambda t, p: captured.append((t, p)),
            model_service=model_service,
            ready=True,
        )
        packet = '{"header": {"message_type": "query_request"}, "body": {"query": "hi", "query_id": "q1"}}'

        handler.process_query(packet)

        assert captured[0][1]["body"]["status"] == "error"
        assert "Camera unavailable" in captured[0][1]["body"]["answer"]

    def test_multiple_frames_are_chunked_into_separate_responses(self, monkeypatch):
        monkeypatch.setenv("VICA_DEVICE_NAME", "Edge-Cam-01")
        model_service = FakeModelService(
            results=[
                {"image": "img1", "results": "r1", "frame_id": 1, "frame_ts": None},
                {"image": "img2", "results": "r2", "frame_id": 2, "frame_ts": None},
            ]
        )
        captured = []
        handler = make_handler(
            on_update_callback=lambda t, p: captured.append((t, p)),
            model_service=model_service,
            ready=True,
        )
        packet = '{"header": {"message_type": "query_request"}, "body": {"query": "hi", "query_id": "q1"}}'

        handler.process_query(packet)

        assert len(captured) == 2
        assert captured[0][1]["body"]["metadata"]["chunk_index"] == 0
        assert captured[0][1]["body"]["metadata"]["total_chunks"] == 2
        assert captured[1][1]["body"]["metadata"]["chunk_index"] == 1

    def test_inference_exception_emits_error_response_instead_of_raising(self, monkeypatch):
        monkeypatch.setenv("VICA_DEVICE_NAME", "Edge-Cam-01")
        model_service = FakeModelService(raise_exc=RuntimeError("boom"))
        captured = []
        handler = make_handler(
            on_update_callback=lambda t, p: captured.append((t, p)),
            model_service=model_service,
            ready=True,
        )
        packet = '{"header": {"message_type": "query_request"}, "body": {"query": "hi", "query_id": "q1"}}'

        result = handler.process_query(packet)

        assert result is None
        assert captured[0][1]["body"]["status"] == "error"
        assert "boom" in captured[0][1]["body"]["answer"]

    def test_unknown_video_name_falls_back_to_live_camera(self, monkeypatch):
        monkeypatch.setenv("VICA_DEVICE_NAME", "Edge-Cam-01")
        model_service = FakeModelService(results=[{"image": "", "results": "ok", "frame_id": 1}])
        handler = make_handler(model_service=model_service, ready=True, video_dir="/videos")
        packet = (
            '{"header": {"message_type": "query_request"}, '
            '"body": {"query": "hi", "query_id": "q1", "video": "does_not_exist.mp4"}}'
        )

        handler.process_query(packet)

        # resolve_video() found nothing, so video_path passed to inference is None.
        assert model_service.calls[0][3] is None


class TestCancelQueryRequest:
    def test_cancel_pauses_model_and_emits_status(self, monkeypatch):
        monkeypatch.setattr(EdgeHandler, "_check_container_exists", lambda self, name: False)
        model_service = FakeModelService()
        captured = []
        handler = make_handler(
            on_update_callback=lambda t, p: captured.append((t, p)),
            model_service=model_service,
            ready=True,
        )
        packet = '{"header": {"message_type": "cancel_query_request"}, "body": {"query_id": "q1"}}'

        handler.process_query(packet)

        assert model_service.paused is True
        assert handler._ready is False
        assert captured[-1][0] == "cancel_query_status"
        assert captured[-1][1]["body"]["status"] == "cancelled"


class TestContainerHelpers:
    def test_check_container_exists_true_when_name_in_docker_output(self, monkeypatch):
        handler = make_handler()

        def fake_run(*args, **kwargs):
            return type("R", (), {"stdout": "nano-vlm\n", "returncode": 0})()

        monkeypatch.setattr("handler.subprocess.run", fake_run)
        assert handler._check_container_exists("nano-vlm") is True

    def test_check_container_exists_false_when_docker_missing(self, monkeypatch):
        handler = make_handler()

        def fake_run(*args, **kwargs):
            raise FileNotFoundError("docker not found")

        monkeypatch.setattr("handler.subprocess.run", fake_run)
        assert handler._check_container_exists("nano-vlm") is False

    def test_stop_and_remove_container_success(self, monkeypatch):
        handler = make_handler()
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        monkeypatch.setattr("handler.subprocess.run", fake_run)
        assert handler._stop_and_remove_container("nano-vlm") is True
        assert any("rm" in c for c in calls)

    def test_stop_and_remove_container_swallows_exceptions(self, monkeypatch):
        handler = make_handler()

        def fake_run(cmd, **kwargs):
            raise RuntimeError("docker daemon not running")

        monkeypatch.setattr("handler.subprocess.run", fake_run)
        assert handler._stop_and_remove_container("nano-vlm") is False


class TestStop:
    def test_stop_pauses_model_and_calls_shutdown(self):
        model_service = FakeModelService()
        model_service.shutdown = lambda: setattr(model_service, "shutdown_called", True)
        handler = make_handler(model_service=model_service)

        handler.stop()

        assert model_service.paused is True
        assert model_service.shutdown_called is True
        assert handler._stop_event.is_set()

    def test_stop_without_model_service_does_not_raise(self):
        handler = make_handler(model_service=None)
        handler.stop()  # must not raise

    def test_stop_joins_live_threads(self):
        started = threading.Event()

        def loop():
            started.set()
            while not handler._stop_event.is_set():
                time.sleep(0.01)

        handler = make_handler()
        handler.model_thread = threading.Thread(target=loop, daemon=True)
        handler.model_thread.start()
        started.wait(timeout=1.0)

        handler.stop()

        assert not handler.model_thread.is_alive()


class TestHandleCommand:
    def test_dict_payload_is_json_encoded_before_processing(self, monkeypatch):
        monkeypatch.setenv("VICA_DEVICE_NAME", "Edge-Cam-01")
        model_service = FakeModelService(results=[])
        handler = make_handler(model_service=model_service, ready=False)
        captured = []
        handler.on_update_callback = lambda t, p: captured.append((t, p))

        handler.handle_command({"header": {"message_type": "query_request"}, "body": {"query": "hi"}})

        assert captured[0][1]["body"]["status"] == "error"  # not ready
