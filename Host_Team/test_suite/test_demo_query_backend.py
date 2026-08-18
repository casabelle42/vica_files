"""
Unit tests for Host_Team/Host/gui/demo_query.py's DemoBackend — the
offline stand-in for MqttBackend used by demo_start_app.py. Pure Python,
no Qt/network dependency, so it is exercised directly with its timer
delays shortened for fast tests.
"""

import time

import pytest

from demo_query import DemoBackend, DUMMY_DEVICES


@pytest.fixture
def backend():
    b = DemoBackend()
    b.DISCOVERY_DELAY_SEC = 0.01
    b.QUERY_FIRST_DELAY_SEC = 0.05
    b.QUERY_PER_TARGET_GAP_SEC = 0.05
    return b


def _collect(backend):
    captured = []
    backend.set_on_packet(captured.append)
    return captured


class TestDiscovery:
    def test_send_command_discover_emits_discovery_response(self, backend):
        captured = _collect(backend)
        pkt = backend.send_command({"command": "discover"})

        assert pkt["header"]["message_type"] == "discovery_response"
        assert len(pkt["body"]["devices"]) == len(DUMMY_DEVICES)
        assert captured == [pkt]

    def test_custom_device_list_is_used_and_copied(self):
        custom = [{"name": "Only-Cam"}]
        backend = DemoBackend(devices=custom)
        pkt = backend.send_command({"command": "discover"})
        assert [d["name"] for d in pkt["body"]["devices"]] == ["Only-Cam"]
        custom.append({"name": "Mutated-Later"})
        assert len(backend._devices) == 1  # backend took a defensive copy

    def test_non_discover_command_returns_empty_dict(self, backend):
        assert backend.send_command({"command": "bogus"}) == {}

    def test_discover_without_callback_does_not_raise(self):
        backend = DemoBackend()
        backend.DISCOVERY_DELAY_SEC = 0.01
        backend.send_command({"command": "discover"})  # no on_packet registered


class TestQueryRequest:
    def test_broadcast_when_no_targets_emits_single_response(self, backend):
        captured = _collect(backend)
        backend.send_query_request("find people")
        time.sleep(0.3)

        responses = [p for p in captured if p["header"]["message_type"] == "query_response"]
        assert len(responses) == 1
        assert responses[0]["header"]["source_device"] == "demo-edge-01"

    def test_targeted_query_emits_one_response_per_target(self, backend):
        captured = _collect(backend)
        backend.send_query_request("find people", target_devices=["Demo-Camera-Lobby", "Demo-Camera-Hallway"])
        time.sleep(0.3)

        responses = [p for p in captured if p["header"]["message_type"] == "query_response"]
        names = sorted(p["header"]["source_device"] for p in responses)
        assert names == ["Demo-Camera-Hallway", "Demo-Camera-Lobby"]

    def test_blank_and_non_string_targets_are_filtered_out(self, backend):
        captured = _collect(backend)
        backend.send_query_request("q", target_devices=["  ", 123, "Demo-Camera-Lobby"])
        time.sleep(0.3)

        responses = [p for p in captured if p["header"]["message_type"] == "query_response"]
        assert len(responses) == 1
        assert responses[0]["header"]["source_device"] == "Demo-Camera-Lobby"

    def test_query_id_is_generated_and_echoed_in_response(self, backend):
        captured = _collect(backend)
        qid = backend.send_query_request("q")
        time.sleep(0.3)
        assert qid.startswith("demo-")
        response = [p for p in captured if p["header"]["message_type"] == "query_response"][0]
        assert response["body"]["query_id"] == qid

    def test_explicit_query_id_is_preserved(self, backend):
        qid = backend.send_query_request("q", query_id="fixed-42")
        assert qid == "fixed-42"

    def test_video_metadata_is_echoed_when_provided(self, backend):
        captured = _collect(backend)
        backend.send_query_request("q", video="cam1/clip.mp4")
        time.sleep(0.3)
        response = [p for p in captured if p["header"]["message_type"] == "query_response"][0]
        assert response["body"]["metadata"]["video"] == "cam1/clip.mp4"
        assert response["body"]["metadata"]["source"] == "video"

    def test_no_video_defaults_source_to_camera(self, backend):
        captured = _collect(backend)
        backend.send_query_request("q")
        time.sleep(0.3)
        response = [p for p in captured if p["header"]["message_type"] == "query_response"][0]
        assert response["body"]["metadata"]["source"] == "camera"
        assert response["body"]["metadata"]["video"] is None


class TestClose:
    def test_close_stops_further_delivery(self, backend):
        captured = _collect(backend)
        backend.close()
        backend.send_query_request("q")
        time.sleep(0.3)
        assert captured == []
