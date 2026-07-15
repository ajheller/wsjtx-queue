#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay recorded WSJT-X UDP packets, or synthesize decodes from ALL.TXT."""

from __future__ import annotations

import argparse
import base64
import json
import re
import socket
import struct
import sys
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

import wsjtx_queue

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 2237
DEFAULT_CLIENT_ID = "ALL.TXT"
DEFAULT_MODE = "FT8"
DEFAULT_CADENCE = 0.1
ALLTXT_MARKERS = {"~", "#", "@", "$"}
MODE_RE = re.compile(r"^(?:FT[48]|FST4|JT(?:4|9|65)|MSK144|Q65|WSPR)$", re.IGNORECASE)
TIME_RE = re.compile(r"^(?:(?:\d{6,8})_)?(\d{6})(?:\.\d+)?$")


@dataclass(frozen=True)
class ReplayEvent:
    delay: float
    data: bytes
    description: str = ""


def parse_addr(value: str) -> tuple[str, int]:
    if ":" not in value:
        return DEFAULT_HOST, int(value)
    host, port = value.rsplit(":", 1)
    return host or DEFAULT_HOST, int(port)


def encode_decode_packet(decode: wsjtx_queue.Decode) -> bytes:
    return b"".join(
        [
            struct.pack(">III", wsjtx_queue.MAGIC, wsjtx_queue.SCHEMA, wsjtx_queue.TYPE_DECODE),
            wsjtx_queue.qutf8(decode.client_id),
            wsjtx_queue.qbool(decode.is_new),
            wsjtx_queue.qu32(decode.time_ms),
            struct.pack(">i", decode.snr),
            struct.pack(">d", decode.dt_seconds),
            wsjtx_queue.qu32(decode.audio_hz),
            wsjtx_queue.qutf8(decode.mode),
            wsjtx_queue.qutf8(decode.message),
            wsjtx_queue.qbool(decode.low_confidence),
            wsjtx_queue.qbool(decode.off_air),
        ]
    )


def time_token_to_ms(token: str) -> int:
    match = TIME_RE.match(token)
    if not match:
        return 0
    hhmmss = match.group(1)
    hour = int(hhmmss[0:2])
    minute = int(hhmmss[2:4])
    second = int(hhmmss[4:6])
    if hour > 23 or minute > 59 or second > 59:
        return 0
    return ((hour * 60 + minute) * 60 + second) * 1000


def maybe_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def maybe_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def parse_alltxt_decode_line(
    line: str,
    *,
    client_id: str = DEFAULT_CLIENT_ID,
    default_mode: str = DEFAULT_MODE,
) -> wsjtx_queue.Decode | None:
    """Parse a common WSJT-X ALL.TXT decode line into a synthetic Decode packet.

    The format has varied across WSJT-X versions and settings. This parser looks
    for the stable decode core: SNR, DT, audio frequency, optional marker, then
    decoded message text. Tokens before SNR are used only to infer time and mode.
    """

    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None

    parts = stripped.split()
    for idx in range(0, max(0, len(parts) - 3)):
        snr = maybe_int(parts[idx])
        dt_seconds = maybe_float(parts[idx + 1])
        audio_hz = maybe_int(parts[idx + 2])
        if snr is None or dt_seconds is None or audio_hz is None:
            continue
        if not -99 <= snr <= 99 or not 0 <= audio_hz <= 5000:
            continue

        message_start = idx + 3
        if message_start < len(parts) and parts[message_start] in ALLTXT_MARKERS:
            message_start += 1
        if message_start >= len(parts):
            return None

        mode = default_mode.upper()
        for token in reversed(parts[:idx]):
            if MODE_RE.match(token):
                mode = token.upper()
                break

        time_ms = 0
        for token in reversed(parts[:idx]):
            time_ms = time_token_to_ms(token)
            if time_ms:
                break

        message = wsjtx_queue.normalize_message(" ".join(parts[message_start:]))
        if not message:
            return None
        return wsjtx_queue.Decode(client_id, True, time_ms, snr, dt_seconds, audio_hz, mode, message)

    return None


def raw_recording_events(path: str, *, speed: float = 1.0, no_timing: bool = False) -> Iterator[ReplayEvent]:
    previous_t: float | None = None
    with open(path, encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            obj = json.loads(line)
            if "format" in obj:
                continue
            data = base64.b64decode(obj["data"])
            event_t = float(obj.get("t", 0.0))
            delay = 0.0
            if not no_timing and previous_t is not None and event_t:
                delay = max(0.0, event_t - previous_t) / max(speed, 0.001)
            previous_t = event_t or previous_t
            yield ReplayEvent(delay, data, f"line {line_number}")


def alltxt_events(path: str, *, client_id: str, mode: str, cadence: float) -> Iterator[ReplayEvent]:
    with open(path, encoding="utf-8", errors="replace") as source:
        for line_number, line in enumerate(source, start=1):
            decode = parse_alltxt_decode_line(line, client_id=client_id, default_mode=mode)
            if decode is None:
                continue
            yield ReplayEvent(cadence, encode_decode_packet(decode), f"line {line_number}: {decode.message}")


def replay_events(events: Iterable[ReplayEvent], address: tuple[str, int], *, dry_run: bool = False) -> int:
    count = 0
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        for event in events:
            if event.delay > 0:
                time.sleep(event.delay)
            if dry_run:
                print(event.description or f"{len(event.data)} bytes")
            else:
                sock.sendto(event.data, address)
            count += 1
    finally:
        sock.close()
    return count


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSONL recording, or WSJT-X ALL.TXT excerpt with --alltxt")
    parser.add_argument(
        "--dest", default=f"{DEFAULT_HOST}:{DEFAULT_PORT}", help="UDP destination, default 127.0.0.1:2237"
    )
    parser.add_argument("--alltxt", action="store_true", help="Treat input as a WSJT-X ALL.TXT excerpt")
    parser.add_argument("--client-id", default=DEFAULT_CLIENT_ID, help="Synthetic client id for --alltxt")
    parser.add_argument("--mode", default=DEFAULT_MODE, help="Default mode for ALL.TXT lines without a mode token")
    parser.add_argument(
        "--cadence", type=float, default=DEFAULT_CADENCE, help="Delay between synthetic ALL.TXT decodes"
    )
    parser.add_argument("--speed", type=float, default=1.0, help="Replay speed multiplier for raw recordings")
    parser.add_argument(
        "--no-timing", action="store_true", help="Send raw recording packets without recorded timing gaps"
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse and count packets without sending UDP")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    address = parse_addr(args.dest)
    if args.alltxt:
        events = alltxt_events(args.input, client_id=args.client_id, mode=args.mode, cadence=args.cadence)
    else:
        events = raw_recording_events(args.input, speed=args.speed, no_timing=args.no_timing)

    count = replay_events(events, address, dry_run=args.dry_run)
    action = "Parsed" if args.dry_run else "Replayed"
    print(f"{action} {count} packets to {address[0]}:{address[1]}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
