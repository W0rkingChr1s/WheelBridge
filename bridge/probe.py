#!/usr/bin/env python3
"""Hilfstool: zeigt Achsen/Knöpfe des Lenkrads live an (zum Befüllen der config.toml).

  wheelbridge probe              # Lenkrad (Name enthält 'G27')
  wheelbridge probe --name DFGT
  wheelbridge probe --usb        # Descriptor-Infos des Xbox-Controllers
"""
import argparse
import sys


def probe_wheel(name):
    from evdev import InputDevice, ecodes, list_devices
    dev = None
    for p in list_devices():
        d = InputDevice(p)
        print(f"  {d.path}: {d.name}")
        if name.lower() in d.name.lower():
            dev = d
    if not dev:
        sys.exit(f"Kein Gerät mit '{name}' gefunden.")
    caps = dev.capabilities(absinfo=True)
    print(f"\n==> {dev.name} ({dev.path})  FFB: {ecodes.EV_FF in caps}")
    print("Achsen:")
    for code, info in caps.get(ecodes.EV_ABS, []):
        n = ecodes.ABS.get(code, code)
        print(f"  {n!s:<12} ({code:3d}) min={info.min} max={info.max} wert={info.value}")
    print("\nBewege Lenkrad/Pedale, drücke Knöpfe, schalte Gänge. Strg+C beendet.\n")
    last = {}
    for ev in dev.read_loop():
        if ev.type == ecodes.EV_KEY and ev.value in (0, 1):
            n = ecodes.BTN.get(ev.code) or ecodes.KEY.get(ev.code) or ev.code
            n = n[0] if isinstance(n, list) else n
            print(f"KNOPF  {n!s:<20} code={ev.code:4d}  {'gedrückt' if ev.value else 'los'}")
        elif ev.type == ecodes.EV_ABS:
            info = dict(caps[ecodes.EV_ABS]).get(ev.code)
            span = (info.max - info.min) if info else 1
            if abs(ev.value - last.get(ev.code, ev.value + span)) * 50 >= span or ev.code in (16, 17):
                last[ev.code] = ev.value
                n = ecodes.ABS.get(ev.code, ev.code)
                print(f"ACHSE  {n!s:<20} code={ev.code:4d}  wert={ev.value}")


def probe_usb():
    import usb.core
    for dev in usb.core.find(find_all=True, idVendor=0x045E):
        print(f"Gerät {dev.idVendor:04x}:{dev.idProduct:04x} bcdDevice={dev.bcdDevice:04x} "
              f"Klasse={dev.bDeviceClass:02x}/{dev.bDeviceSubClass:02x}/{dev.bDeviceProtocol:02x}")
        for cfg in dev:
            for intf in cfg:
                print(f"  Interface {intf.bInterfaceNumber} alt {intf.bAlternateSetting}: "
                      f"{intf.bInterfaceClass:02x}/{intf.bInterfaceSubClass:02x}/{intf.bInterfaceProtocol:02x}")
                for ep in intf:
                    print(f"    EP 0x{ep.bEndpointAddress:02x} attr={ep.bmAttributes} "
                          f"maxpkt={ep.wMaxPacketSize} interval={ep.bInterval}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="G27")
    ap.add_argument("--usb", action="store_true")
    a = ap.parse_args()
    probe_usb() if a.usb else probe_wheel(a.name)
