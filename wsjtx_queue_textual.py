#!/usr/bin/env python3
"""Experimental Textual UI for wsjtx-queue."""

from __future__ import annotations

import argparse
import configparser
import pathlib
import socket
import sys
import time
from datetime import UTC, datetime

import wsjtx_queue as core

MixedStationRow = tuple[str, float, core.Caller | core.CqStation]

try:
    from rich.text import Text
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Vertical
    from textual.widgets import DataTable, Footer, Header, Static
except ModuleNotFoundError as exc:  # pragma: no cover - exercised by users without the optional dependency.
    if exc.name in {"rich", "textual"}:
        print(
            "The experimental Textual UI requires Textual.\n"
            "Install it with: python3 -m pip install textual\n"
            "Then run: wsjtx-queue-textual --call AK6IM --grid CM87um --demo",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    raise


class QueueTextualApp(App):
    """Color Textual front-end that reuses the wsjtx-queue core."""

    TITLE = "WSJT-X Queue"
    SUB_TITLE = "Textual"

    CSS = """
    Screen {
        background: #101318;
        color: #d7e0ea;
    }

    Header {
        background: #17324d;
        color: white;
    }

    #status {
        background: #16202a;
        color: #f4f7fb;
        padding: 0 1;
        height: 1;
    }

    #summary {
        background: #111820;
        color: #9fb0c0;
        padding: 0 1;
        height: 1;
    }

    #tx {
        background: #1a2118;
        color: #d8f5c3;
        padding: 0 1;
        height: 1;
    }

    DataTable {
        height: 1fr;
        background: #0b0f14;
        color: #d7e0ea;
    }

    DataTable > .datatable--header {
        background: #263545;
        color: #ffffff;
        text-style: bold;
    }

    Footer {
        background: #17324d;
        color: white;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("v", "cycle_view", "View"),
        ("1", "profile('ses')", "SES"),
        ("2", "profile('arrl-digital')", "ARRL Digital"),
        ("3", "profile('field-day')", "Field Day"),
        ("4", "profile('pota')", "POTA"),
        Binding("up", "move_selection(-1)", "Up", priority=True),
        Binding("down", "move_selection(1)", "Down", priority=True),
        Binding("enter", "set_dx", "Set DX", priority=True),
        Binding("t", "set_rx_df", "Set Rx DF", priority=True),
        ("c", "clear", "Clear"),
    ]

    def __init__(
        self,
        args: argparse.Namespace,
        state: core.QueueState,
        sock: socket.socket | None,
        bound_port: int | None,
    ) -> None:
        super().__init__()
        self.args = args
        self.state = state
        self.sock = sock
        self.bound_port = bound_port
        self.profile = args.profile
        self.view = args.view
        self.mixed_selected_kind = ""
        self.mixed_selected_call = ""
        self.mixed_selected_index = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Vertical():
            yield Static(id="status")
            yield Static(id="summary")
            yield Static(id="tx")
            yield DataTable(id="table")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(DataTable).cursor_type = "row"
        self.set_interval(self.args.refresh, self.tick)
        self.refresh_screen()

    def tick(self) -> None:
        if self.sock is not None:
            core.process_pending_udp(self.sock, self.state, self.args.max_udp_batch)
        self.refresh_screen()

    def action_profile(self, profile: str) -> None:
        self.profile = profile
        self.refresh_screen()

    def action_cycle_view(self) -> None:
        self.view = core.next_view(self.view)
        self.refresh_screen()

    def action_move_selection(self, delta: int) -> None:
        if self.view == "queue":
            self.state.move_caller_selection(self.profile, delta)
        elif self.view == "cqs":
            self.state.move_cq_selection(self.profile, delta)
        elif self.view == "both":
            self.move_mixed_selection(delta)
        self.refresh_screen()

    def action_set_dx(self) -> None:
        if self.sock is None:
            self.state.set_control_message("demo mode; control not sent")
        elif self.view == "both":
            station = self.selected_mixed_station()
            if station is None:
                self.state.set_control_message("control not sent; no station available")
            else:
                self.send_station_dx(station)
        else:
            core.send_selected_dx(self.sock, self.state, self.profile, self.view, self.args.control)
        self.refresh_screen()

    def action_set_rx_df(self) -> None:
        if self.sock is None:
            self.state.set_control_message("demo mode; control not sent")
        else:
            core.send_suggested_rx_df(self.sock, self.state, self.profile, self.args.control)
        self.refresh_screen()

    def action_clear(self) -> None:
        self.state.callers.clear()
        self.state.cqs.clear()
        self.refresh_screen()

    def refresh_screen(self) -> None:
        now = time.time()
        port_text = "demo" if self.bound_port is None else f"{self.args.host}:{self.bound_port}"
        status_age = "-" if not self.state.last_packet else f"{now - self.state.last_packet:4.1f}s"
        utc_time = datetime.now(UTC).strftime("%H:%M:%SZ")
        control = "control" if self.args.control else "listen-only"
        self.query_one("#status", Static).update(
            f"[b]WSJT-X Queue[/b]  call={self.state.my_call}  grid={self.state.my_grid or '-'}  "
            f"profile=[b]{self.profile}[/b]  view=[b]{self.view}[/b]  udp={port_text}  "
            f"last={status_age}  UTC {utc_time}  {control}"
        )
        self.query_one("#summary", Static).update(
            f"Packets {self.state.packet_count}  Decodes {self.state.decode_count}  "
            f"Ignored {self.state.ignored_count}  Queued {len(self.state.callers)}  "
            f"CQs {len(self.state.cqs)}  Worked {len(self.state.worked)}"
        )
        self.query_one("#tx", Static).update(self.tx_summary())
        self.render_table(now)

    def tx_summary(self) -> str:
        if self.state.status_dx_call and self.state.status_rx_df is not None:
            target_call, target_hz = self.state.status_dx_call, self.state.status_rx_df
        else:
            selected = self.selected_station_for_view()
            if selected is None:
                target_call, target_hz = core.tx_bias_target(self.state, self.profile)
            else:
                target_call, target_hz = selected.call, selected.audio_hz
        candidates = self.state.tx_candidates(target_hz, target_call, limit=1)
        if not candidates:
            return "[b yellow]TX suggestion:[/b yellow] unavailable"

        candidate = candidates[0]
        if candidate.clearance is None:
            clear = "open band"
        else:
            status = "clear" if candidate.clearance >= self.state.tx_guard_hz else "tight"
            clear = f"nearest decode {candidate.clearance} Hz  {status}"
        target = ""
        if candidate.target_call and candidate.target_delta is not None:
            target = f"  target {candidate.target_call} d{candidate.target_delta}"
        return (
            f"[b yellow]TX suggestion:[/b yellow] {candidate.hz} Hz  {clear}  "
            f"window {self.state.tx_window}s  seen {candidate.occupied_count}{target}"
        )

    def render_table(self, now: float) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True)

        if self.view == "worked":
            self.render_worked_table(table, now)
        elif self.view == "tx":
            self.render_tx_table(table)
        elif self.view == "cqs":
            self.render_station_table(table, now, "CQs / QRZs", self.state.ranked_cqs(self.profile), "cq")
        elif self.view == "both":
            rows = self.mixed_rows()
            self.render_station_table(table, now, "Callers and CQs", rows, "mixed")
        else:
            self.render_station_table(table, now, "Callers", self.state.ranked(self.profile), "caller")

    def mixed_rows(self) -> list[MixedStationRow]:
        rows: list[MixedStationRow] = [("Call", score, caller) for score, caller in self.state.ranked(self.profile)]
        rows.extend(("CQ", score, cq) for score, cq in self.state.ranked_cqs(self.profile))
        return rows

    def sync_mixed_selection(self, rows: list[MixedStationRow]) -> int | None:
        if not rows:
            self.mixed_selected_kind = ""
            self.mixed_selected_call = ""
            self.mixed_selected_index = 0
            return None

        if self.mixed_selected_call:
            for idx, (kind, _, station) in enumerate(rows):
                if kind == self.mixed_selected_kind and station.call == self.mixed_selected_call:
                    self.mixed_selected_index = idx
                    return idx

        self.mixed_selected_index = max(0, min(self.mixed_selected_index, len(rows) - 1))
        self.mixed_selected_kind, _, station = rows[self.mixed_selected_index]
        self.mixed_selected_call = station.call
        return self.mixed_selected_index

    def move_mixed_selection(self, delta: int) -> None:
        rows = self.mixed_rows()
        selected = self.sync_mixed_selection(rows)
        if selected is None:
            return

        self.mixed_selected_index = max(0, min(selected + delta, len(rows) - 1))
        self.mixed_selected_kind, _, station = rows[self.mixed_selected_index]
        self.mixed_selected_call = station.call

    def selected_mixed_station(self) -> core.Caller | core.CqStation | None:
        rows = self.mixed_rows()
        selected = self.sync_mixed_selection(rows)
        if selected is None:
            return None
        return rows[selected][2]

    def selected_station_for_view(self) -> core.Caller | core.CqStation | None:
        if self.view == "queue":
            return self.state.selected_caller(self.profile)
        if self.view == "cqs":
            return self.state.selected_cq(self.profile)
        if self.view == "both":
            return self.selected_mixed_station()
        return None

    def send_station_dx(self, station: core.Caller | core.CqStation) -> None:
        if not self.args.control:
            self.state.set_control_message("control disabled; restart with --control")
            return
        if not self.state.client_id:
            self.state.set_control_message("control not sent; no WSJT-X client id yet")
            return
        if not self.state.last_peer:
            self.state.set_control_message("control not sent; no WSJT-X peer address yet")
            return

        packet = core.configure_dx_packet(self.state.client_id, station)
        assert self.sock is not None
        self.sock.sendto(packet, self.state.last_peer)
        grid = f" {station.grid}" if station.grid else ""
        self.state.set_control_message(
            f"sent DX {station.call}{grid} at {station.audio_hz} Hz to {self.state.client_id}"
        )

    def render_station_table(
        self,
        table: DataTable,
        now: float,
        title: str,
        rows: list[tuple[float, core.Caller | core.CqStation]] | list[MixedStationRow],
        row_kind: str,
    ) -> None:
        table.add_column("#", width=3)
        table.add_column("Kind", width=5)
        table.add_column("Score", width=7)
        table.add_column("Call", width=12)
        table.add_column("Grid", width=6)
        table.add_column("km", width=6)
        table.add_column("SNR", width=4)
        table.add_column("DT", width=5)
        table.add_column("Hz", width=5)
        table.add_column("Heard", width=5)
        table.add_column("Age", width=5)
        table.add_column(title)
        if row_kind == "caller":
            selected = self.state.sync_caller_selection(rows)  # type: ignore[arg-type]
        elif row_kind == "cq":
            selected = self.state.sync_cq_selection(rows)  # type: ignore[arg-type]
        else:
            selected = self.sync_mixed_selection(rows)  # type: ignore[arg-type]

        for idx, raw_row in enumerate(rows, start=1):
            if row_kind == "mixed":
                kind, score, station = raw_row  # type: ignore[misc]
            else:
                score, station = raw_row  # type: ignore[misc]
                kind = "Call" if row_kind == "caller" else "CQ"
            age = now - station.last_seen
            dist = "-" if station.distance_km is None else f"{station.distance_km:.0f}"
            call_style = "bold bright_green"
            if self.state.is_wanted(station.call):
                call_style = "bold yellow"
            elif self.state.is_worked(station.call):
                call_style = "dim cyan"
            table.add_row(
                str(idx),
                kind,
                f"{score:.1f}",
                Text(station.call, style=call_style),
                station.grid or "-",
                dist,
                str(station.snr),
                f"{station.dt_seconds:.1f}",
                str(station.audio_hz),
                str(station.heard_count),
                f"{age:.0f}",
                station.message,
            )
        if selected is not None:
            table.move_cursor(row=selected, column=0, animate=False)

    def render_worked_table(self, table: DataTable, now: float) -> None:
        table.add_columns("#", "Call", "Count", "Age")
        for idx, worked in enumerate(self.state.ranked_worked(), start=1):
            table.add_row(
                str(idx), Text(worked.call, style="bold cyan"), str(worked.count), f"{now - worked.worked_at:.0f}"
            )

    def render_tx_table(self, table: DataTable) -> None:
        table.add_columns("#", "Score", "TX Hz", "Clear", "Edge", "Target", "Why")
        target_call, target_hz = core.tx_bias_target(self.state, self.profile)
        for idx, candidate in enumerate(self.state.tx_candidates(target_hz, target_call), start=1):
            clear_text = "open" if candidate.clearance is None else str(candidate.clearance)
            if candidate.target_call and candidate.target_hz is not None and candidate.target_delta is not None:
                target_text = f"{candidate.target_call} {candidate.target_hz} d{candidate.target_delta}"
            else:
                target_text = "-"
            if candidate.clearance is None:
                why = "no recent decodes"
            else:
                status = "clear" if candidate.clearance >= self.state.tx_guard_hz else "tight"
                why = f"{status}; nearest decode {candidate.clearance} Hz"
            table.add_row(
                str(idx),
                f"{candidate.score:.1f}",
                str(candidate.hz),
                clear_text,
                str(candidate.edge_clearance),
                target_text,
                why,
            )


def make_state(args: argparse.Namespace) -> core.QueueState:
    state = core.QueueState(
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
        args.wanted_calls,
        args.wanted_boost,
        args.activation_boost,
        args.activation_tags,
    )
    state.set_control_enabled(args.control)
    return state


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv = sys.argv[1:] if argv is None else argv
    config_probe = argparse.ArgumentParser(add_help=False)
    config_probe.add_argument("--config", default=str(core.default_config_path()))
    config_args, _ = config_probe.parse_known_args(argv)
    config_path = pathlib.Path(config_args.config).expanduser()
    explicit_config = any(arg == "--config" or arg.startswith("--config=") for arg in argv)

    try:
        defaults = core.load_config_defaults(config_path, explicit=explicit_config)
    except (OSError, configparser.Error, ValueError, argparse.ArgumentTypeError) as exc:
        config_probe.error(f"could not read config {config_path}: {exc}")

    parser = core.build_parser(defaults)
    parser.description = "Experimental Textual UI for wsjtx-queue."
    args = parser.parse_args(argv)
    core.validate_args(parser, args)
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if args.save_config:
        try:
            core.write_config(args, pathlib.Path(args.config).expanduser())
        except OSError as exc:
            raise SystemExit(f"could not write config {args.config}: {exc}") from exc
        print(f"Wrote config: {pathlib.Path(args.config).expanduser()}")
        return

    try:
        args.wanted_calls = core.load_wanted_calls(args.wanted) if args.wanted else set()
    except OSError as exc:
        raise SystemExit(f"could not read --wanted file: {exc}") from exc
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    state = make_state(args)
    sock = None
    bound_port = None
    if args.demo:
        for decode in core.demo_packets(args.call):
            state.add_decode(decode)
    else:
        ports = [args.port] if args.port is not None else args.ports
        sock, bound_port = core.udp_socket_from_ports(args.host, ports)

    QueueTextualApp(args, state, sock, bound_port).run()


if __name__ == "__main__":
    main()
