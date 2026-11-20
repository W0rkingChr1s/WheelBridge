"""Übersetzt evdev-Events des Lenkrads in einen Xbox-Pad-Zustand."""
import logging
import threading
import time
from collections import deque

from evdev import ecodes

import gip

log = logging.getLogger("mapper")


def resolve_code(name):
    if isinstance(name, int):
        return name
    s = str(name).strip()
    if s.isdigit():
        return int(s)
    if s.lower().startswith("0x"):
        return int(s, 16)
    if s in ecodes.ecodes:
        return ecodes.ecodes[s]
    raise ValueError(f"Unbekannter evdev-Code: {s}")


def resolve_button(name):
    n = str(name).upper()
    if n not in gip.BUTTONS:
        raise ValueError(f"Unbekannter Xbox-Button: {name} (erlaubt: {', '.join(gip.BUTTONS)})")
    return gip.BUTTONS[n]


def _code_name(etype, code):
    n = ecodes.bytype.get(etype, {}).get(code, str(code))
    return n[0] if isinstance(n, (list, tuple)) else n


class Mapper:
    def __init__(self, cfg, absinfo):
        self.absinfo = absinfo
        self.lock = threading.Lock()

        st = cfg.get("steering", {})
        self.steer_code = resolve_code(st.get("axis", "ABS_X"))
        self.steer_invert = st.get("invert", False)
        self.steer_gamma = float(st.get("gamma", 1.0))
        self.steer_adz = float(st.get("anti_deadzone", 0.0))

        pd = cfg.get("pedals", {})
        self.pedals = {}
        for target in ("throttle", "brake", "clutch"):
            p = pd.get(target)
            if p and p.get("axis"):
                self.pedals[resolve_code(p["axis"])] = (target, p)
        cl = pd.get("clutch", {})
        self.clutch_mask = resolve_button(cl["button"]) if cl.get("button") else 0
        self.clutch_thr = float(cl.get("threshold", 0.5))

        dp = cfg.get("dpad", {})
        self.hat_x = resolve_code(dp["hat_x"]) if dp.get("hat_x") else None
        self.hat_y = resolve_code(dp["hat_y"]) if dp.get("hat_y") else None

        self.btn_entries = [{"key": str(k), "code": resolve_code(k), "target": str(v).upper()}
                            for k, v in cfg.get("buttons", {}).items()]
        for e in self.btn_entries:
            resolve_button(e["target"])          # validieren
        self.btn_map = {e["code"]: gip.BUTTONS[e["target"]] for e in self.btn_entries}

        hs = cfg.get("hshifter", {})
        self.hs_enabled = hs.get("enabled", False)
        self.gear_entries = [{"key": str(k), "code": resolve_code(k), "gear": int(v)}
                             for k, v in hs.get("gears", {}).items()]
        self.hs_gears = {e["code"]: e["gear"] for e in self.gear_entries} if self.hs_enabled else {}
        self.hs_up = resolve_button(hs.get("up", "B"))
        self.hs_down = resolve_button(hs.get("down", "X"))
        self.hs_pulse = hs.get("pulse_ms", 60) / 1000.0
        self.hs_gear = int(hs.get("initial_gear", 1))

        self.held = 0
        self.dpad = 0
        self.clutch_btn = 0
        self.lt = self.rt = self.lx = 0
        self.pulse = 0
        self.pulse_until = 0.0
        self.gap_until = 0.0
        self.pulse_queue = deque()

        # Rohdaten fürs Dashboard (Mapping-Assistent)
        self.raw_abs = {}
        self.raw_held = set()
        self.recent = deque(maxlen=8)
        self.roles = {"steering": self.steer_code}
        for code, (target, _p) in self.pedals.items():
            self.roles[target] = code

    # ---- Achsen ---------------------------------------------------------
    def _norm01(self, code, value, invert, deadzone=0.0):
        info = self.absinfo.get(code)
        if not info or info.max == info.min:
            return 0.0
        n = (value - info.min) / (info.max - info.min)
        if invert:
            n = 1.0 - n
        if n < deadzone:
            return 0.0
        return min(1.0, (n - deadzone) / (1.0 - deadzone)) if deadzone < 1 else 0.0

    def _steer(self, value):
        info = self.absinfo.get(self.steer_code)
        if not info:
            return 0
        half = (info.max - info.min) / 2.0
        n = (value - (info.min + half)) / half
        n = max(-1.0, min(1.0, -n if self.steer_invert else n))
        sign = 1 if n >= 0 else -1
        mag = abs(n) ** self.steer_gamma
        if mag > 0.002 and self.steer_adz > 0:
            mag = self.steer_adz + (1.0 - self.steer_adz) * mag
        return int(sign * mag * 32767)

    # ---- Events ---------------------------------------------------------
    def handle(self, ev):
        with self.lock:
            if ev.type == ecodes.EV_ABS:
                self.raw_abs[ev.code] = ev.value
                return self._abs(ev.code, ev.value)
            if ev.type == ecodes.EV_KEY and ev.value in (0, 1):
                if ev.value:
                    self.raw_held.add(ev.code)
                    self.recent.appendleft({"name": _code_name(ecodes.EV_KEY, ev.code),
                                            "code": ev.code, "t": time.time()})
                else:
                    self.raw_held.discard(ev.code)
                return self._key(ev.code, ev.value == 1)
        return False

    def _abs(self, code, value):
        if code == self.steer_code:
            self.lx = self._steer(value)
            return True
        if code in self.pedals:
            target, p = self.pedals[code]
            n = self._norm01(code, value, p.get("invert", False), float(p.get("deadzone", 0.0)))
            if target == "throttle":
                self.rt = int(n * 1023)
            elif target == "brake":
                self.lt = int(n * 1023)
            elif target == "clutch":
                self.clutch_btn = self.clutch_mask if (self.clutch_mask and n >= self.clutch_thr) else 0
            return True
        if code == self.hat_x:
            self.dpad &= ~(gip.BUTTONS["LEFT"] | gip.BUTTONS["RIGHT"])
            if value < 0:
                self.dpad |= gip.BUTTONS["LEFT"]
            elif value > 0:
                self.dpad |= gip.BUTTONS["RIGHT"]
            return True
        if code == self.hat_y:
            self.dpad &= ~(gip.BUTTONS["UP"] | gip.BUTTONS["DOWN"])
            if value < 0:
                self.dpad |= gip.BUTTONS["UP"]
            elif value > 0:
                self.dpad |= gip.BUTTONS["DOWN"]
            return True
        return False

    def _key(self, code, pressed):
        if code in self.hs_gears:
            if pressed:
                target = self.hs_gears[code]
                diff = target - self.hs_gear
                mask = self.hs_up if diff > 0 else self.hs_down
                self.pulse_queue.extend([mask] * abs(diff))
                log.debug("H-Shifter: Gang %d -> %d (%d Pulse)", self.hs_gear, target, abs(diff))
                self.hs_gear = target
            return False
        mask = self.btn_map.get(code)
        if mask is None:
            if pressed:
                log.info("Unbelegter Knopf: %s (%d)", _code_name(ecodes.EV_KEY, code), code)
            return False
        if pressed:
            self.held |= mask
        else:
            self.held &= ~mask
        return True

    # ---- Zustand --------------------------------------------------------
    def tick(self, now=None):
        """Treibt die Schaltpulse des H-Shifters (sequentiell) an."""
        now = time.monotonic() if now is None else now
        with self.lock:
            if self.pulse and now >= self.pulse_until:
                self.pulse = 0
                self.gap_until = now + self.hs_pulse
            elif not self.pulse and self.pulse_queue and now >= self.gap_until:
                self.pulse = self.pulse_queue.popleft()
                self.pulse_until = now + self.hs_pulse

    def debug(self):
        """Rohzustand + aufgelöste Belegung (Codes statt Alias-Namen) fürs Dashboard."""
        with self.lock:
            axes = []
            for code, info in sorted(self.absinfo.items()):
                if ecodes.ABS_HAT0X <= code <= ecodes.ABS_HAT3Y:
                    continue
                axes.append({"name": _code_name(ecodes.EV_ABS, code), "code": code,
                             "value": self.raw_abs.get(code, info.value),
                             "min": info.min, "max": info.max})
            return {
                "axes": axes,
                "roles": self.roles,
                "recent": list(self.recent),
                "held": sorted(self.raw_held),
                "map": {"buttons": self.btn_entries, "gears": self.gear_entries},
                "gear": self.hs_gear if self.hs_enabled else None,
            }

    def state(self):
        with self.lock:
            return gip.PadState(
                buttons=self.held | self.dpad | self.clutch_btn | self.pulse,
                lt=self.lt, rt=self.rt, lx=self.lx,
            )
