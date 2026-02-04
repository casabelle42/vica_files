#!/usr/bin/env python3
"""
NUC MQTT Relay

Pure message bridge:
- Host -> Edge
- Edge -> Host
"""

import paho.mqtt.client as mqtt

BROKER = "localhost"
PORT = 1883

HOST_TO_SERVER = "host/control"
SERVER_TO_EDGE = "edge/control"

EDGE_TO_SERVER = "edge/results"
SERVER_TO_HOST = "host/results"


def on_connect(client, userdata, flags, rc):
    print("[NUC] Connected to broker")
    client.subscribe([
        (HOST_TO_SERVER, 0),
        (EDGE_TO_SERVER, 0),
    ])


def on_message(client, userdata, msg):
    if msg.topic == HOST_TO_SERVER:
        client.publish(SERVER_TO_EDGE, msg.payload)
        print("[NUC] Host → Edge forwarded")

    elif msg.topic == EDGE_TO_SERVER:
        client.publish(SERVER_TO_HOST, msg.payload)
        print("[NUC] Edge → Host forwarded")


def main():
    client = mqtt.Client(client_id="vica-nuc-relay")
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER, PORT, 60)
    print("[NUC] Relay running...")
    client.loop_forever()


if __name__ == "__main__":
    main()
