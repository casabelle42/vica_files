#!/usr/bin/env python3
import argparse
import asyncio
import logging

from amqtt.broker import Broker


def _build_config(host: str, port: int) -> dict:
    return {
        "listeners": {
            "default": {
                "type": "tcp",
                "bind": f"{host}:{port}",
            }
        },
        "sys_interval": 10,
        "auth": {"allow-anonymous": True},
        "topic-check": {"enabled": False},
    }


async def _run(host: str, port: int) -> None:
    broker = Broker(_build_config(host, port))
    await broker.start()
    try:
        await asyncio.Future()
    finally:
        await broker.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description="Local MQTT broker (amqtt)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=1883, help="Bind port (default: 1883)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    print(f"[local_mqtt_broker] Starting MQTT broker on {args.host}:{args.port}")
    asyncio.run(_run(args.host, args.port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

