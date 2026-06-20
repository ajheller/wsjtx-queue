# WSJT-X Queue

Small terminal queue manager for stations calling your callsign in WSJT-X.

It listens to the same UDP output used by tools like GridTracker, extracts
directed messages such as:

```text
AK6IM K1ABC FN42
K6C JA1NUT PM95
```

and ranks the callers using an operator-selectable profile.

When WSJT-X logs a QSO, the matching station is removed from the queue.
If the station later sends a final `73` to your callsign, that also removes it
from the queue even when WSJT-X does not emit another log event.

The bottom status line shows the last WSJT-X UDP packet received, how long ago
it arrived, and the decoded/logged detail when available.

The UI also suggests a TX audio frequency by looking for holes among recent
decodes. It does not change WSJT-X; it only tells you where a clean spot may be.
When started with `--control`, pressing `T` sends the suggested frequency to
WSJT-X as `Rx DF`. Straight WSJT-X/WSJT-X Improved UDP does not provide a direct
`Tx DF` setter.

## Run

```sh
python3 wsjtx_queue.py --call AK6IM
```

By default the queue tries to bind UDP port `2237` first, then `2238`. This
covers the common cases where WSJT-X sends directly to the queue, or GridTracker
is already using `2237` and forwarding packets to `2238`.

For a special event callsign:

```sh
python3 wsjtx_queue.py --call K6C --profile ses
```

Demo mode, with no radio needed:

```sh
python3 wsjtx_queue.py --call AK6IM --demo
```

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

Each release archive also includes `README.md`, `LICENSE`, and `docs/`.

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
./wsjtx-queue --call AK6IM
```

To download the standalone builds from GitHub, open the repository's
`Actions` tab, choose the latest successful `build` workflow run, and download
the artifact for your platform from the `Artifacts` section:

- `wsjtx-queue-windows`: contains `wsjtx-queue.exe` and `wsjtx-udp-hub.exe`.
- `wsjtx-queue-macos`: contains `wsjtx-queue` and `wsjtx-udp-hub`.
- `wsjtx-queue-linux`: contains `wsjtx-queue` and `wsjtx-udp-hub`.

Each artifact also includes `README.md`, `LICENSE`, and `docs/`. Actions
artifacts are best for testing unreleased builds. If you build locally with
PyInstaller instead of GitHub Actions, the standalone files are written under
`dist/`.

Deploy the current queue and UDP hub scripts to the sBitx test host:

```sh
make deploy-sbitx
```

Override the target if needed:

```sh
make deploy-sbitx SBITX_TARGET=pi@192.168.1.42:~
```

For an older transceiver/interface chain with less high-audio response, such as
a Kenwood TS-950S path that rolls off around 2.4 kHz:

```sh
python3 wsjtx_queue.py --call W6S --tx-max 2400
```

For contest/rate operating where your local log event is enough:

```sh
python3 wsjtx_queue.py --call AK6IM --profile arrl-digital --complete-on log-only
```

To prioritize a chase list in the caller queue and CQ/QRZ list:

```sh
python3 wsjtx_queue.py --call AK6IM --wanted wanted.txt
```

To enable WSJT-X control hotkeys:

```sh
python3 wsjtx_queue.py --call AK6IM --control
```

`--command` is accepted as an alias for `--control`.

To start in the CQ/QRZ list instead of the caller queue:

```sh
python3 wsjtx_queue.py --call AK6IM --view cqs
```

Or show both lists:

```sh
python3 wsjtx_queue.py --call AK6IM --view both
```

To start on the session worked-stations list:

```sh
python3 wsjtx_queue.py --call AK6IM --view worked
```

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
python3 wsjtx_queue.py --call AK6IM --port 2240
```

If you want a different fallback list, use `--ports`:

```sh
python3 wsjtx_queue.py --call AK6IM --ports 2237,2238,2240
```

## Quick Start With GridTracker Forwarding

If you already use GridTracker and have its UDP forwarding enabled, the simplest
setup is:

```text
WSJT-X -> GridTracker -> wsjtx_queue.py
```

For example, if GridTracker forwards WSJT-X UDP packets to `127.0.0.1:2238`,
you can usually run the queue without a port option; it will try `2237` first
and fall back to `2238` if `2237` is already in use:

```sh
python3 wsjtx_queue.py --call AK6IM
```

Do not add `--control` for the normal GridTracker-forwarding setup. Some
GridTracker configurations may pass control packets back to WSJT-X, but treat
that as an advanced choice. For club use, keeping the queue passive is less
surprising and leaves GridTracker as the control-capable app.

## UDP Hub

`wsjtx_udp_hub.py` is a small companion router for running multiple WSJT-X UDP
tools at once. It forwards packets from WSJT-X to named clients. Clients marked
`readonly` can only receive packets. Clients marked `control` can also send
control packets back to WSJT-X through the hub.

For normal club setups, keep `wsjtx_queue.py` listen-only and leave GridTracker
as the control-capable app. Most of the queue tool's useful behavior is passive,
and this avoids surprising operators who already rely on GridTracker control.

Example topology:

```text
WSJT-X -> 127.0.0.1:2237 wsjtx_udp_hub.py
hub    -> 127.0.0.1:2238 GridTracker
hub    -> 127.0.0.1:2240 wsjtx_queue.py
```

Run the hub:

```sh
python3 wsjtx_udp_hub.py \
  --listen 127.0.0.1:2237 \
  --client gridtracker=127.0.0.1:2238:control \
  --client queue=127.0.0.1:2240:readonly
```

Run the queue against the hub:

```sh
python3 wsjtx_queue.py --call AK6IM --port 2240
```

Configure WSJT-X UDP to send to `127.0.0.1:2237`. Configure GridTracker to use
`127.0.0.1:2238`. The queue listens on `127.0.0.1:2240`.

If you intentionally want the queue tool to set WSJT-X fields with `T` or
`Enter`, start the queue with `--control` and mark the queue client as
`control` in the hub. In that setup, make other clients `readonly` unless you
really want more than one app sending commands to WSJT-X.

For protocol details, see [WSJT-X UDP Protocol Notes](docs/wsjtx-udp-protocol.md).

## Profiles

Press these keys while the UI is running:

- `1`: `ses` - steady special-event queue; favors stations heard repeatedly,
  decent SNR, fresh decodes, and low time offset.
- `2`: `arrl-digital` - distance-first ranking for contests where QSO points
  depend on distance.
- `3`: `field-day` - favors quick/easy contacts: stronger SNR, reasonable
  audio frequency, and low time offset.
- `v`: cycle between caller queue, CQ/QRZ list, both lists, and worked list.
- `Up` / `Down`: select a CQ/QRZ row. Selection follows the callsign when rows
  re-rank.
- `Enter`: when started with `--control`, set WSJT-X `DX Call`, `DX Grid`,
  `Rx DF`, and `Generate Messages` from the selected CQ/QRZ station.
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

## Wanted Calls

Use `--wanted FILE` to mark and boost stations you are chasing, such as special
event stations, Museum Ships Weekend calls, W1AW portable stations, or contest
multipliers. Wanted stations are marked with `!` and receive a score boost in
both the caller queue and CQ/QRZ list.

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
the last `120` seconds. Useful options:

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

## License

This project is licensed under the GNU General Public License version 3.
This program interoperates with WSJT-X using its UDP message protocol. The
implementation was written independently and is not linked with WSJT-X.
If the GPL is an impediment to your use of this code, please contact AK6IM to
discuss alternate licensing.
