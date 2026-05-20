from network_targeting_demo_backend import NetworkTargetingDemoBackend


def _collect_packets(backend):
    captured = []

    def on_packet(pkt):
        captured.append(pkt)

    backend.set_on_packet(on_packet)
    return captured


def test_discover_returns_three_devices():
    backend = NetworkTargetingDemoBackend()
    captured = _collect_packets(backend)

    response = backend.send_command({"command": "discover"})

    assert response.get("header", {}).get("message_type") == "discovery_response"
    devices = response.get("body", {}).get("devices", [])
    names = [d.get("name") for d in devices]
    assert names == ["Edge-Cam-01", "Edge-Cam-02", "Edge-Cam-03"]
    assert any(pkt.get("header", {}).get("message_type") == "discovery_response" for pkt in captured)


def test_targeted_query_emits_only_selected_device_response():
    backend = NetworkTargetingDemoBackend()
    captured = _collect_packets(backend)

    backend.send_query_request("find people", target_devices=["Edge-Cam-02"])

    # Timers are short; wait briefly for async callback.
    import time
    time.sleep(0.8)

    responses = [pkt for pkt in captured if pkt.get("header", {}).get("message_type") == "query_response"]
    assert len(responses) == 1
    assert responses[0].get("header", {}).get("source_device") == "Edge-Cam-02"


def test_broadcast_query_emits_all_device_responses():
    backend = NetworkTargetingDemoBackend()
    captured = _collect_packets(backend)

    backend.send_query_request("find people", target_devices=[])

    import time
    time.sleep(1.2)

    responses = [pkt for pkt in captured if pkt.get("header", {}).get("message_type") == "query_response"]
    names = sorted(pkt.get("header", {}).get("source_device") for pkt in responses)
    assert names == ["Edge-Cam-01", "Edge-Cam-02", "Edge-Cam-03"]
