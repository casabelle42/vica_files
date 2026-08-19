"""
Unit tests for the helper functions in Network/server.py that
test_server_routing.py does not already cover: safe_json,
normalize_target_devices, prune_device_cache, make_discovery_response,
and on_connect. Loaded the same way test_server_routing.py does (via
importlib against the file path), since Network/server.py is a
standalone script, not an importable package module.
"""

import importlib.util
import json
import time
from pathlib import Path

SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"
spec = importlib.util.spec_from_file_location("network_server_helpers", SERVER_PATH)
network_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network_server)


def reset_state():
    network_server.device_cache.clear()


class TestSafeJson:
    def test_valid_json_parses_to_dict(self):
        assert network_server.safe_json(b'{"a": 1}') == {"a": 1}

    def test_invalid_json_returns_none(self):
        assert network_server.safe_json(b"{not valid") is None

    def test_non_utf8_bytes_return_none(self):
        assert network_server.safe_json(b"\xff\xfe\x00\x01") is None

    def test_empty_bytes_return_none(self):
        assert network_server.safe_json(b"") is None

    def test_valid_json_scalar_parses(self):
        # json.loads accepts bare scalars; safe_json should pass them through.
        assert network_server.safe_json(b"42") == 42


class TestNormalizeTargetDevices:
    def test_non_dict_body_returns_empty_list(self):
        assert network_server.normalize_target_devices(None) == []
        assert network_server.normalize_target_devices("not a dict") == []
        assert network_server.normalize_target_devices([1, 2]) == []

    def test_target_devices_string_becomes_single_item_list(self):
        assert network_server.normalize_target_devices({"target_devices": "Edge-Cam-01"}) == ["Edge-Cam-01"]

    def test_target_devices_blank_string_returns_empty_list(self):
        assert network_server.normalize_target_devices({"target_devices": "   "}) == []

    def test_target_devices_list_strips_and_filters_non_strings(self):
        body = {"target_devices": [" Edge-Cam-01 ", "", 42, None, "Edge-Cam-02"]}
        assert network_server.normalize_target_devices(body) == ["Edge-Cam-01", "Edge-Cam-02"]

    def test_falls_back_to_singular_target_device_field(self):
        assert network_server.normalize_target_devices({"target_device": "Edge-Cam-03"}) == ["Edge-Cam-03"]

    def test_target_devices_list_takes_priority_over_target_device(self):
        body = {"target_devices": ["Edge-Cam-01"], "target_device": "Edge-Cam-99"}
        assert network_server.normalize_target_devices(body) == ["Edge-Cam-01"]

    def test_no_targeting_fields_returns_empty_list(self):
        assert network_server.normalize_target_devices({"query": "hi"}) == []

    def test_empty_list_returns_empty_list(self):
        assert network_server.normalize_target_devices({"target_devices": []}) == []


class TestPruneDeviceCache:
    def test_removes_entries_older_than_ttl(self, monkeypatch):
        reset_state()
        monkeypatch.setattr(network_server, "DEVICE_CACHE_TTL_SEC", 10.0)
        now = 1_000_000.0
        network_server.device_cache["stale"] = {"body": {}, "last_seen": now - 20}
        network_server.device_cache["fresh"] = {"body": {}, "last_seen": now - 5}

        network_server.prune_device_cache(now)

        assert "stale" not in network_server.device_cache
        assert "fresh" in network_server.device_cache

    def test_entry_exactly_at_ttl_boundary_is_kept(self, monkeypatch):
        reset_state()
        monkeypatch.setattr(network_server, "DEVICE_CACHE_TTL_SEC", 10.0)
        now = 1_000_000.0
        network_server.device_cache["boundary"] = {"body": {}, "last_seen": now - 10}

        network_server.prune_device_cache(now)

        assert "boundary" in network_server.device_cache

    def test_missing_last_seen_defaults_to_zero_and_is_pruned(self, monkeypatch):
        reset_state()
        monkeypatch.setattr(network_server, "DEVICE_CACHE_TTL_SEC", 10.0)
        network_server.device_cache["no_timestamp"] = {"body": {}}

        network_server.prune_device_cache(1_000_000.0)

        assert "no_timestamp" not in network_server.device_cache

    def test_empty_cache_is_a_noop(self):
        reset_state()
        network_server.prune_device_cache()  # must not raise
        assert network_server.device_cache == {}


class TestMakeDiscoveryResponse:
    def test_empty_cache_returns_empty_devices_list(self):
        reset_state()
        resp = network_server.make_discovery_response()
        assert resp["header"]["message_type"] == "discovery_response"
        assert resp["body"]["devices"] == []

    def test_recent_device_is_marked_online(self):
        reset_state()
        network_server.device_cache["Edge-Cam-01"] = {
            "body": {"name": "Edge-Cam-01", "cpu": 5.0},
            "last_seen": time.time(),
        }
        resp = network_server.make_discovery_response()
        assert resp["body"]["devices"][0]["status"] == "online"

    def test_stale_device_is_marked_offline(self):
        reset_state()
        network_server.device_cache["Edge-Cam-01"] = {
            "body": {"name": "Edge-Cam-01"},
            "last_seen": time.time() - 30,
        }
        resp = network_server.make_discovery_response()
        assert resp["body"]["devices"][0]["status"] == "offline"

    def test_camera_open_field_included_only_when_present(self):
        reset_state()
        network_server.device_cache["with_cam"] = {
            "body": {"name": "with_cam", "camera_open": True},
            "last_seen": time.time(),
        }
        network_server.device_cache["without_cam"] = {
            "body": {"name": "without_cam"},
            "last_seen": time.time(),
        }
        resp = network_server.make_discovery_response()
        by_name = {d["name"]: d for d in resp["body"]["devices"]}
        assert by_name["with_cam"]["camera_open"] is True
        assert "camera_open" not in by_name["without_cam"]

    def test_camera_error_field_omitted_when_falsy(self):
        reset_state()
        network_server.device_cache["dev"] = {
            "body": {"name": "dev", "camera_error": ""},
            "last_seen": time.time(),
        }
        resp = network_server.make_discovery_response()
        assert "camera_error" not in resp["body"]["devices"][0]

    def test_missing_metrics_default_sensibly(self):
        reset_state()
        network_server.device_cache["bare"] = {"body": {}, "last_seen": time.time()}
        device = network_server.make_discovery_response()["body"]["devices"][0]
        assert device["cpu"] == 0.0
        assert device["network_strength"] == -100
        assert device["isProcessing"] is False


class TestOnConnect:
    def test_subscribes_to_all_expected_topics(self):
        class FakeClient:
            def __init__(self):
                self.subscribed = None

            def subscribe(self, topics):
                self.subscribed = topics
                return (0, 0)

        client = FakeClient()
        network_server.on_connect(client, None, {}, 0, None)

        topics = [t for t, _qos in client.subscribed]
        assert network_server.HOST_TO_SERVER in topics
        assert network_server.EDGE_TO_SERVER in topics
        assert network_server.EDGE_STATUS in topics
