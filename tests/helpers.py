"""Gemeinsame Test-Helfer: Pfad zu bridge/ und Fake-evdev-Strukturen."""
import os
import sys
from collections import namedtuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bridge"))

AbsInfo = namedtuple("AbsInfo", "value min max fuzz flat resolution")
Event = namedtuple("Event", "type code value")


def g27_absinfo():
    from evdev import ecodes
    return {
        ecodes.ABS_X: AbsInfo(8191, 0, 16383, 0, 0, 0),
        ecodes.ABS_Y: AbsInfo(255, 0, 255, 0, 0, 0),
        ecodes.ABS_Z: AbsInfo(255, 0, 255, 0, 0, 0),
        ecodes.ABS_RZ: AbsInfo(255, 0, 255, 0, 0, 0),
        ecodes.ABS_HAT0X: AbsInfo(0, -1, 1, 0, 0, 0),
        ecodes.ABS_HAT0Y: AbsInfo(0, -1, 1, 0, 0, 0),
    }


def load_config():
    import tomllib
    with open(os.path.join(ROOT, "config.toml"), "rb") as f:
        return tomllib.load(f)
