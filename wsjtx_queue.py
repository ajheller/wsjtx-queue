#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""WSJT-X caller queue for SES and contest pileup handling.

Listens to WSJT-X-compatible UDP packets and ranks stations that appear to be
calling your callsign. This intentionally does not transmit or control WSJT-X.

Aaron Heller <AK6IM@ARRL.net>
10 April 2026
"""

from __future__ import annotations

import argparse
import curses
import dataclasses
import datetime as dt
import math
import re
import socket
import struct
import time
from typing import Callable, Iterable

MAGIC = 0xADBCCBDA
SCHEMA = 3
MAX_U32 = 0xFFFFFFFF
TYPE_HEARTBEAT = 0
TYPE_DECODE = 2
TYPE_CLEAR = 3
TYPE_QSO_LOGGED = 5
TYPE_LOGGED_ADIF = 12
TYPE_CONFIGURE = 15
NULL_STRING = 0xFFFFFFFF

PACKET_NAMES = {
    TYPE_HEARTBEAT: "heartbeat",
    TYPE_DECODE: "decode",
    TYPE_CLEAR: "clear",
    TYPE_QSO_LOGGED: "qso-logged",
    TYPE_LOGGED_ADIF: "logged-adif",
    TYPE_CONFIGURE: "configure",
}

CALL_RE = re.compile(
    r"^(?:(?:[A-Z0-9]{1,3}/)?[A-Z0-9]{1,3}[0-9][A-Z0-9]{1,4}(?:/[A-Z0-9]{1,4})?|[A-Z0-9]{1,4}/[A-Z0-9]{1,3}[0-9][A-Z0-9]{1,4})$"
)
GRID_RE = re.compile(r"^[A-R]{2}[0-9]{2}(?:[A-X]{2})?$")
ADIF_CALL_RE = re.compile(r"<CALL:(\d+)[^>]*>([^<\s]+)", re.IGNORECASE)


class PacketError(ValueError):
    pass


class Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def _take(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise PacketError("truncated packet")
        chunk = self.data[self.pos : self.pos + n]
        self.pos += n
        return chunk

    def u32(self) -> int:
        return struct.unpack(">I", self._take(4))[0]

    def i32(self) -> int:
        return struct.unpack(">i", self._take(4))[0]

    def f64(self) -> float:
        return struct.unpack(">d", self._take(8))[0]

    def bool(self) -> bool:
        return bool(struct.unpack(">?", self._take(1))[0])

    def utf8(self) -> str:
        length = self.u32()
        if length == NULL_STRING:
            return ""
        return self._take(length).decode("utf-8", errors="replace")


def qutf8(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack(">I", len(raw)) + raw


def qbool(value: bool) -> bytes:
    return struct.pack(">?", value)


def qu32(value: int) -> bytes:
    return struct.pack(">I", value)


@dataclasses.dataclass(frozen=True)
class ClientMessage:
    client_id: str


@dataclasses.dataclass(frozen=True)
class Decode:
    client_id: str
    is_new: bool
    time_ms: int
    snr: int
    dt_seconds: float
    audio_hz: int
    mode: str
    message: str
    low_confidence: bool = False
    off_air: bool = False


@dataclasses.dataclass(frozen=True)
class LoggedCall:
    call: str


@dataclasses.dataclass
class Caller:
    call: str
    first_seen: float
    last_seen: float
    snr: int
    dt_seconds: float
    audio_hz: int
    message: str
    grid: str = ""
    distance_km: float | None = None
    heard_count: int = 1


@dataclasses.dataclass
class CqStation:
    call: str
    first_seen: float
    last_seen: float
    snr: int
    dt_seconds: float
    audio_hz: int
    message: str
    grid: str = ""
    distance_km: float | None = None
    heard_count: int = 1


@dataclasses.dataclass
class RecentDecode:
    audio_hz: int
    snr: int
    last_seen: float


@dataclasses.dataclass
class CompletedCall:
    call: str
    completed_at: float
    reason: str


@dataclasses.dataclass
class WorkedStation:
    call: str
    worked_at: float
    count: int = 1


def parse_packet(data: bytes) -> tuple[int, object | None]:
    r = Reader(data)
    magic = r.u32()
    if magic != MAGIC:
        raise PacketError(f"bad magic 0x{magic:08x}")

    schema = r.u32()
    msg_type = r.u32()

    if msg_type == TYPE_HEARTBEAT:
        return msg_type, ClientMessage(r.utf8())

    if msg_type == TYPE_CLEAR:
        return msg_type, ClientMessage(r.utf8()) if r.pos < len(data) else None

    if msg_type == TYPE_LOGGED_ADIF:
        client_id = r.utf8()
        call = call_from_adif(r.utf8())
        return msg_type, LoggedCall(call) if call else ClientMessage(client_id)

    if msg_type == TYPE_QSO_LOGGED:
        call = call_from_qso_logged_payload(data[r.pos :])
        return msg_type, LoggedCall(call) if call else None

    if msg_type != TYPE_DECODE:
        return msg_type, None

    decode = Decode(
        client_id=r.utf8(),
        is_new=r.bool(),
        time_ms=r.u32(),
        snr=r.i32(),
        dt_seconds=r.f64(),
        audio_hz=r.u32(),
        mode=r.utf8(),
        message=normalize_message(r.utf8()),
        low_confidence=r.bool() if r.pos < len(data) else False,
        off_air=r.bool() if schema >= 3 and r.pos < len(data) else False,
    )
    return msg_type, decode


def configure_packet(
    client_id: str,
    *,
    rx_df: int = MAX_U32,
    dx_call: str = "",
    dx_grid: str = "",
    generate_messages: bool = False,
) -> bytes:
    """Build a WSJT-X Configure packet, leaving unspecified fields unchanged."""
    return b"".join(
        [
            struct.pack(">III", MAGIC, SCHEMA, TYPE_CONFIGURE),
            qutf8(client_id),
            qutf8(""),
            qu32(MAX_U32),
            qutf8(""),
            qbool(False),
            qu32(MAX_U32),
            qu32(rx_df),
            qutf8(dx_call),
            qutf8(dx_grid),
            qbool(generate_messages),
        ]
    )


def configure_rx_df_packet(client_id: str, rx_df: int) -> bytes:
    """Build a WSJT-X Configure packet that changes only Rx DF."""
    return configure_packet(client_id, rx_df=rx_df)


def configure_dx_packet(client_id: str, station: CqStation) -> bytes:
    """Build a WSJT-X Configure packet that sets DX fields for a CQ station."""
    return configure_packet(
        client_id,
        rx_df=station.audio_hz,
        dx_call=station.call,
        dx_grid=station.grid,
        generate_messages=True,
    )


def normalize_message(message: str) -> str:
    return " ".join(message.upper().replace("<", "").replace(">", "").split())


def call_from_adif(adif: str) -> str:
    match = ADIF_CALL_RE.search(adif)
    if not match:
        return ""
    length = int(match.group(1))
    return match.group(2)[:length].upper()


def qstring_candidates(data: bytes) -> list[str]:
    """Extract plausible Qt length-prefixed strings from a mixed payload.

    QSO Logged packets include non-string fields before the DX call. This keeps
    the parser tolerant without needing every field in the packet schema.
    """
    found: list[str] = []
    for pos in range(0, max(0, len(data) - 4)):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        if length == NULL_STRING or length == 0 or length > 64:
            continue
        start = pos + 4
        end = start + length
        if end > len(data):
            continue
        raw = data[start:end]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if text and all(32 <= ord(ch) <= 126 for ch in text):
            found.append(text.upper())
    return found


def call_from_qso_logged_payload(payload: bytes) -> str:
    candidates = qstring_candidates(payload)
    for text in candidates:
        if CALL_RE.match(text):
            return text
    return ""


def base_call(call: str) -> str:
    parts = call.upper().split("/")
    calls = [p for p in parts if CALL_RE.match(p)]
    return max(calls or parts, key=len)


def candidate_from_decode(my_call: str, decode: Decode) -> tuple[str, str] | None:
    """Return caller and grid when the decoded text appears directed at my_call."""
    if decode.low_confidence or decode.off_air:
        return None

    tokens = decode.message.split()
    if len(tokens) < 2:
        return None

    my = base_call(my_call)
    first = base_call(tokens[0])
    second = base_call(tokens[1])

    if first != my or not CALL_RE.match(second):
        return None

    grid = ""
    for token in tokens[2:]:
        if GRID_RE.match(token):
            grid = token[:6]
            break

    return second, grid


def cq_from_decode(decode: Decode) -> tuple[str, str] | None:
    """Return station and grid for CQ/QRZ-style decodes."""
    if decode.low_confidence or decode.off_air:
        return None

    tokens = decode.message.split()
    if not tokens or tokens[0] not in {"CQ", "QRZ"}:
        return None

    call = ""
    grid = ""
    for token in tokens[1:]:
        if not call and CALL_RE.match(token):
            call = token
            continue
        if GRID_RE.match(token):
            grid = token[:6]

    if not call:
        return None
    return call, grid


def is_completion_decode(decode: Decode) -> bool:
    tokens = decode.message.split()
    return any(token in {"73", "RR73"} for token in tokens[2:])


def maidenhead_center(grid: str) -> tuple[float, float] | None:
    grid = grid.strip().upper()
    if not GRID_RE.match(grid):
        return None

    lon = (ord(grid[0]) - ord("A")) * 20 - 180
    lat = (ord(grid[1]) - ord("A")) * 10 - 90
    lon += int(grid[2]) * 2
    lat += int(grid[3])

    lon_width = 2.0
    lat_height = 1.0
    if len(grid) >= 6:
        lon += (ord(grid[4]) - ord("A")) * (5.0 / 60.0)
        lat += (ord(grid[5]) - ord("A")) * (2.5 / 60.0)
        lon_width = 5.0 / 60.0
        lat_height = 2.5 / 60.0

    return lat + lat_height / 2.0, lon + lon_width / 2.0


def distance_km(a_grid: str, b_grid: str) -> float | None:
    a = maidenhead_center(a_grid)
    b = maidenhead_center(b_grid)
    if not a or not b:
        return None

    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    hav = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 6371.0 * 2 * math.atan2(math.sqrt(hav), math.sqrt(1 - hav))


def score_ses(c: Caller, now: float) -> float:
    age = now - c.last_seen
    return c.heard_count * 15 + c.snr - min(age, 180) / 6 - abs(c.dt_seconds) * 8


def score_arrl_digital(c: Caller, now: float) -> float:
    dist = c.distance_km or 0
    age = now - c.last_seen
    return dist / 100 + c.snr / 6 - min(age, 180) / 9 - abs(c.dt_seconds) * 4


def score_field_day(c: Caller, now: float) -> float:
    age = now - c.last_seen
    snr_bonus = max(min(c.snr, 20), -30)
    dt_penalty = abs(c.dt_seconds) * 15
    easy_audio_bonus = 6 if 300 <= c.audio_hz <= 2600 else -10
    return snr_bonus + easy_audio_bonus - dt_penalty - min(age, 120) / 5


SCORERS: dict[str, Callable[[Caller, float], float]] = {
    "ses": score_ses,
    "arrl-digital": score_arrl_digital,
    "field-day": score_field_day,
}


class QueueState:
    def __init__(
        self,
        my_call: str,
        my_grid: str,
        max_age: int,
        tx_min_hz: int,
        tx_max_hz: int,
        tx_step_hz: int,
        tx_guard_hz: int,
        tx_window: int,
        complete_on: str,
        completed_suppress: int,
    ) -> None:
        self.my_call = my_call.upper()
        self.my_grid = my_grid.upper()
        self.max_age = max_age
        self.tx_min_hz = tx_min_hz
        self.tx_max_hz = tx_max_hz
        self.tx_step_hz = tx_step_hz
        self.tx_guard_hz = tx_guard_hz
        self.tx_window = tx_window
        self.complete_on = complete_on
        self.completed_suppress = completed_suppress
        self.callers: dict[str, Caller] = {}
        self.cqs: dict[str, CqStation] = {}
        self.worked: dict[str, WorkedStation] = {}
        self.recent_decodes: list[RecentDecode] = []
        self.completed: dict[str, CompletedCall] = {}
        self.last_packet = 0.0
        self.last_packet_name = "none"
        self.last_packet_detail = "waiting for WSJT-X UDP"
        self.client_id = ""
        self.last_peer: tuple[str, int] | None = None
        self.control_message = "control disabled"
        self.control_message_until = 0.0
        self.control_baseline = "control disabled"
        self.packet_count = 0
        self.decode_count = 0
        self.logged_count = 0
        self.ignored_count = 0
        self.last_done = ""
        self.last_error = ""

    def note_packet(self, msg_type: int, detail: str = "") -> None:
        self.last_packet = time.time()
        self.last_packet_name = PACKET_NAMES.get(msg_type, f"type-{msg_type}")
        self.last_packet_detail = detail
        self.packet_count += 1

    def note_client(self, payload: object | None, peer: tuple[str, int]) -> None:
        self.last_peer = peer
        if isinstance(payload, Decode):
            self.client_id = payload.client_id
        elif isinstance(payload, ClientMessage):
            self.client_id = payload.client_id

    def set_control_enabled(self, enabled: bool) -> None:
        self.control_baseline = "control enabled" if enabled else "control disabled"
        self.control_message = self.control_baseline
        self.control_message_until = 0.0

    def set_control_message(self, message: str, ttl: float = 5.0) -> None:
        self.control_message = message
        self.control_message_until = time.time() + ttl if ttl > 0 else 0.0

    def current_control_message(self) -> str:
        if self.control_message_until and time.time() > self.control_message_until:
            self.control_message = self.control_baseline
            self.control_message_until = 0.0
        return self.control_message

    def add_decode(self, decode: Decode) -> None:
        self.decode_count += 1
        self.last_packet_detail = decode.message
        self.add_recent_decode(decode)
        cq_seen = self.add_cq_decode(decode)

        candidate = candidate_from_decode(self.my_call, decode)
        if not candidate:
            if not cq_seen:
                self.ignored_count += 1
            return

        call, grid = candidate
        if is_completion_decode(decode):
            if self.complete_on in {"73-only", "log-or-73"}:
                self.remove_completed_call(call, decode.message)
            return

        if self.is_suppressed(call):
            self.ignored_count += 1
            self.last_packet_detail = f"suppressed {call}: {decode.message}"
            return

        now = time.time()
        existing = self.callers.get(call)
        dist = distance_km(self.my_grid, grid) if grid and self.my_grid else None

        if existing:
            existing.last_seen = now
            existing.snr = decode.snr
            existing.dt_seconds = decode.dt_seconds
            existing.audio_hz = decode.audio_hz
            existing.message = decode.message
            existing.heard_count += 1
            if grid:
                existing.grid = grid
                existing.distance_km = dist
        else:
            self.callers[call] = Caller(
                call=call,
                first_seen=now,
                last_seen=now,
                snr=decode.snr,
                dt_seconds=decode.dt_seconds,
                audio_hz=decode.audio_hz,
                message=decode.message,
                grid=grid,
                distance_km=dist,
            )

    def add_cq_decode(self, decode: Decode) -> bool:
        cq = cq_from_decode(decode)
        if not cq:
            return False

        call, grid = cq
        now = time.time()
        existing = self.cqs.get(call)
        dist = distance_km(self.my_grid, grid) if grid and self.my_grid else None

        if existing:
            existing.last_seen = now
            existing.snr = decode.snr
            existing.dt_seconds = decode.dt_seconds
            existing.audio_hz = decode.audio_hz
            existing.message = decode.message
            existing.heard_count += 1
            if grid:
                existing.grid = grid
                existing.distance_km = dist
        else:
            self.cqs[call] = CqStation(
                call=call,
                first_seen=now,
                last_seen=now,
                snr=decode.snr,
                dt_seconds=decode.dt_seconds,
                audio_hz=decode.audio_hz,
                message=decode.message,
                grid=grid,
                distance_km=dist,
            )
        return True

    def add_recent_decode(self, decode: Decode) -> None:
        if decode.low_confidence or decode.off_air or decode.audio_hz <= 0:
            return
        self.recent_decodes.append(
            RecentDecode(decode.audio_hz, decode.snr, time.time())
        )
        self.prune_recent_decodes()

    def prune_recent_decodes(self) -> None:
        now = time.time()
        self.recent_decodes = [
            d for d in self.recent_decodes if now - d.last_seen <= self.tx_window
        ]

    def prune_completed(self) -> None:
        now = time.time()
        self.completed = {
            call: done
            for call, done in self.completed.items()
            if now - done.completed_at <= self.completed_suppress
        }

    def is_suppressed(self, call: str) -> bool:
        self.prune_completed()
        keys = {call.upper(), base_call(call)}
        return any(
            done.call in keys or base_call(done.call) in keys
            for done in self.completed.values()
        )

    def mark_completed(self, call: str, reason: str) -> None:
        call = call.upper()
        self.prune_completed()
        self.completed[call] = CompletedCall(call, time.time(), reason)

    def mark_worked(self, call: str) -> None:
        call = call.upper()
        existing = self.worked.get(call)
        if existing:
            existing.worked_at = time.time()
            existing.count += 1
        else:
            self.worked[call] = WorkedStation(call, time.time())

    def is_worked(self, call: str) -> bool:
        keys = {call.upper(), base_call(call)}
        return any(
            worked.call in keys or base_call(worked.call) in keys
            for worked in self.worked.values()
        )

    def suggested_tx(self) -> tuple[int | None, int | None, int]:
        self.prune_recent_decodes()
        if self.tx_max_hz < self.tx_min_hz:
            return None, None, len(self.recent_decodes)

        occupied = [
            d.audio_hz
            for d in self.recent_decodes
            if self.tx_min_hz <= d.audio_hz <= self.tx_max_hz
        ]
        if not occupied:
            return (self.tx_min_hz + self.tx_max_hz) // 2, None, 0

        best_hz = self.tx_min_hz
        best_clearance = -1
        for hz in range(self.tx_min_hz, self.tx_max_hz + 1, self.tx_step_hz):
            clearance = min(abs(hz - other) for other in occupied)
            edge_clearance = min(hz - self.tx_min_hz, self.tx_max_hz - hz)
            score = min(clearance, edge_clearance + self.tx_guard_hz)
            if score > best_clearance:
                best_hz = hz
                best_clearance = score

        return best_hz, best_clearance, len(occupied)

    def remove_logged_call(self, call: str) -> None:
        self.logged_count += 1
        self.mark_worked(call)
        if self.complete_on in {"log-only", "log-or-73"}:
            self.last_done = call.upper()
            self.last_packet_detail = f"logged {self.last_done}"
            self.mark_completed(self.last_done, "logged")
            self.remove_call(self.last_done)
        else:
            self.last_packet_detail = (
                f"logged {call.upper()} ignored by --complete-on {self.complete_on}"
            )

    def remove_completed_call(self, call: str, message: str) -> None:
        self.last_done = call.upper()
        self.last_packet_detail = f"completed {self.last_done}: {message}"
        self.mark_completed(self.last_done, "73")
        self.remove_call(self.last_done)

    def remove_call(self, call: str) -> None:
        call = call.upper()
        call_keys = {call, base_call(call)}
        for queued_call in list(self.callers):
            if queued_call in call_keys or base_call(queued_call) in call_keys:
                del self.callers[queued_call]
        for cq_call in list(self.cqs):
            if cq_call in call_keys or base_call(cq_call) in call_keys:
                del self.cqs[cq_call]

    def clear_stale(self) -> None:
        now = time.time()
        stale = [
            call for call, c in self.callers.items() if now - c.last_seen > self.max_age
        ]
        for call in stale:
            del self.callers[call]
        stale_cqs = [
            call for call, c in self.cqs.items() if now - c.last_seen > self.max_age
        ]
        for call in stale_cqs:
            del self.cqs[call]

    def ranked(self, profile: str) -> list[tuple[float, Caller]]:
        self.clear_stale()
        now = time.time()
        scorer = SCORERS[profile]
        rows = [(scorer(c, now), c) for c in self.callers.values()]
        rows.sort(key=lambda item: item[0], reverse=True)
        return rows

    def ranked_cqs(self, profile: str) -> list[tuple[float, CqStation]]:
        self.clear_stale()
        now = time.time()
        scorer = SCORERS[profile]
        rows = [(scorer(c, now), c) for c in self.cqs.values()]
        rows.sort(key=lambda item: item[0], reverse=True)
        return rows

    def ranked_worked(self) -> list[WorkedStation]:
        return sorted(
            self.worked.values(), key=lambda worked: worked.worked_at, reverse=True
        )


def udp_socket(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.setblocking(False)
    return sock


def next_view(view: str) -> str:
    views = ["queue", "cqs", "both", "worked"]
    return views[(views.index(view) + 1) % len(views)]


def render_station_row(
    stdscr: curses.window,
    y: int,
    width: int,
    idx: int,
    score: float,
    station: Caller | CqStation,
    now: float,
    worked: bool = False,
    attr: int = curses.A_NORMAL,
) -> None:
    age = now - station.last_seen
    dist = "-" if station.distance_km is None else f"{station.distance_km:.0f}"
    mark = "*" if worked else " "
    line = (
        f"{idx:>2}{mark} {score:>7.1f} {station.call:<12} {station.grid or '-':<6} {dist:>6} "
        f"{station.snr:>4} {station.dt_seconds:>5.1f} {station.audio_hz:>5} "
        f"{station.heard_count:>5} {age:>5.0f}  {station.message}"
    )
    stdscr.addnstr(y, 0, line, width - 1, attr)


def render_table_header(stdscr: curses.window, y: int, width: int, label: str) -> int:
    stdscr.addnstr(y, 0, label, width - 1, curses.A_BOLD)
    y += 1
    stdscr.addnstr(
        y,
        0,
        f"{'#':>2} {'Score':>7} {'Call':<12} {'Grid':<6} {'km':>6} {'SNR':>4} {'DT':>5} {'Hz':>5} {'Heard':>5} {'Age':>5}  Message",
        width - 1,
        curses.A_UNDERLINE,
    )
    return y + 1


def render(
    stdscr: curses.window,
    state: QueueState,
    profile: str,
    view: str,
    host: str,
    port: int,
) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    now = time.time()
    status_age = "-" if not state.last_packet else f"{now - state.last_packet:4.1f}s"
    title = (
        f"WSJT-X Queue  call={state.my_call} grid={state.my_grid or '-'} "
        f"profile={profile} view={view} complete={state.complete_on} udp={host}:{port} last={status_age}"
    )
    stdscr.addnstr(0, 0, title, width - 1, curses.A_BOLD)
    stdscr.addnstr(
        1,
        0,
        "Keys: 1 SES  2 ARRL Digital  3 Field Day  v view  Enter set DX  T set Rx DF  c clear  q quit  * worked",
        width - 1,
        curses.A_DIM,
    )
    stdscr.addnstr(
        2,
        0,
        f"Packets {state.packet_count}  Decodes {state.decode_count}  Ignored {state.ignored_count}  Queued {len(state.callers)}  CQs {len(state.cqs)}  Worked {len(state.worked)}",
        width - 1,
        curses.A_DIM,
    )
    if state.last_done:
        stdscr.addnstr(
            3,
            0,
            f"Last done: {state.last_done}  Logged packets: {state.logged_count}",
            width - 1,
            curses.A_DIM,
        )
    if state.last_error:
        stdscr.addnstr(3, 0, state.last_error, width - 1, curses.A_REVERSE)

    tx_hz, clearance, occupied_count = state.suggested_tx()
    if tx_hz is None:
        tx_line = "TX suggestion: unavailable; check --tx-min/--tx-max"
    elif clearance is None:
        tx_line = f"TX suggestion: {tx_hz} Hz  no recent decodes in {state.tx_min_hz}-{state.tx_max_hz} Hz"
    else:
        status = "clear" if clearance >= state.tx_guard_hz else "tight"
        tx_line = (
            f"TX suggestion: {tx_hz} Hz  nearest decode {clearance} Hz  "
            f"{status}  window {state.tx_window}s  seen {occupied_count}"
        )
    stdscr.addnstr(4, 0, tx_line, width - 1, curses.A_BOLD)

    y = 5
    if view in {"queue", "both"}:
        y = render_table_header(stdscr, y, width, "Callers")
        for idx, (score, caller) in enumerate(state.ranked(profile), start=1):
            if y >= height - 2:
                break
            attr = curses.A_BOLD if idx == 1 else curses.A_NORMAL
            render_station_row(
                stdscr,
                y,
                width,
                idx,
                score,
                caller,
                now,
                state.is_worked(caller.call),
                attr,
            )
            y += 1
        if view == "both" and y < height - 2:
            y += 1

    if view in {"cqs", "both"} and y < height - 2:
        y = render_table_header(stdscr, y, width, "CQs / QRZs")
        for idx, (score, cq) in enumerate(state.ranked_cqs(profile), start=1):
            if y >= height - 2:
                break
            attr = curses.A_BOLD if idx == 1 and view == "cqs" else curses.A_NORMAL
            render_station_row(
                stdscr, y, width, idx, score, cq, now, state.is_worked(cq.call), attr
            )
            y += 1

    if view == "worked" and y < height - 2:
        stdscr.addnstr(y, 0, "Worked", width - 1, curses.A_BOLD)
        y += 1
        stdscr.addnstr(
            y,
            0,
            f"{'#':>2} {'Call':<12} {'Count':>5} {'Age':>6}",
            width - 1,
            curses.A_UNDERLINE,
        )
        y += 1
        for idx, worked in enumerate(state.ranked_worked(), start=1):
            if y >= height - 2:
                break
            age = now - worked.worked_at
            line = f"{idx:>2} {worked.call:<12} {worked.count:>5} {age:>6.0f}"
            stdscr.addnstr(y, 0, line, width - 1)
            y += 1

    if state.last_packet:
        packet_age = f"{now - state.last_packet:4.1f}s ago"
    else:
        packet_age = "never"
    footer = (
        f"WSJT-X last packet: {state.last_packet_name} {packet_age}"
        f" | {state.last_packet_detail or '-'}"
    )
    if state.last_error:
        footer += f" | error: {state.last_error}"
    control_message = state.current_control_message()
    if control_message:
        footer += f" | {control_message}"
    stdscr.addnstr(height - 1, 0, footer, width - 1, curses.A_REVERSE)
    stdscr.refresh()


def send_suggested_rx_df(
    sock: socket.socket, state: QueueState, control_enabled: bool
) -> None:
    if not control_enabled:
        state.set_control_message("control disabled; restart with --control")
        return

    tx_hz, _, _ = state.suggested_tx()
    if tx_hz is None:
        state.set_control_message("control not sent; no suggested frequency")
        return
    if not state.client_id:
        state.set_control_message("control not sent; no WSJT-X client id yet")
        return
    if not state.last_peer:
        state.set_control_message("control not sent; no WSJT-X peer address yet")
        return

    packet = configure_rx_df_packet(state.client_id, tx_hz)
    sock.sendto(packet, state.last_peer)
    state.set_control_message(
        f"sent Rx DF {tx_hz} Hz to {state.client_id} at {state.last_peer[0]}:{state.last_peer[1]}"
    )


def send_top_cq_dx(
    sock: socket.socket, state: QueueState, profile: str, control_enabled: bool
) -> None:
    if not control_enabled:
        state.set_control_message("control disabled; restart with --control")
        return

    ranked = state.ranked_cqs(profile)
    if not ranked:
        state.set_control_message("control not sent; no CQ/QRZ station available")
        return
    if not state.client_id:
        state.set_control_message("control not sent; no WSJT-X client id yet")
        return
    if not state.last_peer:
        state.set_control_message("control not sent; no WSJT-X peer address yet")
        return

    station = ranked[0][1]
    packet = configure_dx_packet(state.client_id, station)
    sock.sendto(packet, state.last_peer)
    grid = f" {station.grid}" if station.grid else ""
    state.set_control_message(
        f"sent DX {station.call}{grid} at {station.audio_hz} Hz to {state.client_id}"
    )


def run_curses(stdscr: curses.window, args: argparse.Namespace) -> None:
    curses.curs_set(0)
    stdscr.nodelay(True)
    state = QueueState(
        args.call,
        args.grid,
        args.max_age,
        args.tx_min,
        args.tx_max,
        args.tx_step,
        args.tx_guard,
        args.tx_window,
        args.complete_on,
        args.completed_suppress,
    )
    state.set_control_enabled(args.control)
    sock = udp_socket(args.host, args.port)
    profile = args.profile
    view = args.view

    while True:
        try:
            while True:
                try:
                    data, peer = sock.recvfrom(65535)
                except BlockingIOError:
                    break
                try:
                    msg_type, payload = parse_packet(data)
                    state.note_client(payload, peer)
                    state.note_packet(msg_type)
                    if msg_type == TYPE_DECODE and isinstance(payload, Decode):
                        state.add_decode(payload)
                    elif msg_type in (TYPE_LOGGED_ADIF, TYPE_QSO_LOGGED) and isinstance(
                        payload, LoggedCall
                    ):
                        state.remove_logged_call(payload.call)
                    elif msg_type == TYPE_CLEAR:
                        state.callers.clear()
                        state.last_packet_detail = "cleared"
                except PacketError as exc:
                    state.last_error = str(exc)

            key = stdscr.getch()
            if key in (ord("q"), ord("Q")):
                break
            if key == ord("1"):
                profile = "ses"
            elif key == ord("2"):
                profile = "arrl-digital"
            elif key == ord("3"):
                profile = "field-day"
            elif key in (ord("v"), ord("V")):
                view = next_view(view)
            elif key in (ord("t"), ord("T")):
                send_suggested_rx_df(sock, state, args.control)
            elif key in (curses.KEY_ENTER, 10, 13):
                send_top_cq_dx(sock, state, profile, args.control)
            elif key in (ord("c"), ord("C")):
                state.callers.clear()
                state.cqs.clear()

            render(stdscr, state, profile, view, args.host, args.port)
            time.sleep(args.refresh)
        finally:
            pass


def demo_packets(my_call: str) -> Iterable[Decode]:
    samples = [
        f"{my_call} W6S DM04",
        f"{my_call} K1ABC FN42",
        f"{my_call} JA1NUT PM95",
        f"{my_call} N6XYZ CM98",
        "CQ K7ZZZ CN87",
        "CQ POTA 7M2VAP QM05",
        "QRZ VE7DX CN89",
        f"{my_call} VE7DX CN89",
    ]
    for i, msg in enumerate(samples):
        yield Decode(
            "WSJT-X",
            True,
            0,
            [-3, -14, -20, 10, 1, -17, -8, -8][i],
            0.1 + i / 10,
            500 + i * 260,
            "FT8",
            msg,
        )


def run_demo(args: argparse.Namespace) -> None:
    state = QueueState(
        args.call,
        args.grid,
        args.max_age,
        args.tx_min,
        args.tx_max,
        args.tx_step,
        args.tx_guard,
        args.tx_window,
        args.complete_on,
        args.completed_suppress,
    )
    for decode in demo_packets(args.call):
        state.add_decode(decode)
    tx_hz, clearance, occupied_count = state.suggested_tx()
    clear_text = "open band" if clearance is None else f"nearest decode {clearance} Hz"
    print(
        f"TX suggestion: {tx_hz} Hz ({clear_text}, {occupied_count} decodes in passband)"
    )
    for profile in SCORERS:
        print(f"\n{profile}")
        for score, caller in state.ranked(profile):
            dist = "-" if caller.distance_km is None else f"{caller.distance_km:.0f} km"
            print(
                f"{score:6.1f} {caller.call:8} {caller.grid:6} {dist:>8} {caller.snr:>4} dB  {caller.message}"
            )
    print("\ncqs")
    for score, cq in state.ranked_cqs(args.profile):
        dist = "-" if cq.distance_km is None else f"{cq.distance_km:.0f} km"
        print(
            f"{score:6.1f} {cq.call:8} {cq.grid:6} {dist:>8} {cq.snr:>4} dB  {cq.message}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rank stations calling you from WSJT-X UDP decodes."
    )
    parser.add_argument(
        "--call", required=True, help="Your callsign, e.g. AK6IM or K6C"
    )
    parser.add_argument(
        "--grid",
        default="CM87um",
        help="Your Maidenhead grid, used for distance scoring",
    )
    parser.add_argument("--host", default="127.0.0.1", help="UDP bind host")
    parser.add_argument("--port", type=int, default=2237, help="WSJT-X UDP server port")
    parser.add_argument("--profile", choices=sorted(SCORERS), default="ses")
    parser.add_argument(
        "--view",
        choices=("queue", "cqs", "both", "worked"),
        default="queue",
        help="Initial table view",
    )
    parser.add_argument(
        "--complete-on",
        choices=("log-or-73", "log-only", "73-only"),
        default="log-or-73",
        help="When to remove completed callers from the queue",
    )
    parser.add_argument(
        "--completed-suppress",
        type=int,
        default=600,
        help="Seconds to suppress re-adding calls after they complete",
    )
    parser.add_argument(
        "--max-age", type=int, default=180, help="Drop callers after this many seconds"
    )
    parser.add_argument(
        "--tx-min", type=int, default=300, help="Lowest TX audio frequency to suggest"
    )
    parser.add_argument(
        "--tx-max",
        type=int,
        default=2600,
        help="Highest TX audio frequency to suggest; use 2400 for older rigs",
    )
    parser.add_argument(
        "--tx-step", type=int, default=10, help="TX suggestion frequency step"
    )
    parser.add_argument(
        "--tx-guard", type=int, default=80, help="Desired spacing from nearby decodes"
    )
    parser.add_argument(
        "--tx-window",
        type=int,
        default=120,
        help="Seconds of recent decodes used for TX hole finding",
    )
    parser.add_argument(
        "--control",
        "--command",
        action="store_true",
        help="Enable WSJT-X UDP control hotkeys, including T to set Rx DF",
    )
    parser.add_argument(
        "--refresh", type=float, default=0.25, help="UI refresh interval"
    )
    parser.add_argument(
        "--demo", action="store_true", help="Print demo rankings and exit"
    )
    args = parser.parse_args()

    if args.demo:
        run_demo(args)
        return

    curses.wrapper(run_curses, args)


if __name__ == "__main__":
    main()
