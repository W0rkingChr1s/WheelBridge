"""G27 über evdev (Linux-Treiber hid-logitech / lg4ff) inkl. Force Feedback."""
import logging
import os

from evdev import InputDevice, ecodes, ff, list_devices

log = logging.getLogger("wheel")


class Wheel:
    def __init__(self, name_match="G27"):
        self.name_match = name_match
        self.dev = None
        self.absinfo = {}
        self.effect_id = None
        self._level = 0

    def open(self):
        self.effect_id = None
        self._level = 0
        for path in list_devices():
            d = InputDevice(path)
            if self.name_match.lower() in d.name.lower():
                self.dev = d
                break
            d.close()
        else:
            raise RuntimeError(f"Kein Eingabegerät mit '{self.name_match}' im Namen gefunden")
        caps = self.dev.capabilities(absinfo=True)
        self.absinfo = {code: info for code, info in caps.get(ecodes.EV_ABS, [])}
        self.has_ff = ecodes.EV_FF in caps
        log.info("Lenkrad: %s (%s), FFB=%s", self.dev.name, self.dev.path, self.has_ff)

    def _sysfs(self, attr):
        base = os.path.realpath(f"/sys/class/input/{os.path.basename(self.dev.path)}/device/device")
        return os.path.join(base, attr)

    def set_range(self, degrees):
        path = self._sysfs("range")
        if not os.path.exists(path):
            log.warning("Kein sysfs 'range' (%s) – Lenkwinkel nicht gesetzt", path)
            return
        with open(path, "w") as f:
            f.write(str(int(degrees)))
        log.info("Lenkwinkel auf %d° gesetzt", degrees)

    def set_gain(self, gain):
        if self.has_ff:
            self.dev.write(ecodes.EV_FF, ecodes.FF_GAIN, int(0xFFFF * max(0.0, min(1.0, gain))))

    def set_autocenter(self, strength):
        if self.has_ff:
            self.dev.write(ecodes.EV_FF, ecodes.FF_AUTOCENTER, int(0xFFFF * max(0.0, min(1.0, strength))))

    def _effect(self, level, eid):
        return ff.Effect(
            ecodes.FF_CONSTANT, eid, 0x4000,          # 0x4000 = 90° -> volle Kraft auf der Lenkachse
            ff.Trigger(0, 0),
            ff.Replay(0, 0),                          # length 0 = unendlich
            ff.EffectType(ff_constant_effect=ff.Constant(level, ff.Envelope(0, 0, 0, 0))),
        )

    def init_constant(self):
        if not self.has_ff:
            return
        self.effect_id = self.dev.upload_effect(self._effect(0, -1))
        self.dev.write(ecodes.EV_FF, self.effect_id, 1)

    def set_constant(self, level):
        """level -1.0 .. 1.0"""
        dev = self.dev
        if self.effect_id is None or dev is None:
            return
        lv = int(max(-1.0, min(1.0, level)) * 32767)
        if lv == self._level:
            return
        self._level = lv
        try:
            dev.upload_effect(self._effect(lv, self.effect_id))
        except OSError as e:
            log.debug("FFB-Update fehlgeschlagen: %s", e)

    def close(self):
        dev, self.dev = self.dev, None
        self.effect_id = None
        if dev:
            try:
                dev.write(ecodes.EV_FF, ecodes.FF_AUTOCENTER, 0)
            except OSError:
                pass
            try:
                dev.close()
            except OSError:
                pass
