#!/usr/bin/env python3
"""WheelBridge – alte PC-Lenkräder an Xbox One/Series (Raspberry Pi 4).

  Xbox  <--USB-C (Gadget)-->  Pi  <--USB-A-->  echter Xbox-Controller (Auth)
                                   <--USB-A-->  Logitech G27

Xbox <-> Controller: alles roh durchreichen (Announce, Identify, Auth, ACKs ...)
Ausnahmen: Controller-INPUT wird durch Lenkraddaten ersetzt/gemischt,
           Xbox-RUMBLE wird abgezweigt und aufs Lenkrad gegeben.

Ein Supervisor-Thread bringt die Hardware hoch, sobald sie da ist –
das Dashboard läuft also auch, wenn noch nichts angesteckt ist.
"""
import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict

try:
    import tomllib
except ModuleNotFoundError:   # Python < 3.11
    sys.exit("Python >= 3.11 nötig (tomllib). Raspberry Pi OS Bookworm erfüllt das.")

import gip
from controller import XboxController
from ffb import FakeFFB
from ffs import FunctionFS
from gadget import Gadget
from mapper import Mapper
from web import RingLog, start_web
from wheel import Wheel

log = logging.getLogger("bridge")

# Diese Tabellen werden beim Speichern komplett ersetzt statt gemischt,
# sonst ließen sich einzelne Belegungen nie entfernen.
REPLACE_KEYS = {"buttons", "gears"}


def deep_merge(base, patch):
    out = dict(base)
    for k, v in patch.items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict) and k not in REPLACE_KEYS:
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Sniffer:
    def __init__(self, path):
        self.f = open(path, "a", buffering=1) if path else None
        self.lock = threading.Lock()
        self.t0 = time.monotonic()

    def __call__(self, direction, pkt, note=""):
        if not self.f:
            return
        with self.lock:
            self.f.write(f"{time.monotonic() - self.t0:9.4f} {direction} {gip.describe(pkt)} {note}\n")


class Bridge:
    def __init__(self, base_cfg, settings_path=None, sniff_path=None):
        self.base_cfg = base_cfg
        self.settings_path = settings_path
        self.overrides = {}
        if settings_path and os.path.exists(settings_path):
            try:
                with open(settings_path) as f:
                    self.overrides = json.load(f)
            except (OSError, ValueError) as e:
                log.warning("settings.json ignoriert: %s", e)
        self.cfg = deep_merge(base_cfg, self.overrides)
        self.sniff = Sniffer(sniff_path)

        c = self.cfg.get("controller", {})
        self.ctrl = XboxController(vid=c.get("vid", 0x045E), pid=c.get("pid"))
        self.wheel = Wheel(self.cfg.get("wheel", {}).get("name_match", "G27"))
        self.ffb = FakeFFB(self.wheel)
        self.mapper = None
        self.gadget = None
        self.ffs = None
        self.ids = None

        self.running = True
        self.enabled = False
        self.armed = False
        self.auth_seen = False
        self.last_auth = 0.0
        self.need_reset = threading.Event()
        self.cv = threading.Condition()
        self.dirty = False
        self.console_lock = threading.Lock()
        self.cfg_lock = threading.Lock()
        self.input_seq = 0
        self.ctrl_state = gip.PadState()
        self.ctrl_flags = 0x00
        self.ctrl_extra = b""

        self.t_start = time.monotonic()
        self.errors = {"controller": None, "wheel": None, "gadget": None}
        self.stats = {k: 0 for k in ("x2c", "c2x", "inj", "auth", "rumble", "ctrl_in")}
        self._checks, self._checks_t = {}, 0.0
        self._load_params()

    # ---- Konfiguration --------------------------------------------------
    def _load_params(self):
        c = self.cfg.get("controller", {})
        self.merge = c.get("merge_inputs", True)
        self.reset_on_enable = c.get("reset_on_enable", True)
        rep = self.cfg.get("report", {})
        self.min_interval = rep.get("min_interval_ms", 4) / 1000.0
        self.arm_after_auth = float(rep.get("arm_after_auth_s", 3.0))
        f = self.cfg.get("ffb", {})
        self.silence_rumble = f.get("silence_controller_rumble", True)
        self.ffb.gain = float(f.get("rumble_gain", 0.4))
        self.ffb.set_hz(f.get("rumble_hz", 30))

    def _apply_wheel(self):
        w = self.cfg.get("wheel", {})
        if w.get("steering_degrees"):
            self.wheel.set_range(w["steering_degrees"])
        self.wheel.set_gain(w.get("gain", 1.0))
        self.wheel.set_autocenter(w.get("autocenter", 0.35))
        if self.wheel.effect_id is None:
            self.wheel.init_constant()

    def update_settings(self, patch):
        with self.cfg_lock:
            new_over = deep_merge(self.overrides, patch)
            new_cfg = deep_merge(self.base_cfg, new_over)
            absinfo = self.wheel.absinfo if self.wheel.dev else {}
            new_mapper = Mapper(new_cfg, absinfo)       # validiert; wirft bei Unsinn
            self.overrides, self.cfg = new_over, new_cfg
            self._save_overrides()
            self._load_params()
            if self.wheel.dev:
                self._apply_wheel()
                self.mapper = new_mapper
        log.info("Einstellungen übernommen: %s", ", ".join(patch) or "-")

    def reset_settings(self):
        with self.cfg_lock:
            self.overrides = {}
            self.cfg = deep_merge(self.base_cfg, {})
            if self.settings_path and os.path.exists(self.settings_path):
                os.remove(self.settings_path)
            self._load_params()
            if self.wheel.dev:
                self._apply_wheel()
                self.mapper = Mapper(self.cfg, self.wheel.absinfo)
        log.info("Einstellungen auf config.toml zurückgesetzt")

    def _save_overrides(self):
        if not self.settings_path:
            return
        tmp = self.settings_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.overrides, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.settings_path)

    # ---- Lebenszyklus ---------------------------------------------------
    def start(self):
        self.ffb.start()
        for target, name in ((self._supervisor, "supervisor"), (self._wheel_loop, "wheel"),
                             (self._sender_loop, "sender")):
            threading.Thread(target=target, name=name, daemon=True).start()

    def _supervisor(self):
        while self.running:
            # Lenkrad (unabhängig vom Rest)
            if self.wheel.dev is None:
                try:
                    self.wheel.open()
                    with self.cfg_lock:
                        self._apply_wheel()
                        self.mapper = Mapper(self.cfg, self.wheel.absinfo)
                    self.errors["wheel"] = None
                except Exception as e:   # noqa: BLE001
                    self._err("wheel", e)

            # Controller + Gadget: das Gadget klont die Controller-Identität
            if self.ffs is None:
                try:
                    if self.ctrl.dev is None:
                        self.ctrl.open(retries=1)
                        self.ids = self.ctrl.ids()
                        log.info("Klone Controller-Identität: %04x:%04x bcd=%04x '%s'",
                                 self.ids["vid"], self.ids["pid"], self.ids["bcd"], self.ids.get("product"))
                    self.errors["controller"] = None
                except Exception as e:   # noqa: BLE001
                    self._err("controller", e)
                if self.ctrl.dev is not None:
                    self._setup_gadget()
            time.sleep(1)

    def _setup_gadget(self):
        g = self.cfg.get("gadget", {})
        try:
            self.gadget = Gadget(self.ids, g)
            self.gadget.setup()
            ffs = FunctionFS(self.gadget.ffs_path, self._on_enable, self._on_disable,
                             g.get("fs_interval", 4), g.get("hs_interval", 4))
            try:
                self.gadget.bind()
            except Exception:
                ffs.close()
                raise
            self.ffs = ffs
            self.errors["gadget"] = None
            threading.Thread(target=self._console_to_ctrl, name="x2c", daemon=True).start()
            threading.Thread(target=self._ctrl_to_console, name="c2x", daemon=True).start()
            log.info("Bereit – Pi jetzt per USB-C mit der Xbox verbinden")
        except Exception as e:   # noqa: BLE001
            self._err("gadget", e)
            if self.gadget:
                try:
                    self.gadget.teardown()
                except Exception:   # noqa: BLE001
                    pass
            self.gadget = None
            time.sleep(4)

    def _err(self, part, e):
        msg = str(e)
        if self.errors.get(part) != msg:
            log.warning("%s: %s", part, msg)
        self.errors[part] = msg

    def stop(self):
        self.running = False
        self._notify()
        self.ffb.stop()
        if self.ffs:
            self.ffs.close()
        if self.gadget:
            self.gadget.teardown()
        self.wheel.close()

    # ---- FunctionFS-Callbacks --------------------------------------------
    def _on_enable(self):
        self.enabled = True
        self.armed = False
        self.auth_seen = False
        if self.reset_on_enable:
            self.need_reset.set()

    def _on_disable(self):
        self.enabled = False
        self.armed = False

    # ---- Helfer ---------------------------------------------------------
    def _notify(self):
        with self.cv:
            self.dirty = True
            self.cv.notify()

    def _write_console(self, pkt):
        with self.console_lock:
            try:
                self.ffs.write_in(pkt)
                return True
            except OSError as e:
                log.debug("write Xbox: %s", e)
                return False

    def _arm(self, why):
        if not self.armed:
            self.armed = True
            log.info("Input-Injektion aktiv (%s)", why)

    def test_rumble(self):
        threading.Thread(target=self.ffb.pulse, args=(max(self.ffb.gain, 0.4), 1.0), daemon=True).start()

    # ---- Xbox -> Controller ---------------------------------------------
    def _console_to_ctrl(self):
        while self.running:
            try:
                pkt = self.ffs.read_out()
            except OSError:
                time.sleep(0.05)
                continue
            if not pkt:
                continue
            self.stats["x2c"] += 1
            note = ""
            if pkt[0] == gip.CMD_AUTH:
                self.auth_seen, self.last_auth = True, time.monotonic()
                self.stats["auth"] += 1
            r = gip.parse_rumble(pkt)
            if r:
                self.stats["rumble"] += 1
                self.ffb.set_rumble(*r)
                if self.silence_rumble:
                    pkt = gip.silence_rumble(pkt)
                    note = "(Rumble -> Lenkrad)"
            self.sniff("X>C", pkt, note)
            self.ctrl.write(pkt)

    # ---- Controller -> Xbox ---------------------------------------------
    def _ctrl_to_console(self):
        while self.running:
            if self.need_reset.is_set():
                self.need_reset.clear()
                log.info("Controller-Reset für frische Anmeldung")
                try:
                    self.ctrl.reset()
                    self.errors["controller"] = None
                except Exception as e:   # noqa: BLE001
                    self._err("controller", e)
                    time.sleep(1)
                    self.need_reset.set()
                continue
            if self.ctrl.dev is None:            # abgesteckt -> neu suchen
                try:
                    self.ctrl.open(retries=1)
                    self.errors["controller"] = None
                except Exception as e:   # noqa: BLE001
                    self._err("controller", e)
                    time.sleep(1)
                continue
            pkt = self.ctrl.read(100)
            if not pkt:
                continue
            if pkt[0] == gip.CMD_AUTH:
                self.auth_seen, self.last_auth = True, time.monotonic()
                self.stats["auth"] += 1
            parsed = gip.parse_input(pkt)
            if parsed:
                self.stats["ctrl_in"] += 1
                self.ctrl_state, self.ctrl_flags, self.ctrl_extra = parsed
                self.sniff("C>.", pkt, "(Input abgefangen)")
                if self.enabled:
                    self._arm("Controller-Input gesehen")
                self._notify()
                continue
            self.stats["c2x"] += 1
            self.sniff("C>X", pkt)
            if self.enabled:
                self._write_console(pkt)

    # ---- Lenkrad --------------------------------------------------------
    def _wheel_loop(self):
        while self.running:
            dev = self.wheel.dev
            if dev is None or self.mapper is None:
                time.sleep(0.2)
                continue
            try:
                for ev in dev.read_loop():
                    if not self.running:
                        return
                    m = self.mapper
                    if m and m.handle(ev):
                        self._notify()
            except OSError as e:
                log.error("Lenkrad getrennt: %s", e)
                self.mapper = None
                self.wheel.close()

    # ---- Report-Sender --------------------------------------------------
    def _compose(self):
        m = self.mapper
        w = m.state() if m else gip.PadState()
        if not self.merge:
            return w
        c = self.ctrl_state
        return gip.PadState(
            buttons=w.buttons | c.buttons,
            lt=max(w.lt, c.lt), rt=max(w.rt, c.rt),
            lx=w.lx if abs(w.lx) >= abs(c.lx) else c.lx,
            ly=c.ly, rx=c.rx, ry=c.ry,
        )

    def _sender_loop(self):
        last, last_sent = None, 0.0
        while self.running:
            with self.cv:
                self.cv.wait_for(lambda: self.dirty or not self.running, timeout=0.01)
                self.dirty = False
            now = time.monotonic()
            m = self.mapper
            if m:
                m.tick(now)
            if self.enabled and not self.armed and self.auth_seen and now - self.last_auth > self.arm_after_auth:
                self._arm("Auth-Austausch abgeschlossen (Heuristik)")
            if not (self.enabled and self.armed and self.ffs):
                last = None
                continue
            wait = self.min_interval - (now - last_sent)
            if wait > 0:
                time.sleep(wait)
            st = self._compose()
            key = (st.as_tuple(), self.ctrl_flags, self.ctrl_extra)
            if key == last:
                continue
            self.input_seq = gip.next_seq(self.input_seq)
            pkt = gip.build_input(self.input_seq, st, self.ctrl_flags, self.ctrl_extra)
            if self._write_console(pkt):
                self.stats["inj"] += 1
                last, last_sent = key, time.monotonic()
                self.sniff("P>X", pkt)

    # ---- Status fürs Dashboard ------------------------------------------
    def _stage(self):
        if self.armed:
            return "Aktiv – Lenkrad steuert"
        if self.enabled and self.auth_seen:
            return "Handshake läuft"
        if self.enabled:
            return "Xbox verbunden – warte auf Handshake"
        if self.ffs:
            return "Bereit – mit Xbox verbinden"
        if self.ctrl.dev is None:
            return "Warte auf Xbox-Controller"
        return "Starte …"

    def checks(self):
        now = time.monotonic()
        if now - self._checks_t < 2:
            return self._checks
        c = {"root": os.geteuid() == 0, "xpad_loaded": os.path.isdir("/sys/module/xpad")}
        try:
            c["udc"] = bool(os.listdir("/sys/class/udc"))
        except OSError:
            c["udc"] = False
        c["undervoltage_now"] = c["undervoltage_boot"] = None
        try:
            out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True,
                                 text=True, timeout=1).stdout
            val = int(out.strip().split("=")[1], 16)
            c["undervoltage_now"] = bool(val & 0x1)
            c["undervoltage_boot"] = bool(val & 0x10000)
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            pass
        self._checks, self._checks_t = c, now
        return c

    def status(self):
        m = self.mapper
        wd = self.wheel.dev
        ids = self.ids
        return {
            "uptime": int(time.monotonic() - self.t_start),
            "stage": self._stage(),
            "errors": self.errors,
            "checks": self.checks(),
            "controller": {
                "connected": self.ctrl.dev is not None,
                "ids": f"{ids['vid']:04x}:{ids['pid']:04x} {ids.get('product') or ''}".strip() if ids else None,
            },
            "wheel": {"connected": wd is not None, "name": wd.name if wd else None,
                      "ffb": bool(getattr(self.wheel, "has_ff", False))},
            "gadget": self.ffs is not None,
            "xbox": {"enabled": self.enabled, "auth_seen": self.auth_seen, "armed": self.armed},
            "stats": self.stats,
            "pad": asdict(self._compose()),
            "raw": m.debug() if m else None,
            "rumble": round(self.ffb.amp, 3),
        }


def main():
    ap = argparse.ArgumentParser(description="WheelBridge")
    ap.add_argument("-c", "--config", default="config.toml")
    ap.add_argument("--settings", help="Datei für Dashboard-Änderungen (Standard: settings.json neben der Config)")
    ap.add_argument("--sniff", metavar="DATEI", help="alle GIP-Pakete in DATEI protokollieren")
    ap.add_argument("--port", type=int, help="Port des Dashboards (überschreibt [web] port)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    fmt = logging.Formatter("%(asctime)s %(name)-10s %(levelname)-7s %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if args.verbose else logging.INFO)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    ring = RingLog()
    ring.setFormatter(fmt)
    root.addHandler(console)
    root.addHandler(ring)

    with open(args.config, "rb") as f:
        cfg = tomllib.load(f)
    settings = args.settings or os.path.join(os.path.dirname(os.path.abspath(args.config)), "settings.json")

    bridge = Bridge(cfg, settings, args.sniff)
    web = cfg.get("web", {})
    if web.get("enabled", True):
        start_web(bridge, ring, web.get("bind", "0.0.0.0"), args.port or web.get("port", 8080))

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        bridge.start()
        stop.wait()
    finally:
        log.info("Beende …")
        bridge.stop()


if __name__ == "__main__":
    main()
