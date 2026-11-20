"""USB-Gadget über configfs anlegen/abbauen (libcomposite + FunctionFS)."""
import logging
import os
import subprocess

log = logging.getLogger("gadget")
CONFIGFS = "/sys/kernel/config/usb_gadget"


def _w(path, value):
    with open(path, "w") as f:
        f.write(str(value))


class Gadget:
    def __init__(self, ids, cfg, name="wheelbridge", func="xbox"):
        self.ids = ids
        self.cfg = cfg
        self.func = func
        self.root = f"{CONFIGFS}/{name}"
        self.conf = f"{self.root}/configs/c.1"
        self.func_dir = f"{self.root}/functions/ffs.{func}"
        self.ffs_path = f"/dev/ffs-{func}"

    def setup(self):
        if not os.path.isdir(CONFIGFS):
            subprocess.run(["modprobe", "libcomposite"], check=True)
        if os.path.exists(self.root):
            log.info("Altes Gadget gefunden, räume auf")
            self.teardown()

        r = self.root
        os.makedirs(r)
        _w(f"{r}/idVendor", f"0x{self.ids['vid']:04x}")
        _w(f"{r}/idProduct", f"0x{self.ids['pid']:04x}")
        _w(f"{r}/bcdDevice", f"0x{self.ids['bcd']:04x}")
        _w(f"{r}/bcdUSB", "0x0200")
        _w(f"{r}/bDeviceClass", "0xff")
        _w(f"{r}/bDeviceSubClass", "0x47")
        _w(f"{r}/bDeviceProtocol", "0xd0")
        _w(f"{r}/bMaxPacketSize0", "64")

        os.makedirs(f"{r}/strings/0x409")
        _w(f"{r}/strings/0x409/manufacturer", self.ids.get("manufacturer") or "Microsoft")
        _w(f"{r}/strings/0x409/product", self.ids.get("product") or "Controller")
        _w(f"{r}/strings/0x409/serialnumber", self.ids.get("serial") or "0")

        os.makedirs(f"{self.conf}/strings/0x409")
        _w(f"{self.conf}/strings/0x409/configuration", "GIP")
        _w(f"{self.conf}/MaxPower", "500")
        _w(f"{self.conf}/bmAttributes", "0xa0")

        os.makedirs(self.func_dir)
        os.symlink(self.func_dir, f"{self.conf}/ffs.{self.func}")

        # MS-OS-Descriptor (String 0xEE "MSFT100", Vendor-Code 0x90) wie beim Original
        _w(f"{r}/os_desc/use", "1")
        _w(f"{r}/os_desc/b_vendor_code", "0x90")
        _w(f"{r}/os_desc/qw_sign", "MSFT100")
        os.symlink(self.conf, f"{r}/os_desc/c.1")

        speed = self.cfg.get("max_speed", "full-speed")
        if speed and os.path.exists(f"{r}/max_speed"):
            try:
                _w(f"{r}/max_speed", speed)
            except OSError as e:
                log.warning("max_speed=%s nicht gesetzt: %s", speed, e)

        os.makedirs(self.ffs_path, exist_ok=True)
        subprocess.run(["mount", "-t", "functionfs", self.func, self.ffs_path], check=True)
        log.info("Gadget angelegt, FunctionFS unter %s", self.ffs_path)

    def bind(self):
        udc = self.cfg.get("udc") or ""
        if not udc:
            udcs = os.listdir("/sys/class/udc")
            if not udcs:
                raise RuntimeError("Kein UDC gefunden – dtoverlay=dwc2,dr_mode=peripheral gesetzt und rebootet?")
            udc = udcs[0]
        _w(f"{self.root}/UDC", udc)
        log.info("Gadget an UDC %s gebunden", udc)

    def unbind(self):
        try:
            _w(f"{self.root}/UDC", "\n")
        except OSError:
            pass

    def teardown(self):
        r = self.root
        self.unbind()
        subprocess.run(["umount", self.ffs_path], stderr=subprocess.DEVNULL, check=False)
        for link in (f"{r}/os_desc/c.1", f"{self.conf}/ffs.{self.func}"):
            if os.path.islink(link):
                os.unlink(link)
        for d in (f"{self.conf}/strings/0x409", self.conf, self.func_dir,
                  f"{r}/strings/0x409", r):
            if os.path.isdir(d):
                try:
                    os.rmdir(d)
                except OSError as e:
                    log.warning("rmdir %s: %s", d, e)
