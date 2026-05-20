import json
import importlib.util
from pathlib import Path


SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"
spec = importlib.util.spec_from_file_location("network_server", SERVER_PATH)
network_server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network_server)


class FakeClient:
    def __init__(self):
        self.published = []
        self.subscribed = []

    def publish(self, topic, payload):
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        self.published.append((topic, payload))

        class Result:
            rc = 0

        return Result()

    def subscribe(self, topics):
        self.subscribed.append(topics)
        return (0, 0)


class FakeMsg:
    def __init__(self, topic, payload_dict):
        self.topic = topic
        self.payload = json.dumps(payload_dict).encode("utf-8")


def make_query_packet(target_devices=None, model="dino-v2"):
    body = {
        "query_id": "qid-123",
        "query": "find people",
    }
    if target_devices is not None:
        body["target_devices"] = target_devices
    if model:
        body["model"] = model

    return {
        "header": {
            "timestamp": "2026-05-20T12:00:00",
            "source_device": "Host-01",
            "message_type": "query_request",
        },
        "body": body,
    }


def make_discovery_packet():
    return {
        "header": {
            "timestamp": "2026-05-20T12:00:00",
            "source_device": "Host-01",
            "message_type": "discovery",
        },
        "body": {},
    }


def make_device_status_packet(name="Edge-Cam-01"):
    return {
        "header": {
            "timestamp": "2026-05-20T12:00:00",
            "source_device": name,
            "message_type": "device_status",
        },
        "body": {
            "name": name,
            "cpu": 12.3,
            "ram": 45.6,
            "gpu": 7.8,
            "network_strength": -60,
            "isProcessing": False,
            "available_models": ["dino-v2"],
            "active_model": "dino-v2",
        },
    }


def reset_state():
    network_server.device_cache.clear()


def test_targeted_query_single_device_routes_only_to_that_device():
    reset_state()
    client = FakeClient()
    pkt = make_query_packet(target_devices=["Edge-Cam-01"])
    msg = FakeMsg(network_server.HOST_TO_SERVER, pkt)

    network_server.on_message(client, None, msg)

    topics = [t for t, _ in client.published]
    assert "edge/Edge-Cam-01/control" in topics
    assert network_server.SERVER_TO_EDGE not in topics


def test_targeted_query_multiple_devices_routes_to_each_device_topic():
    reset_state()
    client = FakeClient()
    pkt = make_query_packet(target_devices=["Edge-Cam-01", "Edge-Cam-03"])
    msg = FakeMsg(network_server.HOST_TO_SERVER, pkt)

    network_server.on_message(client, None, msg)

    topics = [t for t, _ in client.published]
    assert "edge/Edge-Cam-01/control" in topics
    assert "edge/Edge-Cam-03/control" in topics
    assert network_server.SERVER_TO_EDGE not in topics


def test_broadcast_query_when_targets_missing_goes_to_edge_control():
    reset_state()
    client = FakeClient()
    pkt = make_query_packet(target_devices=None)
    msg = FakeMsg(network_server.HOST_TO_SERVER, pkt)

    network_server.on_message(client, None, msg)

    topics = [t for t, _ in client.published]
    assert network_server.SERVER_TO_EDGE in topics


def test_broadcast_query_when_targets_empty_goes_to_edge_control():
    reset_state()
    client = FakeClient()
    pkt = make_query_packet(target_devices=[])
    msg = FakeMsg(network_server.HOST_TO_SERVER, pkt)

    network_server.on_message(client, None, msg)

    topics = [t for t, _ in client.published]
    assert network_server.SERVER_TO_EDGE in topics


def test_discovery_request_publishes_discovery_response_to_host_results():
    reset_state()
    client = FakeClient()
    pkt = make_discovery_packet()
    msg = FakeMsg(network_server.HOST_TO_SERVER, pkt)

    network_server.on_message(client, None, msg)

    assert len(client.published) == 1
    topic, payload = client.published[0]
    assert topic == network_server.SERVER_TO_HOST
    parsed = json.loads(payload)
    assert parsed["header"]["message_type"] == "discovery_response"
    assert "devices" in parsed["body"]


def test_device_status_updates_cache_and_forwards_to_host_results():
    reset_state()
    client = FakeClient()
    pkt = make_device_status_packet("Edge-Cam-02")
    msg = FakeMsg(network_server.EDGE_STATUS, pkt)

    network_server.on_message(client, None, msg)

    assert "Edge-Cam-02" in network_server.device_cache
    topics = [t for t, _ in client.published]
    assert network_server.SERVER_TO_HOST in topics


def test_edge_results_forward_to_host_results():
    reset_state()
    client = FakeClient()
    pkt = {
        "header": {
            "timestamp": "2026-05-20T12:00:00",
            "source_device": "Edge-Cam-01",
            "message_type": "query_response",
        },
        "body": {"query_id": "q1"},
    }
    msg = FakeMsg(network_server.EDGE_TO_SERVER, pkt)

    network_server.on_message(client, None, msg)

    assert len(client.published) == 1
    topic, _ = client.published[0]
    assert topic == network_server.SERVER_TO_HOST
