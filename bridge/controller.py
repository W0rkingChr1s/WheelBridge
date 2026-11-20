"""Echter Xbox-Controller am Pi (USB-Host) – dient nur als Auth-Partner."""
import logging
import threading
import time

import usb.core
import usb.util

log = logging.getLogger("controller")
_TIMEOUT_ERR = getattr(usb.core, "USBTimeoutError", ())


def _is_gip(intf):
    return (intf.bInterfaceClass, intf.bInterfaceSubClass, intf.bInterfaceProtocol) == (0xFF, 0x47, 0xD0)


class XboxController:
    def __init__(self, vid=0x045E, pid=None):
        self.vid = vid
        self.pid = pid
        self.dev = None
        self.intf = None
        self.ep_in = None
        self.ep_out = None
        self.lock = threading.Lock()

    def open(self, retries=10):
        last = None
        for _ in range(retries):
            try:
                self._open_once()
                return
            except Exception as e:      # noqa: BLE001 – Gerät evtl. noch nicht da
                last = e
                time.sleep(0.5)
        raise RuntimeError(f"Xbox-Controller nicht gefunden/öffnbar: {last}")

    def _open_once(self):
        kw = {"idVendor": self.vid}
        if self.pid:
            kw["idProduct"] = self.pid
        for dev in usb.core.find(find_all=True, **kw):
            for cfg in dev:
                for intf in cfg:
                    if _is_gip(intf) and intf.bAlternateSetting == 0:
                        self._claim(dev, intf)
                        return
        raise RuntimeError("kein GIP-Interface gefunden")

    def _claim(self, dev, intf):
        n = intf.bInterfaceNumber
        try:
            if dev.is_kernel_driver_active(n):
                dev.detach_kernel_driver(n)
                log.info("Kerneltreiber (xpad?) von Interface %d gelöst", n)
        except (NotImplementedError, usb.core.USBError):
            pass
        try:
            dev.set_configuration()
        except usb.core.USBError:
            pass   # schon konfiguriert
        usb.util.claim_interface(dev, n)
        self.ep_in = usb.util.find_descriptor(
            intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
        self.ep_out = usb.util.find_descriptor(
            intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
        if not self.ep_in or not self.ep_out:
            raise RuntimeError("Endpunkte nicht gefunden")
        self.dev, self.intf = dev, intf
        log.info("Controller %04x:%04x geöffnet (EP in 0x%02x, out 0x%02x)",
                 dev.idVendor, dev.idProduct, self.ep_in.bEndpointAddress, self.ep_out.bEndpointAddress)

    def ids(self):
        d = self.dev

        def s(attr):
            try:
                return getattr(d, attr)
            except Exception:   # noqa: BLE001
                return None
        return {"vid": d.idVendor, "pid": d.idProduct, "bcd": d.bcdDevice,
                "manufacturer": s("manufacturer"), "product": s("product"),
                "serial": s("serial_number")}

    def read(self, timeout_ms=100):
        dev = self.dev
        if dev is None:
            time.sleep(0.05)
            return None
        try:
            return bytes(dev.read(self.ep_in.bEndpointAddress, 64, timeout_ms))
        except _TIMEOUT_ERR:
            return None
        except usb.core.USBError as e:
            if e.errno == 110 or "timed out" in str(e).lower():
                return None
            if e.errno == 19:                 # ENODEV: abgesteckt
                log.warning("Controller getrennt")
                self.dev = None
                return None
            log.warning("Controller read: %s", e)
            time.sleep(0.1)
            return None

    def write(self, data):
        dev = self.dev
        if dev is None:
            return False
        try:
            dev.write(self.ep_out.bEndpointAddress, data, 200)
            return True
        except usb.core.USBError as e:
            log.warning("Controller write: %s", e)
            return False

    def reset(self):
        """USB-Reset -> Controller meldet sich frisch an (neues ANNOUNCE)."""
        with self.lock:
            dev, self.dev = self.dev, None
            if dev is not None:
                try:
                    dev.reset()
                except usb.core.USBError:
                    pass
                usb.util.dispose_resources(dev)
        time.sleep(1.0)
        self.open()
