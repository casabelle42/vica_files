"""
Additional edge-case coverage for NetworkTargetingDemoBackend, complementing
the happy-path tests in test_offline_targeting_backend.py: unknown targets,
malformed target lists, and callback-less usage.
"""

import time

from network_targeting_demo_backend import NetworkTargetingDemoBackend


def _collect_packets(backend):
    captured = []
    backend.set_on_packet(captured.append)
    return captured


class TestUnknownAndMalformedTargets:
    def test_unknown_device_name_is_dropped_and_falls_back_to_broadcast(self):
        backend = NetworkTargetingDemoBackend()
        captured = _collect_packets(backend)

        backend.send_query_request("find people", target_devices=["Ghost-Cam-99"])
        time.sleep(1.2)

        responses = [p for p in captured if p["header"]["message_type"] == "query_response"]
        names = sorted(p["header"]["source_device"] for p in responses)
        # No real devices matched, so the backend broadcasts to everyone.
        assert names == ["Edge-Cam-01", "Edge-Cam-02", "Edge-Cam-03"]

    def test_mixed_known_and_unknown_targets_only_hits_known_device(self):
        backend = NetworkTargetingDemoBackend()
        captured = _collect_packets(backend)

        backend.send_query_request("find people", target_devices=["Edge-Cam-02", "Ghost-Cam"])
        time.sleep(0.8)

        responses = [p for p in captured if p["header"]["message_type"] == "query_response"]
        assert len(responses) == 1
        assert responses[0]["header"]["source_device"] == "Edge-Cam-02"

    def test_non_string_targets_are_ignored(self):
        backend = NetworkTargetingDemoBackend()
        captured = _collect_packets(backend)

        backend.send_query_request("find people", target_devices=[123, None, {}])
        time.sleep(1.2)

        responses = [p for p in captured if p["header"]["message_type"] == "query_response"]
        # All targets were invalid, so it falls back to broadcast.
        assert len(responses) == 3

    def test_none_target_devices_broadcasts(self):
        backend = NetworkTargetingDemoBackend()
        captured = _collect_packets(backend)

        backend.send_query_request("find people", target_devices=None)
        time.sleep(1.2)

        responses = [p for p in captured if p["header"]["message_type"] == "query_response"]
        assert len(responses) == 3


class TestNoCallbackRegistered:
    def test_send_command_without_callback_does_not_raise(self):
        backend = NetworkTargetingDemoBackend()
        response = backend.send_command({"command": "discover"})
        assert response["body"]["devices"]

    def test_unknown_command_returns_empty_dict(self):
        backend = NetworkTargetingDemoBackend()
        assert backend.send_command({"command": "bogus"}) == {}

    def test_close_clears_callback_and_further_emits_are_silent(self):
        backend = NetworkTargetingDemoBackend()
        captured = _collect_packets(backend)
        backend.close()

        backend.send_command({"command": "discover"})  # must not raise, must not deliver
        assert captured == []
