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
        # NICHT erneut SET_CONFIGURATION senden, wenn der Kernel das Gerät schon konfiguriert hat:
        # Der Xbox-One-S-Controller (02ea, FW 3.01) nimmt danach genau ein Paket an und blockiert
        # dann alle weiteren Schreibzugriffe, bis er stromlos war (Errno 110). xpad macht es genauso.
        try:
            dev.get_active_configuration()
        except usb.core.USBError:
            dev.set_configuration()
        usb.util.claim_interface(dev, n)
        self.ep_in = usb.util.find_descriptor(
            intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
        self.ep_out = usb.util.find_descriptor(
            intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
        if not self.ep_in or not self.ep_out:
            raise RuntimeError("Endpunkte nicht gefunden")
        self._disable_audio(dev)
        self.dev, self.intf = dev, intf
        log.info("Controller %04x:%04x geöffnet (EP in 0x%02x, out 0x%02x)",
                 dev.idVendor, dev.idProduct, self.ep_in.bEndpointAddress, self.ep_out.bEndpointAddress)

    def _disable_audio(self, dev):
        """Audio-Interface (Nr. 1) auf Alt-Setting 0 schalten – wie der Linux-Treiber xpad.

        Ohne diesen SET_INTERFACE-Request bleibt z. B. der Xbox-One-S-Controller (02ea) im
        ANNOUNCE-Modus: Er nimmt genau ein Paket an, beantwortet es nicht und blockiert dann
        alle weiteren Schreibzugriffe. Am echten Xbox-Port schickt die Konsole diesen Request
        selbst; die Bridge reicht aber nur Interrupt-Daten durch, also übernehmen wir das hier.
        """
        try:
            cfg = dev.get_active_configuration()
            if not any(i.bInterfaceNumber == 1 for i in cfg):
                return
            try:
                if dev.is_kernel_driver_active(1):
                    dev.detach_kernel_driver(1)
            except (NotImplementedError, usb.core.USBError):
                pass
            usb.util.claim_interface(dev, 1)
            dev.set_interface_altsetting(interface=1, alternate_setting=0)
            log.info("Audio-Interface des Controllers deaktiviert (SET_INTERFACE 1/0)")
        except usb.core.USBError as e:
            log.warning("Audio-Interface nicht deaktivierbar: %s", e)

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

    def gip_reset(self):
        """Controller per GIP zurücksetzen (POWER 0x07, wie es auch die Xbox tut).

        Danach meldet er sich mit ANNOUNCE neu an. Bevorzugt gegenüber usb_reset():
        Ein USB-Reset bringt z. B. den Xbox-One-S-Controller (045e:02ea, FW 3.01) in einen
        Zustand, in dem er keine Daten mehr annimmt, bis er stromlos war.
        """
        ok = self.write(bytes([0x05, 0x20, 0x00, 0x01, 0x07]))
        log.info("GIP-Reset an Controller gesendet" if ok else "GIP-Reset fehlgeschlagen")
        return ok

    def usb_reset(self):
        """USB-Reset. NICHT im normalen Betrieb verwenden (siehe gip_reset)."""
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
