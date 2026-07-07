# WSJT-X Queue

Terminal helper for FT8/FT4 operating with WSJT-X and WSJT-X Improved.

`wsjtx-queue` listens to the same WSJT-X UDP output used by tools like
GridTracker and turns recent decodes into operator-focused lists:

- a caller queue for stations calling your callsign during special-event, POTA,
  and contest pileups
- a CQ/QRZ list for hunting stations, including `CQ POTA`
- a worked-stations list for the current session
- wanted-call highlighting for special events, museum ships, W1AW portable
  operations, contest targets, and other chase lists
- TX audio-frequency suggestions based on holes among recent decodes
- optional WSJT-X control hotkeys for setting Rx DF or preparing a selected
  caller or CQ station

Directed messages such as:

```text
AK6IM K1ABC FN42
K6C JA1NUT PM95
```

are ranked using an operator-selectable profile such as `ses`, `field-day`,
`arrl-digital`, or `pota`.

When WSJT-X logs a QSO, the matching station is removed from the queue.
If the station later sends a final `73` to your callsign, that also removes it
from the queue even when WSJT-X does not emit another log event.

By default the tool is listen-only. With `--control`, it can send WSJT-X UDP
`Configure` packets, but it still does not transmit, key PTT, or control CAT.

## Run

The examples below use the standalone release command names.

Command names by platform:

- Windows PowerShell: `.\wsjtx-queue.exe` and `.\wsjtx-udp-hub.exe`
- macOS/Linux, from the extracted release folder: `./wsjtx-queue` and
  `./wsjtx-udp-hub`
- Source checkout: `python3 wsjtx_queue.py` and `python3 wsjtx_udp_hub.py`

First run: save your normal callsign and grid square. Your grid matters for
distance-aware profiles such as `arrl-digital` and `pota`.

```sh
wsjtx-queue --call AK6IM --grid CM87um --profile ses --save-config
```

After that, normal runs can use the saved defaults:

```sh
wsjtx-queue
```

By default the queue tries to bind UDP port `2237` first, then `2238`. This
covers the common cases where WSJT-X sends directly to the queue, or GridTracker
is already using `2237` and forwarding packets to `2238`.

For a special event callsign:

```sh
wsjtx-queue --call K6C --grid CM87um --profile ses
```

Demo mode, with no radio needed:

```sh
wsjtx-queue --call AK6IM --grid CM87um --demo
```

### Experimental Textual UI

The `feature/textual-ui` branch includes an experimental color UI built with
Textual. It is a prototype, not the default club-member setup.

From a source checkout:

```sh
make textual-venv
.venv-textual/bin/python wsjtx_queue_textual.py --call AK6IM --grid CM87um --demo
```

For live UDP testing:

```sh
.venv-textual/bin/python wsjtx_queue_textual.py --call AK6IM --grid CM87um --profile ses
```

On Raspberry Pi OS, run the app with `.venv-textual/bin/python` rather than
plain `python3`. If Textual reports a `platformdirs` import error, rerun
`make textual-venv` to refresh the venv packages. The Make targets clear
`PYTHONPATH` so system packages from the sBitx software environment do not
override the venv.

The Textual version uses the same ranking, completion, TX suggestion, config,
and UDP control code as the regular terminal UI. The point of the branch is to
evaluate whether color, richer table styling, and a footer key bar make the
operator workflow clearer enough to justify the extra dependency.

In Textual `both` view, callers and CQ/QRZ stations are shown as one mixed
selectable list. `Up` and `Down` move through the visible rows, and `Enter`
uses the highlighted row when `--control` is enabled.

GitHub Actions builds standalone Windows, macOS, and Linux artifacts for
`wsjtx_queue.py` and `wsjtx_udp_hub.py` on each push, pull request, and manual
workflow run. Version tags such as `v0.1.0` also publish a GitHub Release with
ready-to-download archives.

For normal installs, open the repository's
[latest release](https://github.com/ajheller/wsjtx-queue/releases/latest) and
download the archive for your platform:

- `wsjtx-queue-vX.Y.Z-windows.zip`: contains `wsjtx-queue.exe` and
  `wsjtx-udp-hub.exe`.
- `wsjtx-queue-vX.Y.Z-macos.tar.gz`: contains `wsjtx-queue` and
  `wsjtx-udp-hub`.
- `wsjtx-queue-vX.Y.Z-linux.tar.gz`: contains `wsjtx-queue` and
  `wsjtx-udp-hub`.

Each release archive also includes `README.md`, `LICENSE`, `docs/`, `wanted/`,
and a simple launcher for that platform.

### Desktop Shortcuts

After first-run setup with `--save-config`, non-CLI users can start the queue
from the launcher included in the release archive.

On Windows:

1. Extract `wsjtx-queue-vX.Y.Z-windows.zip`.
2. Double-click `Start WSJT-X Queue.bat`.
3. To put it on the desktop, right-click `Start WSJT-X Queue.bat`, choose
   `Send to -> Desktop (create shortcut)`, and rename the shortcut if desired.

On macOS:

1. Extract `wsjtx-queue-vX.Y.Z-macos.tar.gz`.
2. Follow the first-run quarantine step below if macOS blocks the app.
3. Double-click `Start WSJT-X Queue.command`.
4. To put it somewhere convenient, make an alias for `Start WSJT-X Queue.command`
   and move the alias to the desktop.

On Linux:

1. Extract `wsjtx-queue-vX.Y.Z-linux.tar.gz`.
2. Run `./start-wsjtx-queue.sh` from a terminal, or use your desktop
   environment's shortcut creator to launch that script.

### macOS First Run

The macOS release is not Apple-notarized. The first time you run it, macOS may
say Apple could not verify that `wsjtx-queue` is free of malware.

You can allow it from `System Settings -> Privacy & Security` after the first
blocked launch, or remove the download quarantine flag from the extracted
folder:

```sh
xattr -dr com.apple.quarantine ~/Downloads/wsjtx-queue-vX.Y.Z-macos
```

Then run it from Terminal:

```sh
./wsjtx-queue --call AK6IM --grid CM87um --profile ses --save-config
./wsjtx-queue
```

For an older transceiver/interface chain with less high-audio response, such as
a Kenwood TS-950S path that rolls off around 2.4 kHz:

```sh
wsjtx-queue --call W6S --grid CM87um --tx-max 2400
```

For contest/rate operating where your local log event is enough:

```sh
wsjtx-queue --call AK6IM --grid CM87um --profile arrl-digital --complete-on log-only
```

To prioritize a chase list in the caller queue and CQ/QRZ list:

```sh
wsjtx-queue --call AK6IM --grid CM87um --wanted wanted.txt
```

To enable WSJT-X control hotkeys:

```sh
wsjtx-queue --call AK6IM --grid CM87um --control
```

`--command` is accepted as an alias for `--control`.

To start in the CQ/QRZ list instead of the caller queue:

```sh
wsjtx-queue --call AK6IM --grid CM87um --view cqs
```

Or show both lists:

```sh
wsjtx-queue --call AK6IM --grid CM87um --view both
```

To start on the session worked-stations list:

```sh
wsjtx-queue --call AK6IM --grid CM87um --view worked
```

To start on the TX frequency candidate list:

```sh
wsjtx-queue --call AK6IM --grid CM87um --view tx
```

## Config File

Command-line options are still the quickest way to try the tool, but regular
operators can store their defaults in a config file. Command-line options
override config file values.

Default locations:

- macOS/Linux: `~/.config/wsjtx-queue/config.ini`
- Windows: `%APPDATA%\wsjtx-queue\config.ini`

Use `--config FILE` to use a different path.

To create or update your config from command-line options:

```sh
wsjtx-queue --call AK6IM --grid CM87um --profile ses --save-config
```

After that, normal runs can use the saved defaults:

```sh
wsjtx-queue
```

Example:

```ini
[station]
call = AK6IM
grid = CM87um

[udp]
ports = 2237,2238

[queue]
profile = ses
complete_on = log-or-73
wanted = wanted.txt
wanted_boost = 1000
activation_boost = 150
activation_tags = POTA,SOTA

[tx]
max = 2600

[ui]
refresh = 0.25
```

For distance-scored contest profiles, such as `arrl-digital`, set `grid` to
your home or activation grid square.

## WSJT-X Setup

In WSJT-X, open `Settings -> Reporting`.

- Enable UDP server.
- Use server `127.0.0.1`.
- Use port `2237`.
- Keep GridTracker pointed at WSJT-X as usual. If another app already binds
  port `2237`, use WSJT-X's secondary UDP forwarding or put this tool on a
  forwarded/multicast feed.

If you need to pin a single queue port, use `--port`:

```sh
wsjtx-queue --call AK6IM --grid CM87um --port 2240
```

If you want a different fallback list, use `--ports`:

```sh
wsjtx-queue --call AK6IM --grid CM87um --ports 2237,2238,2240
```

## Quick Start With GridTracker Forwarding

If you already use GridTracker and have its UDP forwarding enabled, the simplest
setup is:

```text
WSJT-X -> GridTracker -> wsjtx-queue
```

In GridTracker, enable `Forward UDP Messages`, set `IP` to `127.0.0.1`, and
set `Port` to `2238`:

![GridTracker Forward UDP Messages setting](docs/images/gridtracker-forward-udp-messages.png)

For example, if GridTracker forwards WSJT-X UDP packets to `127.0.0.1:2238`,
you can usually run the queue without a port option; it will try `2237` first
and fall back to `2238` if `2237` is already in use:

```sh
wsjtx-queue --call AK6IM --grid CM87um --save-config
wsjtx-queue
```

Do not add `--control` for the normal GridTracker-forwarding setup. Some
GridTracker configurations may pass control packets back to WSJT-X, but treat
that as an advanced choice. For club use, keeping the queue passive is less
surprising and leaves GridTracker as the control-capable app.

## Profiles

Press these keys while the UI is running:

- `1`: `ses` - steady special-event queue; favors stations heard repeatedly,
  decent SNR, fresh decodes, and low time offset.
- `2`: `arrl-digital` - distance-first ranking for contests where QSO points
  depend on distance.
- `3`: `field-day` - favors quick/easy contacts: stronger SNR, reasonable
  audio frequency, and low time offset.
- `4`: `pota` - favors fresh, workable callers with a modest distance boost.
  In CQ/QRZ view, activation CQs such as `CQ POTA` and `CQ SOTA` are strongly
  boosted for hunters.
- `v`: cycle between caller queue, CQ/QRZ list, both lists, worked list, and
  TX frequency candidates.
- `Up` / `Down`: select a caller row in queue view or a CQ/QRZ row in CQ views.
  Selection follows the callsign when rows re-rank.
- `Enter`: when started with `--control`, set WSJT-X `DX Call`, `DX Grid`,
  `Rx DF`, and `Generate Messages` from the selected caller or CQ/QRZ station.
- `T`: when started with `--control`, sends a WSJT-X `Configure` packet that
  sets `Rx DF` to the current suggested audio frequency. This does not directly
  set `Tx DF`; use WSJT-X's lock/coupling options if you want Tx to follow Rx.
  The send/failure status is shown briefly in the footer, then returns to the
  control enabled/disabled baseline.
- `c`: clear queue.
- `q`: quit.

## Completion Policy

`--complete-on` controls when a caller disappears from the queue:

- `log-or-73`: default; remove on your WSJT-X log event or their decoded final
  `73`. Good for SES/POTA courtesy operating.
- `log-only`: remove on your WSJT-X log event and suppress repeats for a while.
  Good for contest/rate operating.
- `73-only`: ignore local log events and wait until the other station sends a
  final `73`. Good for strict confirmation.

After a call completes, repeated reports from that call are suppressed for
`--completed-suppress 600` seconds by default.

## CQ/QRZ List

The `cqs` view lists stations calling `CQ` or `QRZ`, including common forms
such as `CQ POTA K7ABC CN87` and `CQ DX JA1ABC PM95`. CQs age out using the
same `--max-age` setting as callers, and are ranked with the same active
profile as the caller queue.

With `--control`, pressing `Enter` prepares WSJT-X to answer the selected
CQ/QRZ station by setting DX call/grid, moving Rx DF to that station's audio
frequency, and asking WSJT-X to generate messages. If you have not moved the
selection, the selected station is the top-ranked CQ/QRZ. It does not enable
transmit.

## POTA

For POTA activations, use the caller queue:

```sh
wsjtx-queue --call AK6IM --grid CM87um --profile pota
```

For POTA hunting, start in the CQ/QRZ list:

```sh
wsjtx-queue --call AK6IM --grid CM87um --profile pota --view cqs
```

The `pota` profile strongly boosts activation CQs in CQ/QRZ view while still
favoring fresh, workable callers in the normal queue. By default, `CQ POTA` and
`CQ SOTA` rows get `--activation-boost 150`. Use `--activation-tags
POTA,SOTA,WWFF,IOTA` to change which CQ tags are boosted. Raise
`--activation-boost` if you want activation CQs to dominate the hunting list
more aggressively, or lower it if you want ordinary CQ ranking factors to matter
more.

## Wanted Calls

Use `--wanted FILE` to mark and boost stations you are chasing, such as special
event stations, Museum Ships Weekend calls, W1AW portable stations, or contest
multipliers. Wanted stations are marked with `!` and receive a score boost in
both the caller queue and CQ/QRZ list.

Sample wanted files are included under `wanted/`:

- `wanted/13-colonies.txt`
- `wanted/w1aw-portable.txt`
- `wanted/world-cup-2026-ses.txt`

Example:

```sh
wsjtx-queue --call AK6IM --grid CM87um --view cqs --wanted wanted/13-colonies.txt
```

Example `wanted.txt`:

```text
# Museum Ships
NJ2BB Battleship New Jersey
K8E
W5KID

# W1AW portable
W1AW

# Match only this exact portable call
K6C/7
```

Only the first token on each non-comment line is used, so you can keep notes
after a callsign. Inline comments beginning with `#` are ignored.

Matching rules:

- `W1AW` matches `W1AW`, `W1AW/6`, and similar portable forms.
- `K6C/7` matches `K6C/7` specifically.

The default boost is `--wanted-boost 1000`, which is intentionally large enough
to float wanted stations to the top in normal use.

## Worked Tracking

Logged QSOs are added to a session worked list. Queue and CQ rows marked with
`*` are calls already worked this session. Rows marked with `!` are wanted
calls. The `worked` view shows worked calls, duplicate log count, and age since
last log. Pressing `c` clears active queue/CQ state but leaves worked history
intact.

## TX Frequency Suggestion

By default, TX suggestions are limited to `300-2600 Hz` and use decodes from
the last `120` seconds. The footer shows the top suggestion. The `tx` view shows
a ranked list of candidate audio frequencies, including local clearance, edge
spacing, and any target-frequency bias.

When WSJT-X reports a current `DX Call` and `Rx DF` in its Status UDP packet,
the candidate list mildly favors clear holes near that station's audio
frequency. This means changing the DX station in WSJT-X or GridTracker updates
the TX target bias. If WSJT-X has no current DX station, the target falls back
to the selected CQ/QRZ station or top-ranked caller. This is only a local
heuristic; it does not know what the DX station's receiver passband or local QRM
looks like.

Useful options:

- `--tx-min 300`: lowest TX audio frequency to suggest.
- `--tx-max 2600`: highest TX audio frequency to suggest.
- `--tx-max 2400`: useful for older rigs or audio chains that roll off high.
- `--tx-guard 80`: desired spacing from nearby decoded signals.
- `--tx-window 120`: how long recent decodes are considered active.

## Notes

- By default this is receive-only. With `--control`, it can send WSJT-X UDP
  control packets, but it still does not transmit, click callers, or control
  CAT/PTT.
- Logged QSOs are removed when WSJT-X sends its Logged ADIF or QSO Logged UDP
  notification.
- Callers age out after `--max-age` seconds, default `180`.
- This AK6IM copy defaults to `CM87um`. Use `--grid` to override it for
  portable activations.
- Distance scoring needs your grid and a caller grid in the decoded message.
- The parser currently uses WSJT-X decode, clear, Logged ADIF, and QSO Logged
  UDP packets.

## UDP Hub

`wsjtx-udp-hub` is a small companion router for running multiple WSJT-X UDP
tools at once. It forwards packets from WSJT-X to named clients. Clients marked
`readonly` can only receive packets. Clients marked `control` can also send
control packets back to WSJT-X through the hub.

For normal club setups, keep `wsjtx-queue` listen-only and leave GridTracker
as the control-capable app. Most of the queue tool's useful behavior is passive,
and this avoids surprising operators who already rely on GridTracker control.

Example topology:

```text
WSJT-X -> 127.0.0.1:2237 wsjtx-udp-hub
hub    -> 127.0.0.1:2238 GridTracker
hub    -> 127.0.0.1:2240 wsjtx-queue
```

Run the hub:

```sh
wsjtx-udp-hub \
  --listen 127.0.0.1:2237 \
  --client gridtracker=127.0.0.1:2238:control \
  --client queue=127.0.0.1:2240:readonly
```

Run the queue against the hub:

```sh
wsjtx-queue --call AK6IM --grid CM87um --port 2240
```

Configure WSJT-X UDP to send to `127.0.0.1:2237`. Configure GridTracker to use
`127.0.0.1:2238`. The queue listens on `127.0.0.1:2240`.

### Multiple Queue Windows

Because `wsjtx-queue` is listen-only by default, the hub can feed several queue
windows from the same WSJT-X UDP stream. This is useful when you want separate
views for callers, CQs, POTA/SOTA hunting, or wanted-call chasing.

Example topology:

```text
WSJT-X -> 127.0.0.1:2237 wsjtx-udp-hub
hub    -> 127.0.0.1:2238 GridTracker       control
hub    -> 127.0.0.1:2240 callers window    readonly
hub    -> 127.0.0.1:2241 activation CQs    readonly
hub    -> 127.0.0.1:2242 wanted CQs        readonly
```

Run the hub:

```sh
wsjtx-udp-hub \
  --listen 127.0.0.1:2237 \
  --client gridtracker=127.0.0.1:2238:control \
  --client callers=127.0.0.1:2240:readonly \
  --client activations=127.0.0.1:2241:readonly \
  --client wanted=127.0.0.1:2242:readonly
```

Then start separate queue windows:

```sh
wsjtx-queue --call AK6IM --grid CM87um --port 2240 --view queue --profile ses
wsjtx-queue --call AK6IM --grid CM87um --port 2241 --view cqs --profile pota
wsjtx-queue --call AK6IM --grid CM87um --port 2242 --view cqs --wanted wanted.txt
```

Leave these extra queue windows readonly unless you intentionally want one of
them to send WSJT-X control packets. If more than one client is marked
`control`, WSJT-X receives commands from all of them in arrival order, so the
last command wins.

If you intentionally want the queue tool to set WSJT-X fields with `T` or
`Enter`, start the queue with `--control` and mark the queue client as
`control` in the hub. In that setup, make other clients `readonly` unless you
really want more than one app sending commands to WSJT-X.

For protocol details, see [WSJT-X UDP Protocol Notes](docs/wsjtx-udp-protocol.md).

## License

This project is licensed under the GNU General Public License version 3.
This program interoperates with WSJT-X using its UDP message protocol. The
implementation was written independently and is not linked with WSJT-X.
If the GPL is an impediment to your use of this code, please contact AK6IM to
discuss alternate licensing.
