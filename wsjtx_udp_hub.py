#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Small WSJT-X UDP hub.

Routes WSJT-X UDP packets to multiple local tools and optionally forwards
control packets from approved tools back to WSJT-X.

Aaron Heller <AK6IM@ARRL.net>
14 June 2026
"""

from __future__ import annotations

import argparse
import dataclasses
import select
import socket
import sys
import time

VALID_MODES = {"readonly", "control"}


@dataclasses.dataclass(frozen=True)
class Endpoint:
    host: str
    port: int

    @property
    def address(self) -> tuple[str, int]:
        return self.host, self.port


@dataclasses.dataclass(frozen=True)
class Client:
    name: str
    endpoint: Endpoint
    mode: str


@dataclasses.dataclass
class HubStats:
    wsjtx_packets: int = 0
    client_packets: int = 0
    forwarded_to_clients: int = 0
    forwarded_to_wsjtx: int = 0
    dropped_readonly: int = 0
    dropped_no_wsjtx: int = 0
    last_wsjtx: tuple[str, int] | None = None
    last_event: str = "waiting"


def parse_endpoint(text: str) -> Endpoint:
    if ":" not in text:
        raise argparse.ArgumentTypeError("expected HOST:PORT")
    host, port_text = text.rsplit(":", 1)
    if not host:
        raise argparse.ArgumentTypeError("host cannot be empty")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be an integer") from exc
    if not 0 < port < 65536:
        raise argparse.ArgumentTypeError("port must be 1-65535")
    return Endpoint(host, port)


def parse_client_simple(text: str) -> Client:
    # Kept separate so tests and future config readers can avoid the CLI's
    # trailing-field compatibility shim if desired.
    name_part, rest = text.split("=", 1)
    host, port_text, mode = rest.rsplit(":", 2)
    return _client_from_fields(name_part, host, port_text, mode)


def _client_from_fields(name: str, host: str, port_text: str, mode: str) -> Client:
    if not name:
        raise argparse.ArgumentTypeError("client name cannot be empty")
    if mode not in VALID_MODES:
        raise argparse.ArgumentTypeError("mode must be readonly or control")
    endpoint = parse_endpoint(f"{host}:{port_text}")
    return Client(name, endpoint, mode)


def parse_client_arg(text: str) -> Client:
    try:
        return parse_client_simple(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "expected NAME=HOST:PORT:readonly|control"
        ) from exc


def client_by_address(clients: list[Client]) -> dict[tuple[str, int], Client]:
    return {client.endpoint.address: client for client in clients}


def create_socket(listen: Endpoint) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(listen.address)
    sock.setblocking(False)
    return sock


def route_datagram(
    sock: socket.socket,
    data: bytes,
    sender: tuple[str, int],
    clients: list[Client],
    clients_by_addr: dict[tuple[str, int], Client],
    stats: HubStats,
) -> None:
    client = clients_by_addr.get(sender)
    if client:
        stats.client_packets += 1
        if client.mode != "control":
            stats.dropped_readonly += 1
            stats.last_event = f"dropped readonly packet from {client.name}"
            return
        if not stats.last_wsjtx:
            stats.dropped_no_wsjtx += 1
            stats.last_event = f"dropped control from {client.name}; no WSJT-X seen yet"
            return
        sock.sendto(data, stats.last_wsjtx)
        stats.forwarded_to_wsjtx += 1
        stats.last_event = f"control {client.name} -> WSJT-X {stats.last_wsjtx[0]}:{stats.last_wsjtx[1]}"
        return

    stats.wsjtx_packets += 1
    stats.last_wsjtx = sender
    forwarded = 0
    for dest in clients:
        sock.sendto(data, dest.endpoint.address)
        forwarded += 1
    stats.forwarded_to_clients += forwarded
    stats.last_event = f"WSJT-X {sender[0]}:{sender[1]} -> {forwarded} clients"


def stats_line(stats: HubStats) -> str:
    wsjtx = (
        "-" if not stats.last_wsjtx else f"{stats.last_wsjtx[0]}:{stats.last_wsjtx[1]}"
    )
    return (
        f"wsjtx={stats.wsjtx_packets} client={stats.client_packets} "
        f"to_clients={stats.forwarded_to_clients} to_wsjtx={stats.forwarded_to_wsjtx} "
        f"drop_ro={stats.dropped_readonly} drop_no_wsjtx={stats.dropped_no_wsjtx} "
        f"last_wsjtx={wsjtx} event={stats.last_event}"
    )


def run(args: argparse.Namespace) -> None:
    sock = create_socket(args.listen)
    clients_by_addr = client_by_address(args.client)
    stats = HubStats()
    last_print = 0.0

    print(f"Listening on {args.listen.host}:{args.listen.port}")
    for client in args.client:
        print(
            f"Client {client.name}: {client.endpoint.host}:{client.endpoint.port} {client.mode}"
        )
    print("Ctrl-C to stop.")

    while True:
        readable, _, _ = select.select([sock], [], [], 0.25)
        if readable:
            data, sender = sock.recvfrom(65535)
            route_datagram(sock, data, sender, args.client, clients_by_addr, stats)

        now = time.time()
        if args.status and now - last_print >= args.status:
            print(stats_line(stats), flush=True)
            last_print = now


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Route WSJT-X UDP packets to multiple tools."
    )
    parser.add_argument(
        "--listen", type=parse_endpoint, default=Endpoint("127.0.0.1", 2237)
    )
    parser.add_argument(
        "--client",
        type=parse_client_arg,
        action="append",
        default=[],
        help="Client as NAME=HOST:PORT:readonly|control. May be repeated.",
    )
    parser.add_argument(
        "--status",
        type=float,
        default=10.0,
        help="Print status every N seconds; 0 disables",
    )
    args = parser.parse_args()

    if not args.client:
        parser.error("at least one --client is required")

    try:
        run(args)
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)


if __name__ == "__main__":
    main()
