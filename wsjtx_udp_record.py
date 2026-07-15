#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Record WSJT-X UDP packets to an inspectable JSON Lines file."""

from __future__ import annotations

import argparse
import base64
import json
import socket
import sys
import time

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 2245
MAX_PACKET = 65535


def parse_addr(value: str) -> tuple[str, int]:
    if ":" not in value:
        return DEFAULT_HOST, int(value)
    host, port = value.rsplit(":", 1)
    return host or DEFAULT_HOST, int(port)


def make_socket(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    return sock


def record_packets(
    sock: socket.socket,
    output,
    *,
    max_packets: int | None = None,
    max_seconds: float | None = None,
) -> int:
    started = time.time()
    count = 0
    output.write(json.dumps({"format": "wsjtx-udp-record-v1", "started": started}) + "\n")
    output.flush()

    while True:
        if max_packets is not None and count >= max_packets:
            break
        if max_seconds is not None and time.time() - started >= max_seconds:
            break

        data, peer = sock.recvfrom(MAX_PACKET)
        event = {
            "t": time.time(),
            "peer": [peer[0], peer[1]],
            "data": base64.b64encode(data).decode("ascii"),
        }
        output.write(json.dumps(event, separators=(",", ":")) + "\n")
        output.flush()
        count += 1

    return count


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--listen",
        default=f"{DEFAULT_HOST}:{DEFAULT_PORT}",
        help=f"UDP address to bind, default {DEFAULT_HOST}:{DEFAULT_PORT}",
    )
    parser.add_argument("-o", "--output", required=True, help="Output JSONL capture file")
    parser.add_argument("--max-packets", type=int, help="Stop after this many packets")
    parser.add_argument("--max-seconds", type=float, help="Stop after this many seconds")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    host, port = parse_addr(args.listen)
    sock = make_socket(host, port)
    print(f"Recording WSJT-X UDP from {host}:{port} to {args.output}")
    print("Ctrl-C to stop.")

    try:
        with open(args.output, "w", encoding="utf-8") as output:
            count = record_packets(sock, output, max_packets=args.max_packets, max_seconds=args.max_seconds)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    finally:
        sock.close()

    print(f"Recorded {count} packets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
