import struct
import unittest

from helpers import ROOT  # noqa: F401
import ffs


class TestDescriptors(unittest.TestCase):
    def test_header_and_length(self):
        blob = ffs.build_descriptors()
        magic, length, flags = struct.unpack_from("<III", blob)
        self.assertEqual(magic, ffs.DESCRIPTORS_MAGIC_V2)
        self.assertEqual(length, len(blob))
        self.assertEqual(flags, ffs.HAS_FS_DESC | ffs.HAS_HS_DESC | ffs.HAS_MS_OS_DESC)
        self.assertEqual(struct.unpack_from("<III", blob, 12), (3, 3, 1))

    def test_gip_interface_and_endpoints(self):
        blob = ffs.build_descriptors(fs_interval=4)
        intf = blob[24:33]
        self.assertEqual(tuple(intf[5:8]), (0xFF, 0x47, 0xD0))   # Xbox-One-GIP-Klasse
        ep_in, ep_out = blob[33:40], blob[40:47]
        self.assertEqual((ep_in[2], ep_in[3]), (0x81, 0x03))     # IN, Interrupt
        self.assertEqual((ep_out[2], ep_out[3]), (0x02, 0x03))   # OUT, Interrupt
        self.assertEqual(struct.unpack_from("<H", ep_in, 4)[0], 64)

    def test_ms_os_compat_id(self):
        blob = ffs.build_descriptors()
        self.assertIn(b"XGIP10\x00\x00", blob)
        os_hdr = blob[-35:-24]
        _intf, dw_len, bcd, windex, count, _r = struct.unpack("<BIHHBB", os_hdr)
        self.assertEqual((dw_len, bcd, windex, count), (35, 1, 4, 1))

    def test_strings_blob(self):
        self.assertEqual(struct.unpack("<IIII", ffs.build_strings()), (ffs.STRINGS_MAGIC, 16, 0, 0))


if __name__ == "__main__":
    unittest.main()
