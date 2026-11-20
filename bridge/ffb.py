"""Fake-FFB: Xbox-Rumble -> Vibration (Rechteck-Konstantkraft) am Lenkrad.

Die Zentrierfeder läuft separat über FF_AUTOCENTER im Lenkrad selbst.
Echtes, spielgesteuertes FFB gibt es im Gamepad-Modus nicht.
"""
import threading
import time


class FakeFFB(threading.Thread):
    def __init__(self, wheel, gain=0.4, hz=30):
        super().__init__(name="ffb", daemon=True)
        self.wheel = wheel
        self.gain = float(gain)
        self.half_period = 0.0
        self.set_hz(hz)
        self.amp = 0.0
        self._test_until = 0.0
        self._test_amp = 0.0
        self.running = True

    def set_hz(self, hz):
        self.half_period = 1.0 / (2.0 * max(1.0, float(hz)))

    def set_rumble(self, lt, rt, strong, weak):
        self.amp = self.gain * min(100, max(strong, weak)) / 100.0

    def pulse(self, amp, seconds):
        """Testvibration fürs Dashboard."""
        self._test_amp = amp
        self._test_until = time.monotonic() + seconds

    def run(self):
        phase = 1
        while self.running:
            amp = self._test_amp if time.monotonic() < self._test_until else self.amp
            if amp > 0.01:
                phase = -phase
                self.wheel.set_constant(amp * phase)
                time.sleep(self.half_period)
            else:
                self.wheel.set_constant(0.0)
                time.sleep(0.02)

    def stop(self):
        self.running = False
