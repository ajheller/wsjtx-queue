import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("wsjtx_queue", ROOT / "wsjtx_queue.py")
wsjtx_queue = importlib.util.module_from_spec(SPEC)
sys.modules["wsjtx_queue"] = wsjtx_queue
SPEC.loader.exec_module(wsjtx_queue)


class QueueCoreTests(unittest.TestCase):
    def decode(self, message, snr=-10, audio_hz=1000):
        return wsjtx_queue.Decode("WSJT-X", True, 0, snr, 0.2, audio_hz, "FT8", message)

    def state(self, profile="log-or-73"):
        return wsjtx_queue.QueueState(
            "AK6IM", "CM87um", 180, 300, 2600, 10, 80, 120, profile, 600
        )

    def test_digit_first_callsign_is_queued(self):
        state = self.state()
        state.add_decode(self.decode("AK6IM 7M2VAP QM05"))

        self.assertEqual(["7M2VAP"], list(state.callers))

    def test_logged_call_is_removed_and_suppressed(self):
        state = self.state()
        state.add_decode(self.decode("AK6IM K1ABC R-10"))
        self.assertEqual(1, len(state.callers))

        state.remove_logged_call("K1ABC")
        state.add_decode(self.decode("AK6IM K1ABC R-10"))

        self.assertEqual(0, len(state.callers))
        self.assertTrue(state.is_worked("K1ABC"))
        self.assertEqual(["K1ABC"], [worked.call for worked in state.ranked_worked()])

    def test_worked_count_increments_on_duplicate_log(self):
        state = self.state()
        state.remove_logged_call("K1ABC")
        state.remove_logged_call("K1ABC")

        self.assertEqual(2, state.worked["K1ABC"].count)

    def test_final_73_removes_call(self):
        state = self.state()
        state.add_decode(self.decode("AK6IM K1ABC R-10"))
        state.add_decode(self.decode("AK6IM K1ABC 73"))

        self.assertEqual(0, len(state.callers))

    def test_cq_variants_are_listed(self):
        state = self.state()
        state.add_decode(self.decode("CQ POTA 7M2VAP QM05"))
        state.add_decode(self.decode("QRZ VE7DX CN89"))

        self.assertEqual(["7M2VAP", "VE7DX"], list(state.cqs))
        self.assertEqual(0, state.ignored_count)

    def test_arrl_digital_ranks_distant_cq_first(self):
        state = self.state()
        state.add_decode(self.decode("CQ K7ZZZ CN87", snr=1, audio_hz=900))
        state.add_decode(self.decode("CQ POTA 7M2VAP QM05", snr=-17, audio_hz=1200))

        ranked = [cq.call for _, cq in state.ranked_cqs("arrl-digital")]
        self.assertEqual("7M2VAP", ranked[0])

    def test_configure_packet_sets_only_rx_df(self):
        packet = wsjtx_queue.configure_rx_df_packet("WSJT-X", 2240)
        reader = wsjtx_queue.Reader(packet)

        self.assertEqual(wsjtx_queue.MAGIC, reader.u32())
        self.assertEqual(wsjtx_queue.SCHEMA, reader.u32())
        self.assertEqual(wsjtx_queue.TYPE_CONFIGURE, reader.u32())
        self.assertEqual("WSJT-X", reader.utf8())
        self.assertEqual("", reader.utf8())
        self.assertEqual(wsjtx_queue.MAX_U32, reader.u32())
        self.assertEqual("", reader.utf8())
        self.assertFalse(reader.bool())
        self.assertEqual(wsjtx_queue.MAX_U32, reader.u32())
        self.assertEqual(2240, reader.u32())

    def test_configure_dx_packet_sets_dx_and_generates_messages(self):
        station = wsjtx_queue.CqStation(
            "7M2VAP", 0, 0, -17, 0.2, 1200, "CQ POTA 7M2VAP QM05", "QM05"
        )
        packet = wsjtx_queue.configure_dx_packet("WSJT-X", station)
        reader = wsjtx_queue.Reader(packet)

        self.assertEqual(wsjtx_queue.MAGIC, reader.u32())
        self.assertEqual(wsjtx_queue.SCHEMA, reader.u32())
        self.assertEqual(wsjtx_queue.TYPE_CONFIGURE, reader.u32())
        self.assertEqual("WSJT-X", reader.utf8())
        self.assertEqual("", reader.utf8())
        self.assertEqual(wsjtx_queue.MAX_U32, reader.u32())
        self.assertEqual("", reader.utf8())
        self.assertFalse(reader.bool())
        self.assertEqual(wsjtx_queue.MAX_U32, reader.u32())
        self.assertEqual(1200, reader.u32())
        self.assertEqual("7M2VAP", reader.utf8())
        self.assertEqual("QM05", reader.utf8())
        self.assertTrue(reader.bool())


if __name__ == "__main__":
    unittest.main()
