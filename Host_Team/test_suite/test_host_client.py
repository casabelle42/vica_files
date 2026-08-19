"""
Unit tests for Host_Team/host_client.py — MQTTHostClient's packet
construction, targeting normalization, non-destructive caching, and the
HostCommandSender compatibility shim. No real MQTT connection is made:
mqtt_client.connect()/loop_start() are never invoked by these tests, only
the pure in-process logic (queue construction, header building, cache
handling) that also had to work correctly before host_client.py ever
touches a socket.
"""

import json
import queue
import threading
import time

import pytest

from host_client import HostCommandSender, MQTTHostClient


@pytest.fixture
def host():
    return MQTTHostClient(mqtt_broker="unused", mqtt_port=1883)


class TestSendDiscovery:
    def test_queues_discovery_packet_with_correct_shape(self, host):
        host.send_discovery()
        topic, pkt = host.outgoing_queue.get_nowait()
        assert topic == "host/control"
        assert pkt["header"]["message_type"] == "discovery"
        assert pkt["body"] == {}


class TestSendQueryRequest:
    def test_broadcast_query_omits_targeting_fields(self, host):
        host.send_query_request("find people")
        _topic, pkt = host.outgoing_queue.get_nowait()
        assert "target_devices" not in pkt["body"]
        assert "target_device" not in pkt["body"]

    def test_multiple_targets_set_target_devices_list(self, host):
        host.send_query_request("find people", target_devices=["Edge-01", "Edge-02"])
        _topic, pkt = host.outgoing_queue.get_nowait()
        assert pkt["body"]["target_devices"] == ["Edge-01", "Edge-02"]
        assert "target_device" not in pkt["body"]

    def test_single_target_devices_entry_stays_a_list_not_singular_field(self, host):
        # A non-empty target_devices list always wins over target_device,
        # even when it has exactly one entry.
        host.send_query_request("q", target_devices=["Edge-01"])
        _topic, pkt = host.outgoing_queue.get_nowait()
        assert pkt["body"]["target_devices"] == ["Edge-01"]
        assert "target_device" not in pkt["body"]

    def test_target_device_field_used_when_no_list_given(self, host):
        host.send_query_request("q", target_device="Edge-05")
        _topic, pkt = host.outgoing_queue.get_nowait()
        assert pkt["body"]["target_device"] == "Edge-05"
        assert "target_devices" not in pkt["body"]

    def test_blank_target_device_is_ignored(self, host):
        host.send_query_request("q", target_device="   ")
        _topic, pkt = host.outgoing_queue.get_nowait()
        assert "target_device" not in pkt["body"]

    def test_model_and_video_included_only_when_non_blank(self, host):
        host.send_query_request("q", model="dino-v2", video="cam1/clip.mp4")
        _topic, pkt = host.outgoing_queue.get_nowait()
        assert pkt["body"]["model"] == "dino-v2"
        assert pkt["body"]["video"] == "cam1/clip.mp4"

    def test_blank_model_and_video_are_omitted(self, host):
        host.send_query_request("q", model="  ", video="")
        _topic, pkt = host.outgoing_queue.get_nowait()
        assert "model" not in pkt["body"]
        assert "video" not in pkt["body"]

    def test_returns_generated_query_id_when_not_provided(self, host):
        qid = host.send_query_request("q")
        _topic, pkt = host.outgoing_queue.get_nowait()
        assert pkt["body"]["query_id"] == qid
        assert qid  # non-empty uuid string

    def test_explicit_query_id_is_preserved(self, host):
        qid = host.send_query_request("q", query_id="fixed-id-123")
        assert qid == "fixed-id-123"

    def test_none_query_becomes_empty_string(self, host):
        host.send_query_request(None)
        _topic, pkt = host.outgoing_queue.get_nowait()
        assert pkt["body"]["query"] == ""


class TestSendCancelAndCommand:
    def test_cancel_query_request_packet_shape(self, host):
        host.send_cancel_query_request("q1")
        _topic, pkt = host.outgoing_queue.get_nowait()
        assert pkt["header"]["message_type"] == "cancel_query_request"
        assert pkt["body"]["query_id"] == "q1"

    def test_send_command_wraps_params(self, host):
        host.send_command("reboot", {"force": True})
        _topic, pkt = host.outgoing_queue.get_nowait()
        assert pkt["body"]["command"] == "reboot"
        assert pkt["body"]["params"] == {"force": True}

    def test_send_command_defaults_params_to_empty_dict(self, host):
        host.send_command("ping")
        _topic, pkt = host.outgoing_queue.get_nowait()
        assert pkt["body"]["params"] == {}


class TestHandleIncoming:
    def test_non_dict_packet_is_ignored(self, host):
        host._handle_incoming("not a dict")  # must not raise
        assert host.get_last("anything") is None

    def test_device_status_updates_cache(self, host):
        pkt = {"header": {"message_type": "device_status"}, "body": {"name": "Edge-01", "cpu": 5.0}}
        host._handle_incoming(pkt)
        assert "Edge-01" in host.device_status_cache
        assert host.device_status_cache["Edge-01"]["body"]["cpu"] == 5.0

    def test_device_status_missing_name_defaults_to_unknown(self, host):
        pkt = {"header": {"message_type": "device_status"}, "body": {}}
        host._handle_incoming(pkt)
        assert "unknown" in host.device_status_cache

    def test_on_packet_callback_is_invoked(self, host):
        received = []
        host.on_packet = received.append
        pkt = {"header": {"message_type": "query_response"}, "body": {}}
        host._handle_incoming(pkt)
        assert received == [pkt]

    def test_on_packet_callback_exception_does_not_propagate(self, host):
        def boom(pkt):
            raise RuntimeError("gui crashed")

        host.on_packet = boom
        pkt = {"header": {"message_type": "query_response"}, "body": {}}
        host._handle_incoming(pkt)  # must not raise

    def test_get_last_returns_most_recent_packet_of_type(self, host):
        first = {"header": {"message_type": "query_response"}, "body": {"n": 1}}
        second = {"header": {"message_type": "query_response"}, "body": {"n": 2}}
        host._handle_incoming(first)
        host._handle_incoming(second)
        assert host.get_last("query_response")["body"]["n"] == 2

    def test_clear_last_removes_cached_packet(self, host):
        pkt = {"header": {"message_type": "discovery_response"}, "body": {}}
        host._handle_incoming(pkt)
        host.clear_last("discovery_response")
        assert host.get_last("discovery_response") is None

    def test_packet_missing_message_type_is_not_cached(self, host):
        host._handle_incoming({"header": {}, "body": {}})
        assert host.get_last(None) is None


class TestWaitForMessageType:
    def test_returns_immediately_if_already_cached_and_not_cleared(self, host):
        pkt = {"header": {"message_type": "discovery_response"}, "body": {}}
        host._handle_incoming(pkt)
        result = host.wait_for_message_type("discovery_response", timeout=1.0, clear_existing=False)
        assert result is pkt

    def test_clears_stale_packet_by_default_and_times_out(self, host):
        pkt = {"header": {"message_type": "discovery_response"}, "body": {}}
        host._handle_incoming(pkt)
        result = host.wait_for_message_type("discovery_response", timeout=0.2)
        assert result is None  # cleared, and nothing new arrived

    def test_wakes_up_when_matching_packet_arrives_from_another_thread(self, host):
        pkt = {"header": {"message_type": "query_response"}, "body": {"ok": True}}

        def deliver_later():
            time.sleep(0.1)
            host._handle_incoming(pkt)

        threading.Thread(target=deliver_later, daemon=True).start()
        result = host.wait_for_message_type("query_response", timeout=2.0)
        assert result["body"]["ok"] is True

    def test_times_out_returning_none_when_nothing_arrives(self, host):
        assert host.wait_for_message_type("never_comes", timeout=0.2) is None


class TestMqttCallbacks:
    def _fake_client(self, calls):
        return type(
            "FC",
            (),
            {
                "subscribe": lambda self, t: calls.append(("subscribe", t)),
                "publish": lambda self, t, p: calls.append(("publish", t, p)),
            },
        )()

    def test_on_connect_subscribes_to_host_results(self, host):
        calls = []
        host._on_mqtt_connect(self._fake_client(calls), None, {}, 0)
        assert ("subscribe", "host/results") in calls

    def test_on_connect_success_does_not_auto_discover_by_default(self, host):
        calls = []
        host._on_mqtt_connect(self._fake_client(calls), None, {}, 0)
        assert not any(c[0] == "publish" for c in calls)

    def test_on_connect_with_auto_discover_publishes_discovery(self):
        host = MQTTHostClient(mqtt_broker="unused", mqtt_port=1883, auto_discover_on_connect=True)
        published = []
        # _publish_direct publishes via self.mqtt_client, not the callback's client arg.
        host.mqtt_client.publish = lambda topic, payload: published.append((topic, payload))

        host._on_mqtt_connect(self._fake_client([]), None, {}, 0)

        assert len(published) == 1
        assert published[0][0] == "host/control"
        assert json.loads(published[0][1])["header"]["message_type"] == "discovery"

    def test_on_connect_failure_does_not_subscribe(self, host):
        calls = []
        host._on_mqtt_connect(self._fake_client(calls), None, {}, 1)
        assert calls == []

    def test_on_disconnect_does_not_raise_for_clean_or_unexpected(self, host):
        host._on_mqtt_disconnect(None, None, 0)
        host._on_mqtt_disconnect(None, None, 7)  # must not raise

    def test_on_mqtt_message_parses_and_caches_packet(self, host):
        msg = type(
            "Msg",
            (),
            {
                "topic": "host/results",
                "payload": json.dumps({"header": {"message_type": "device_status"}, "body": {"name": "Edge-01"}}).encode(),
            },
        )()
        host._on_mqtt_message(None, None, msg)
        assert "Edge-01" in host.device_status_cache
        assert host.incoming_queue.get_nowait()["body"]["name"] == "Edge-01"

    def test_on_mqtt_message_malformed_json_does_not_raise(self, host):
        msg = type("Msg", (), {"topic": "host/results", "payload": b"{not json"})()
        host._on_mqtt_message(None, None, msg)  # must not raise
        assert host.incoming_queue.empty()


class TestEnqueueIncomingOverflow:
    def test_full_incoming_queue_drops_oldest(self, host):
        host.incoming_queue = queue.Queue(maxsize=2)
        host._enqueue_incoming("a")
        host._enqueue_incoming("b")
        host._enqueue_incoming("c")

        remaining = []
        while not host.incoming_queue.empty():
            remaining.append(host.incoming_queue.get_nowait())
        assert remaining == ["b", "c"]


class TestPublishOutgoing:
    def test_publish_outgoing_sends_all_queued_packets(self, host):
        published = []
        host.mqtt_client.publish = lambda topic, payload: published.append((topic, payload)) or type(
            "R", (), {"rc": 0}
        )()
        host.send_discovery()
        host.send_command("ping")

        host._publish_outgoing()

        assert len(published) == 2
        assert host.outgoing_queue.empty()

    def test_publish_outgoing_exception_is_swallowed(self, host):
        def raising_publish(topic, payload):
            raise ConnectionError("broker down")

        host.mqtt_client.publish = raising_publish
        host.send_discovery()

        host._publish_outgoing()  # must not raise
        assert host.outgoing_queue.empty()


class TestHostCommandSenderShim:
    @pytest.fixture
    def sender(self, monkeypatch):
        # Prevent the shim from touching a real MQTT connection.
        monkeypatch.setattr(MQTTHostClient, "start_background", lambda self: None)
        return HostCommandSender(mqtt_broker="unused", request_timeout_sec=0.2)

    def test_discover_command_waits_for_response_and_returns_it(self, sender):
        pkt = {"header": {"message_type": "discovery_response"}, "body": {"devices": []}}
        threading.Timer(0.05, sender._client._handle_incoming, args=(pkt,)).start()
        result = sender.send_command({"command": "discover"})
        assert result["body"]["devices"] == []

    def test_discover_command_times_out_to_empty_dict(self, sender):
        assert sender.send_command({"command": "discover"}) == {}

    def test_query_command_waits_for_query_response(self, sender):
        pkt = {"header": {"message_type": "query_response"}, "body": {"answer": "42"}}
        threading.Timer(0.05, sender._client._handle_incoming, args=(pkt,)).start()
        result = sender.send_command({"command": "query", "query": "life?"})
        assert result["body"]["answer"] == "42"

    def test_unknown_command_falls_back_to_generic_send(self, sender):
        result = sender.send_command({"command": "reboot"})
        assert result == {}
        _topic, pkt = sender._client.outgoing_queue.get_nowait()
        assert pkt["body"]["command"] == "reboot"

    def test_send_query_request_returns_query_id_immediately(self, sender):
        qid = sender.send_query_request("hi", target_devices=["Edge-01"])
        assert qid
        _topic, pkt = sender._client.outgoing_queue.get_nowait()
        assert pkt["body"]["target_devices"] == ["Edge-01"]

    def test_set_on_packet_registers_callback_on_underlying_client(self, sender):
        received = []
        sender.set_on_packet(received.append)
        pkt = {"header": {"message_type": "query_response"}, "body": {}}
        sender._client._handle_incoming(pkt)
        assert received == [pkt]

    def test_close_stops_background_without_raising(self, sender, monkeypatch):
        monkeypatch.setattr(MQTTHostClient, "stop_background", lambda self: None)
        sender.close()  # must not raise
