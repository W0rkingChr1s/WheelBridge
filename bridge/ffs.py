"""FunctionFS-Endpunkt: der Pi gibt sich gegenüber der Xbox als GIP-Gerät aus.

Ein Interface (Vendor 0xFF / Subclass 0x47 / Protocol 0xD0) mit zwei
Interrupt-Endpunkten à 64 Byte, plus MS-OS-Descriptor "XGIP10" –
so meldet sich auch ein echter Xbox-One-Controller.
"""
import logging
import os
import struct
import threading
import time

log = logging.getLogger("ffs")

DESCRIPTORS_MAGIC_V2 = 3
STRINGS_MAGIC = 2
HAS_FS_DESC = 1
HAS_HS_DESC = 2
HAS_MS_OS_DESC = 8

EV_BIND, EV_UNBIND, EV_ENABLE, EV_DISABLE, EV_SETUP, EV_SUSPEND, EV_RESUME = range(7)
EV_NAMES = ["BIND", "UNBIND", "ENABLE", "DISABLE", "SETUP", "SUSPEND", "RESUME"]
EVENT_FMT = "<BBHHHB3x"          # usb_ctrlrequest (8) + type + pad = 12 Byte
EVENT_SIZE = struct.calcsize(EVENT_FMT)


def _intf():
    # bLength, bDescriptorType, bInterfaceNumber, bAlternateSetting,
    # bNumEndpoints, bInterfaceClass, bInterfaceSubClass, bInterfaceProtocol, iInterface
    return struct.pack("<BBBBBBBBB", 9, 4, 0, 0, 2, 0xFF, 0x47, 0xD0, 0)


def _ep(addr, interval):
    # bLength, bDescriptorType, bEndpointAddress, bmAttributes(Interrupt), wMaxPacketSize, bInterval
    return struct.pack("<BBBBHB", 7, 5, addr, 0x03, 64, interval)


def build_descriptors(fs_interval=4, hs_interval=4):
    fs = _intf() + _ep(0x81, fs_interval) + _ep(0x02, fs_interval)
    hs = _intf() + _ep(0x81, hs_interval) + _ep(0x02, hs_interval)

    # Extended Compat ID: bFirstInterfaceNumber, Reserved1(=1), CompatibleID, SubCompatibleID, Reserved2
    compat = struct.pack("<BB8s8s6s", 0, 1, b"XGIP10", b"", b"")
    # usb_os_desc_header (packed, 11 Byte): interface, dwLength, bcdVersion(=1), wIndex(4=ext compat), bCount, Reserved
    os_hdr = struct.pack("<BIHHBB", 0, 11 + len(compat), 1, 4, 1, 0)
    os_desc = os_hdr + compat

    counts = struct.pack("<III", 3, 3, 1)       # fs_count, hs_count, os_count
    body = counts + fs + hs + os_desc
    head = struct.pack("<III", DESCRIPTORS_MAGIC_V2, 12 + len(body),
                       HAS_FS_DESC | HAS_HS_DESC | HAS_MS_OS_DESC)
    return head + body


def build_strings():
    # keine Strings: magic, length, str_count, lang_count
    return struct.pack("<IIII", STRINGS_MAGIC, 16, 0, 0)


class FunctionFS:
    def __init__(self, mountpoint, on_enable=None, on_disable=None,
                 fs_interval=4, hs_interval=4):
        self.mountpoint = mountpoint
        self.on_enable = on_enable
        self.on_disable = on_disable
        self.running = True

        self.ep0 = os.open(f"{mountpoint}/ep0", os.O_RDWR)
        os.write(self.ep0, build_descriptors(fs_interval, hs_interval))
        os.write(self.ep0, build_strings())
        # ep1 = IN (Pi -> Xbox), ep2 = OUT (Xbox -> Pi); Reihenfolge wie in den Descriptors.
        # Blockierende IO wartet automatisch, bis der Host das Interface aktiviert.
        self.ep_in = os.open(f"{mountpoint}/ep1", os.O_RDWR)
        self.ep_out = os.open(f"{mountpoint}/ep2", os.O_RDWR)

        self._thread = threading.Thread(target=self._ep0_loop, name="ep0", daemon=True)
        self._thread.start()

    def _ep0_loop(self):
        while self.running:
            try:
                data = os.read(self.ep0, EVENT_SIZE * 4)
            except OSError as e:
                if not self.running:
                    break
                log.warning("ep0 read: %s", e)
                time.sleep(0.1)
                continue
            for off in range(0, len(data) - EVENT_SIZE + 1, EVENT_SIZE):
                rtype, req, wval, widx, wlen, etype = struct.unpack_from(EVENT_FMT, data, off)
                name = EV_NAMES[etype] if etype < len(EV_NAMES) else str(etype)
                if etype == EV_SETUP:
                    log.info("SETUP ungehandhabt: type=0x%02x req=0x%02x val=0x%04x idx=0x%04x len=%d -> STALL",
                             rtype, req, wval, widx, wlen)
                    self._stall(rtype)
                    continue
                log.info("FunctionFS-Event: %s", name)
                if etype == EV_ENABLE and self.on_enable:
                    self.on_enable()
                elif etype in (EV_DISABLE, EV_UNBIND, EV_SUSPEND) and self.on_disable:
                    self.on_disable()

    def _stall(self, rtype):
        # Stall = IO in die "falsche" Richtung
        try:
            if rtype & 0x80:
                os.read(self.ep0, 0)
            else:
                os.write(self.ep0, b"")
        except OSError:
            pass

    def write_in(self, data):
        return os.write(self.ep_in, data)

    def read_out(self):
        return os.read(self.ep_out, 64)

    def close(self):
        self.running = False
        for fd in (self.ep_in, self.ep_out, self.ep0):
            try:
                os.close(fd)
            except OSError:
                pass
