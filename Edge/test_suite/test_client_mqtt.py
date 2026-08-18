"""
Unit tests for Edge/client.py — MQTTEdgeClient's queueing, topic routing,
and lifecycle logic, isolated from both the real MQTT broker and the real
EdgeHandler (which is expensive to construct — see test_handler.py).

We monkeypatch the ``EdgeHandler`` symbol that client.py imported, so
``MQTTEdgeClient()`` builds a lightweight fake instead of spinning up
Docker/model threads. The real ``paho.mqtt.client.Client`` object is left
in place (constructing one does no I/O), but its network methods
(connect/publish) are never exercised here — only the in-process queues.
"""

import json
import queue
import threading
import time

import pytest

import client as client_module
from client import MQTTEdgeClient


class FakeEdgeHandler:
    instances = []

    def __init__(self, on_update_callback=None):
        self.on_update_callback = on_update_callback
        self.stopped = False
        self.processed = []
        FakeEdgeHandler.instances.append(self)

    def process_query(self, payload_str):
        self.processed.append(payload_str)

    def stop(self):
        self.stopped = True


@pytest.fixture(autouse=True)
def fake_edge_handler(monkeypatch):
    FakeEdgeHandler.instances.clear()
    monkeypatch.setattr(client_module, "EdgeHandler", FakeEdgeHandler)
    yield


@pytest.fixture
def edge_client():
    c = MQTTEdgeClient(mqtt_broker="unused", mqtt_port=1883)
    yield c
    # Ensure no lingering worker thread from tests that call start().
    c.stop()


class TestConstruction:
    def test_device_name_and_handler_wired_up(self, edge_client):
        assert isinstance(edge_client.edge_handler, FakeEdgeHandler)
        assert edge_client.device_name  # non-empty identity string

    def test_handler_update_callback_routes_to_outgoing_queue(self, edge_client):
        edge_client._on_handler_update("device_status", {"body": {}})
        topic, data = edge_client.outgoing_queue.get_nowait()
        assert topic == "edge/status"

    def test_container_status_also_routes_to_status_topic(self, edge_client):
        edge_client._on_handler_update("container_status", {"body": {}})
        topic, _ = edge_client.outgoing_queue.get_nowait()
        assert topic == "edge/status"

    def test_query_response_routes_to_results_topic(self, edge_client):
        edge_client._on_handler_update("query_response", {"body": {}})
        topic, _ = edge_client.outgoing_queue.get_nowait()
        assert topic == "edge/results"


class TestOnMqttConnect:
    def test_subscribes_to_device_topic_and_broadcast_topic(self, edge_client):
        calls = []
        fake_client = type("FC", (), {"subscribe": lambda self, t: calls.append(t)})()
        edge_client._on_mqtt_connect(fake_client, None, {}, 0)
        assert f"edge/{edge_client.device_name}/control" in calls
        assert "edge/control" in calls

    def test_connect_failure_does_not_subscribe(self, edge_client):
        calls = []
        fake_client = type("FC", (), {"subscribe": lambda self, t: calls.append(t)})()
        edge_client._on_mqtt_connect(fake_client, None, {}, 1)
        assert calls == []


class TestOnMqttMessage:
    def _msg(self, topic, payload: str):
        return type("Msg", (), {"topic": topic, "payload": payload.encode()})()

    def test_message_enqueued_for_worker_processing(self, edge_client):
        edge_client._on_mqtt_message(None, None, self._msg("edge/control", '{"a": 1}'))
        topic, payload = edge_client.incoming_queue.get_nowait()
        assert topic == "edge/control"
        assert payload == '{"a": 1}'

    def test_undecodable_payload_does_not_raise(self, edge_client):
        bad_msg = type("Msg", (), {"topic": "edge/control", "payload": b"\xff\xfe\x00"})()
        edge_client._on_mqtt_message(None, None, bad_msg)  # must not raise
        assert edge_client.incoming_queue.empty()

    def test_full_incoming_queue_drops_oldest_message(self, edge_client):
        edge_client.incoming_queue = queue.Queue(maxsize=2)
        for i in range(2):
            edge_client._on_mqtt_message(None, None, self._msg("t", f"msg{i}"))
        edge_client._on_mqtt_message(None, None, self._msg("t", "msg2"))  # triggers drop-oldest

        remaining = []
        while not edge_client.incoming_queue.empty():
            remaining.append(edge_client.incoming_queue.get_nowait()[1])
        assert remaining == ["msg1", "msg2"]


class TestWorkerLoop:
    def test_worker_thread_drains_incoming_queue_into_handler(self, edge_client):
        edge_client.incoming_queue.put(("edge/control", '{"query": "hi"}'))
        edge_client._stop.clear()
        t = threading.Thread(target=edge_client._worker_loop, daemon=True)
        t.start()
        deadline = time.time() + 2.0
        while time.time() < deadline and not edge_client.edge_handler.processed:
            time.sleep(0.01)
        edge_client._stop.set()
        t.join(timeout=2.0)

        assert edge_client.edge_handler.processed == ['{"query": "hi"}']

    def test_worker_survives_handler_exception(self, edge_client, monkeypatch):
        def boom(payload):
            raise RuntimeError("bad packet")

        edge_client.edge_handler.process_query = boom
        edge_client.incoming_queue.put(("edge/control", "bad"))
        edge_client._stop.clear()
        t = threading.Thread(target=edge_client._worker_loop, daemon=True)
        t.start()
        time.sleep(0.3)
        edge_client._stop.set()
        t.join(timeout=2.0)
        assert not t.is_alive()  # exception in one item does not kill the worker


class TestPublishOutgoing:
    def test_publishes_all_queued_packets(self, edge_client):
        published = []
        edge_client.mqtt_client.publish = lambda topic, payload: published.append((topic, payload)) or type(
            "R", (), {"rc": 0}
        )()
        edge_client.outgoing_queue.put(("edge/results", {"header": {}, "body": {"x": 1}}))
        edge_client.outgoing_queue.put(("edge/status", {"header": {}, "body": {"y": 2}}))

        edge_client._publish_outgoing()

        assert len(published) == 2
        assert json.loads(published[0][1])["body"] == {"x": 1}
        assert edge_client.outgoing_queue.empty()

    def test_publish_exception_does_not_raise_and_drains_queue(self, edge_client):
        def raising_publish(topic, payload):
            raise ConnectionError("broker unreachable")

        edge_client.mqtt_client.publish = raising_publish
        edge_client.outgoing_queue.put(("edge/results", {"header": {}, "body": {}}))

        edge_client._publish_outgoing()  # must not raise

        assert edge_client.outgoing_queue.empty()


class TestStop:
    def test_stop_stops_handler_and_joins_worker(self, edge_client):
        edge_client._stop.clear()
        edge_client._worker_thread = threading.Thread(
            target=edge_client._worker_loop, daemon=True
        )
        edge_client._worker_thread.start()
        edge_client.mqtt_client.loop_stop = lambda: None
        edge_client.mqtt_client.disconnect = lambda: None

        edge_client.stop()

        assert edge_client.edge_handler.stopped is True
        assert edge_client._stop.is_set()

    def test_stop_is_idempotent(self, edge_client):
        edge_client.mqtt_client.loop_stop = lambda: None
        edge_client.mqtt_client.disconnect = lambda: None
        edge_client.stop()
        edge_client.stop()  # must not raise or double-stop the handler oddly
        assert edge_client.edge_handler.stopped is True
