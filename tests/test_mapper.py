import unittest

from evdev import ecodes

from helpers import Event, g27_absinfo, load_config
import gip
from mapper import Mapper


def ev(etype, code, value):
    return Event(etype, code, value)


class TestMapper(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config()
        self.m = Mapper(self.cfg, g27_absinfo())

    def test_steering_full_lock_and_center(self):
        self.m.handle(ev(ecodes.EV_ABS, ecodes.ABS_X, 16383))
        self.assertGreater(self.m.state().lx, 32700)
        self.m.handle(ev(ecodes.EV_ABS, ecodes.ABS_X, 0))
        self.assertLess(self.m.state().lx, -32700)
        self.m.handle(ev(ecodes.EV_ABS, ecodes.ABS_X, 8191))
        self.assertLess(abs(self.m.state().lx), 50)

    def test_inverted_pedals(self):
        self.m.handle(ev(ecodes.EV_ABS, ecodes.ABS_Y, 0))      # Gas voll (invertiert)
        self.m.handle(ev(ecodes.EV_ABS, ecodes.ABS_RZ, 255))   # Bremse los
        st = self.m.state()
        self.assertEqual((st.rt, st.lt), (1023, 0))

    def test_clutch_as_button(self):
        self.m.handle(ev(ecodes.EV_ABS, ecodes.ABS_Z, 0))
        self.assertTrue(self.m.state().buttons & gip.BUTTONS["LB"])
        self.m.handle(ev(ecodes.EV_ABS, ecodes.ABS_Z, 255))
        self.assertFalse(self.m.state().buttons & gip.BUTTONS["LB"])

    def test_button_and_alias(self):
        # BTN_TRIGGER und BTN_JOYSTICK sind derselbe Code (288)
        self.m.handle(ev(ecodes.EV_KEY, ecodes.BTN_JOYSTICK, 1))
        self.assertTrue(self.m.state().buttons & gip.BUTTONS["A"])
        self.m.handle(ev(ecodes.EV_KEY, ecodes.BTN_TRIGGER, 0))
        self.assertFalse(self.m.state().buttons & gip.BUTTONS["A"])

    def test_dpad_from_hat(self):
        self.m.handle(ev(ecodes.EV_ABS, ecodes.ABS_HAT0X, -1))
        self.m.handle(ev(ecodes.EV_ABS, ecodes.ABS_HAT0Y, 1))
        b = self.m.state().buttons
        self.assertTrue(b & gip.BUTTONS["LEFT"] and b & gip.BUTTONS["DOWN"])

    def test_hshifter_pulses(self):
        self.cfg["hshifter"].update(enabled=True, gears={"BTN_BASE3": 1, "BTN_BASE5": 3})
        m = Mapper(self.cfg, g27_absinfo())
        m.handle(ev(ecodes.EV_KEY, ecodes.BTN_BASE5, 1))   # 1 -> 3 = zwei Hochschaltpulse
        ups, prev, t = 0, 0, 0.0
        for _ in range(100):
            m.tick(t)
            b = m.state().buttons & gip.BUTTONS["B"]
            ups += bool(b and not prev)
            prev, t = b, t + 0.01
        self.assertEqual(ups, 2)

    def test_invalid_target_rejected(self):
        self.cfg["buttons"] = {"BTN_TRIGGER": "Q"}
        with self.assertRaises(ValueError):
            Mapper(self.cfg, g27_absinfo())

    def test_debug_exposes_resolved_codes(self):
        d = self.m.debug()
        self.assertEqual(d["roles"]["steering"], ecodes.ABS_X)
        self.assertTrue(all(isinstance(e["code"], int) for e in d["map"]["buttons"]))
        self.assertNotIn(ecodes.ABS_HAT0X, [a["code"] for a in d["axes"]])


if __name__ == "__main__":
    unittest.main()
