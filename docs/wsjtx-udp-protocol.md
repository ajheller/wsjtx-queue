# WSJT-X UDP Protocol Notes

These notes summarize the UDP protocol used by WSJT-X and, as far as this
project has verified, WSJT-X Improved. They are intended for operators and
developers working on `wsjtx_queue.py` and `wsjtx_udp_hub.py`, not as a
replacement for the upstream source.

Primary references:

- WSJT-X `Network/NetworkMessage.hpp` in the official SourceForge tree:
  <https://sourceforge.net/p/wsjt/wsjtx/ci/master/tree/Network/NetworkMessage.hpp>
- WSJT-X user-facing download/documentation site:
  <https://wsjt.sourceforge.io/wsjtx.html>

## Transport Model

WSJT-X sends UDP datagrams to the configured reporting host and port. A helper
program can receive those datagrams and, for supported message types, send UDP
datagrams back to WSJT-X.

Typical local setup:

```text
WSJT-X UDP server -> 127.0.0.1:2237 -> client app
```

For more than one client, use WSJT-X multicast, WSJT-X secondary forwarding if
available, GridTracker forwarding, or a UDP fan-out helper such as
`wsjtx_udp_hub.py`.

WSJT-X identifies each running instance with an `Id` string. Control packets
sent back to WSJT-X should use the target instance's `Id`. This project learns
that value from incoming packets and uses it when `--control` is enabled.

## Packet Framing

All WSJT-X UDP messages are serialized with Qt `QDataStream`.

Every packet begins with:

| Field | Type | Notes |
| --- | --- | --- |
| Magic number | `quint32` | Always `0xadbccbda` |
| Schema number | `quint32` | Current WSJT-X schema is `3` |
| Message type | `quint32` | See message table below |

Important encoding details:

- Integer fields are big-endian.
- Floating point values are 64-bit IEEE doubles.
- `utf8` strings are encoded like a Qt `QByteArray`: a 32-bit byte length,
  followed by that many UTF-8 bytes. No NUL terminator is included.
- A null string is encoded with length `0xffffffff`; an empty string is encoded
  with length `0`.
- WSJT-X schema 3 corresponds to Qt 5.4 stream encoding.
- New fields may be added to the end of existing packet types. Readers should
  ignore extra trailing bytes.
- New message types may be added. Readers should ignore message types they do
  not recognize.

## Message Types

Direction is from WSJT-X's point of view:

- `Out`: WSJT-X sends this to UDP clients.
- `In`: a UDP client may send this to WSJT-X.

| Type | Name | Direction | Purpose |
| ---: | --- | --- | --- |
| 0 | Heartbeat | Out/In | Presence and schema negotiation |
| 1 | Status | Out | Current WSJT-X state |
| 2 | Decode | Out | New or replayed decode |
| 3 | Clear | Out/In | Band activity/Rx frequency clear notice or request |
| 4 | Reply | In | Act on a prior CQ/QRZ decode, like double-clicking it |
| 5 | QSO Logged | Out | Structured QSO log notification |
| 6 | Close | Out/In | Graceful shutdown notice or request |
| 7 | Replay | In | Ask WSJT-X to resend current band activity decodes |
| 8 | Halt Tx | In | Stop current or automatic transmit |
| 9 | Free Text | In | Set/send the free-text message |
| 10 | WSPR Decode | Out | WSPR decode notification |
| 11 | Location | In | Temporarily set operating grid/location |
| 12 | Logged ADIF | Out | ADIF log notification |
| 13 | Highlight Callsign | In | Highlight calls in the band activity window |
| 14 | Switch Configuration | In | Switch to a named WSJT-X configuration |
| 15 | Configure | In | Set selected operating fields |
| 16 | Annotation Info | In | Annotate/sort Fox-mode hound callers |

## Messages This Project Uses

### Heartbeat, Type 0, Out/In

Fields:

| Field | Type | Notes |
| --- | --- | --- |
| Id | `utf8` | Unique instance key |
| Maximum schema number | `quint32` | Added with schema 3 |
| Version | `utf8` | WSJT-X version |
| Revision | `utf8` | Source revision |

`wsjtx_queue.py` currently uses the `Id` so it can send control packets to the
right WSJT-X instance.

### Status, Type 1, Out

Status includes dial frequency, mode, DX call/grid, report, transmit state,
decode state, Rx DF, Tx DF, station call/grid, special activity mode, frequency
tolerance, T/R period, configuration name, and current Tx message.

`wsjtx_queue.py` parses the current DX call/grid plus Rx DF and Tx DF. TX
frequency suggestions prefer the current WSJT-X DX call and Rx DF when present,
so changing the DX station in WSJT-X or GridTracker updates the target bias.

### Decode, Type 2, Out

Fields:

| Field | Type | Notes |
| --- | --- | --- |
| Id | `utf8` | Unique instance key |
| New | `bool` | True for a fresh decode, false for replay |
| Time | `QTime` | Decode time |
| SNR | `qint32` | Signal-to-noise report |
| Delta time | `double` | Seconds |
| Delta frequency | `quint32` | Audio frequency in Hz |
| Mode | `utf8` | FT8, FT4, etc. |
| Message | `utf8` | Decoded text |
| Low confidence | `bool` | Protocol-dependent warning |
| Off air | `bool` | Decode came from playback rather than RF |

`wsjtx_queue.py` uses Decode packets to:

- find stations calling the active callsign;
- find CQ/QRZ stations;
- track recent occupied audio frequencies;
- remove callers when a decoded final `73`/`RR73` matches the completion
  policy.

### Clear, Type 3, Out/In

Outbound from WSJT-X, this means prior Decode messages have been discarded.
`wsjtx_queue.py` clears its active caller queue when it sees this.

Inbound to WSJT-X, it can clear one or both windows:

| Window | Meaning |
| ---: | --- |
| 0 | Band Activity |
| 1 | Rx Frequency |
| 2 | Both windows |

### QSO Logged, Type 5, Out

Fields include:

| Field | Type |
| --- | --- |
| Id | `utf8` |
| Date & Time Off | `QDateTime` |
| DX call | `utf8` |
| DX grid | `utf8` |
| Tx frequency | `quint64` |
| Mode | `utf8` |
| Report sent | `utf8` |
| Report received | `utf8` |
| Tx power | `utf8` |
| Comments | `utf8` |
| Name | `utf8` |
| Date & Time On | `QDateTime` |
| Operator call | `utf8` |
| My call | `utf8` |
| My grid | `utf8` |
| Exchange sent | `utf8` |
| Exchange received | `utf8` |
| ADIF propagation mode | `utf8` |

WSJT-X sends this when the operator accepts the Log QSO dialog.

### Logged ADIF, Type 12, Out

Fields:

| Field | Type | Notes |
| --- | --- | --- |
| Id | `utf8` | Unique instance key |
| ADIF text | `utf8` | Complete one-record ADIF document |

WSJT-X also sends this when the operator accepts the Log QSO dialog. This
project parses the ADIF `CALL` field to remove the station from the queue and
mark it worked.

### Configure, Type 15, In

Fields:

| Field | Type | No-change value |
| --- | --- | --- |
| Id | `utf8` | Required target id |
| Mode | `utf8` | Empty string |
| Frequency Tolerance | `quint32` | `0xffffffff` |
| Submode | `utf8` | Empty string |
| Fast Mode | `bool` | No explicit no-change marker |
| T/R Period | `quint32` | `0xffffffff` |
| Rx DF | `quint32` | `0xffffffff` |
| DX Call | `utf8` | Empty string |
| DX Grid | `utf8` | Empty string |
| Generate Messages | `bool` | No explicit no-change marker |

Invalid or unrecognized values are silently ignored by WSJT-X. A mode/submode
change may also change frequency if the current frequency is not valid for the
new mode.

There is no no-change sentinel for `Fast Mode`; upstream WSJT-X applies the
boolean when the Fast control is visible. There is also no sentinel for
`Generate Messages`, but `false` means do not click the generate-messages
button.

`wsjtx_queue.py --control` uses Configure in two ways:

- `T` sends only `Rx DF`, leaving string fields empty and integer fields at
  `0xffffffff`.
- `Enter` in CQ mode sends `DX Call`, `DX Grid`, `Rx DF`, and
  `Generate Messages = true` for the top-ranked CQ/QRZ station.

Configure does not include a direct `Tx DF` field.

## Useful Messages Not Yet Used Here

### Reply, Type 4, In

Reply describes a prior Decode packet and asks WSJT-X to act as if the operator
double-clicked that CQ/QRZ decode in Band Activity. WSJT-X only acts if the
message exactly matches an earlier CQ or QRZ decode. This can be useful for
chasing stations, but it is intentionally not a general remote-control UI.

### Replay, Type 7, In

Replay asks WSJT-X to resend the current Band Activity decodes with `New =
false`, followed by a Status packet. This is useful when a helper starts after
WSJT-X and wants initial state.

### Halt Tx, Type 8, In

Halt Tx can stop transmission immediately or at the end of the current transmit
period, depending on the `Auto Tx Only` flag.

### Free Text, Type 9, In

Free Text sets or sends the current free-text/Tx5 message. The sender is
responsible for choosing legal message text.

### Location, Type 11, In

Location temporarily overrides the operating locator for the current session.
Upstream documentation says 4- or 6-character Maidenhead locators are accepted.

### Highlight Callsign, Type 13, In

Highlight Callsign lets an external app color matching callsigns in WSJT-X's
Band Activity panel. A special callsign of `CLEARALL!` clears stored highlight
instructions.

### Switch Configuration, Type 14, In

Switch Configuration changes WSJT-X to an existing named configuration.

### Annotation Info, Type 16, In

Annotation Info is intended for Fox-mode hound sorting/annotation. It can attach
a numeric sort order to a DX call.

## What UDP Does Not Expose

The upstream Configure packet can set `Rx DF`, but not `Tx DF`. WSJT-X sends
`Tx DF` in Status, so a helper can observe it, but there is no corresponding
direct setter in the documented UDP protocol.

The reviewed WSJT-X Improved builds preserve the WSJT-X UDP protocol shape for
the features this project uses. The improved-only Wait features, including Wait
and Reply, Wait and Call, and Wait and Pounce, were not found as documented UDP
commands. Treat those as GUI features unless future WSJT-X Improved source adds
explicit network messages for them.

The UDP API also does not act like a complete headless WSJT-X control surface.
Some operations can be requested, but normal operating decisions and transmit
enablement remain in the WSJT-X UI.

## Compatibility Guidance

When adding packet support:

- Parse only the fields you need.
- Ignore unknown message types.
- Ignore trailing bytes on known message types.
- Prefer Logged ADIF for log extraction when possible; it is easier to parse
  robustly than mixed binary QSO Logged fields.
- Use `0xffffffff` for integer no-change fields in Configure.
- Use empty strings for string no-change fields in Configure.
- Do not assume multicast, forwarding, and bidirectional control are all
  available in every operator's setup. Keep simple unicast examples available.
