import base64
import importlib.util
import io
import json
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

QUEUE_SPEC = importlib.util.spec_from_file_location("wsjtx_queue", ROOT / "wsjtx_queue.py")
wsjtx_queue = importlib.util.module_from_spec(QUEUE_SPEC)
sys.modules["wsjtx_queue"] = wsjtx_queue
QUEUE_SPEC.loader.exec_module(wsjtx_queue)

REPLAY_SPEC = importlib.util.spec_from_file_location("wsjtx_udp_replay", ROOT / "wsjtx_udp_replay.py")
wsjtx_udp_replay = importlib.util.module_from_spec(REPLAY_SPEC)
sys.modules["wsjtx_udp_replay"] = wsjtx_udp_replay
REPLAY_SPEC.loader.exec_module(wsjtx_udp_replay)


class UdpReplayTests(unittest.TestCase):
    def test_parse_compact_alltxt_decode_line(self):
        decode = wsjtx_udp_replay.parse_alltxt_decode_line("102315 -10  0.2  632 ~  AK6IM 7M2VAP QM05")

        self.assertIsNotNone(decode)
        self.assertEqual("ALL.TXT", decode.client_id)
        self.assertEqual(10 * 3600 * 1000 + 23 * 60 * 1000 + 15 * 1000, decode.time_ms)
        self.assertEqual(-10, decode.snr)
        self.assertEqual(0.2, decode.dt_seconds)
        self.assertEqual(632, decode.audio_hz)
        self.assertEqual("FT8", decode.mode)
        self.assertEqual("AK6IM 7M2VAP QM05", decode.message)

    def test_parse_full_alltxt_decode_line_with_mode(self):
        decode = wsjtx_udp_replay.parse_alltxt_decode_line(
            "20260715_102330 14.074 Rx FT4 -06  0.3 1287 ~  CQ AB9QT EN55"
        )

        self.assertIsNotNone(decode)
        self.assertEqual("FT4", decode.mode)
        self.assertEqual("CQ AB9QT EN55", decode.message)
        self.assertEqual(1287, decode.audio_hz)

    def test_encode_decode_packet_round_trips_through_core_parser(self):
        decode = wsjtx_udp_replay.parse_alltxt_decode_line("102315 -10  0.2  632 ~  AK6IM 7M2VAP QM05")
        packet = wsjtx_udp_replay.encode_decode_packet(decode)

        msg_type, payload = wsjtx_queue.parse_packet(packet)

        self.assertEqual(wsjtx_queue.TYPE_DECODE, msg_type)
        self.assertEqual(decode, payload)

    def test_raw_recording_events_skip_header_and_decode_payload(self):
        packet = b"abc123"
        recording = io.StringIO(
            json.dumps({"format": "wsjtx-udp-record-v1", "started": 1.0})
            + "\n"
            + json.dumps({"t": 2.0, "data": base64.b64encode(packet).decode("ascii")})
            + "\n"
        )
        path = ROOT / "tests" / "_tmp-recording.jsonl"
        try:
            path.write_text(recording.getvalue(), encoding="utf-8")
            events = list(wsjtx_udp_replay.raw_recording_events(str(path)))
        finally:
            path.unlink(missing_ok=True)

        self.assertEqual(1, len(events))
        self.assertEqual(packet, events[0].data)


if __name__ == "__main__":
    unittest.main()
