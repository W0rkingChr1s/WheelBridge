import unittest

from helpers import ROOT  # noqa: F401  (setzt sys.path)
import gip


class TestGip(unittest.TestCase):
    def test_input_roundtrip(self):
        st = gip.PadState(buttons=gip.BUTTONS["A"] | gip.BUTTONS["LB"], lt=512, rt=1023, lx=-20000, ly=100)
        pkt = gip.build_input(7, st)
        self.assertEqual(pkt[:4], bytes([0x20, 0x00, 7, 14]))
        parsed, flags, extra = gip.parse_input(pkt)
        self.assertEqual(parsed, st)
        self.assertEqual((flags, extra), (0, b""))

    def test_input_keeps_template_extra_bytes(self):
        pkt = gip.build_input(8, gip.PadState(), 0x00, b"\x01\x02")
        self.assertEqual(gip.parse_input(pkt)[2], b"\x01\x02")

    def test_values_are_clamped(self):
        pkt = gip.build_input(1, gip.PadState(lt=5000, rt=-5, lx=99999, ly=-99999))
        st = gip.parse_input(pkt)[0]
        self.assertEqual((st.lt, st.rt, st.lx, st.ly), (1023, 0, 32767, -32768))

    def test_rumble_parse_and_silence(self):
        pkt = bytes([0x09, 0x00, 3, 0x09, 0x00, 0x0F, 0, 0, 80, 40, 0xFF, 0x00, 0xEB])
        self.assertEqual(gip.parse_rumble(pkt), (0, 0, 80, 40))
        silent = gip.silence_rumble(pkt)
        self.assertEqual(gip.parse_rumble(silent), (0, 0, 0, 0))
        self.assertEqual(len(silent), len(pkt))

    def test_continuation_data_is_not_misread(self):
        # Länge passt nicht zur Transfergröße -> kein Input
        self.assertFalse(gip.is_simple(bytes([0x20, 0x00, 1, 14]) + b"\x00" * 30, gip.CMD_INPUT))
        # gechunkte Pakete werden nie als Input/Rumble interpretiert
        self.assertFalse(gip.is_simple(bytes([0x20, 0x80, 1, 14]) + b"\x00" * 14, gip.CMD_INPUT))

    def test_varint_length(self):
        pkt = gip.build_packet(0x06, 0x00, 1, b"\x00" * 200)
        cmd, _f, _s, length, hlen = gip.parse_header(pkt)
        self.assertEqual((cmd, length, hlen), (0x06, 200, 5))
        self.assertTrue(gip.is_simple(pkt, 0x06))

    def test_sequence_skips_zero(self):
        self.assertEqual(gip.next_seq(255), 1)
        self.assertEqual(gip.next_seq(1), 2)


if __name__ == "__main__":
    unittest.main()
