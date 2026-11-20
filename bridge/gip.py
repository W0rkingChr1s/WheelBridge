"""Minimale GIP-Helfer (Gaming Input Protocol, Xbox One/Series).

Paketformat:  [cmd][flags][seq][len (LEB128-Varint)][payload ...]

Wir parsen bewusst nur, was wir anfassen (Input 0x20, Rumble 0x09).
Alles andere (Announce, Identify, Auth, Keepalive, ACKs) wird roh
zwischen Xbox und echtem Controller durchgereicht.
"""
import struct
from dataclasses import dataclass

CMD_ACK = 0x01
CMD_ANNOUNCE = 0x02
CMD_STATUS = 0x03
CMD_IDENTIFY = 0x04
CMD_POWER = 0x05
CMD_AUTH = 0x06
CMD_GUIDE = 0x07
CMD_RUMBLE = 0x09
CMD_LED = 0x0A
CMD_INPUT = 0x20

FLAG_ACK_REQ = 0x10
FLAG_SYSTEM = 0x20
FLAG_CHUNK_START = 0x40
FLAG_CHUNKED = 0x80

CMD_NAMES = {
    CMD_ACK: "ACK", CMD_ANNOUNCE: "ANNOUNCE", CMD_STATUS: "STATUS",
    CMD_IDENTIFY: "IDENTIFY", CMD_POWER: "POWER", CMD_AUTH: "AUTH",
    CMD_GUIDE: "GUIDE", CMD_RUMBLE: "RUMBLE", CMD_LED: "LED", CMD_INPUT: "INPUT",
}

# Bitbelegung des 16-Bit-Button-Feldes im Input-Report (vgl. Linux xpad.c)
BUTTONS = {
    "MENU": 1 << 2, "VIEW": 1 << 3,
    "A": 1 << 4, "B": 1 << 5, "X": 1 << 6, "Y": 1 << 7,
    "UP": 1 << 8, "DOWN": 1 << 9, "LEFT": 1 << 10, "RIGHT": 1 << 11,
    "LB": 1 << 12, "RB": 1 << 13, "LS": 1 << 14, "RS": 1 << 15,
}

INPUT_BASE_LEN = 14          # buttons(2) LT(2) RT(2) LX LY RX RY (je 2)
_INPUT_FMT = "<HHHhhhh"


def _varint_decode(buf, pos):
    value = shift = 0
    while pos < len(buf):
        b = buf[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if not b & 0x80:
            return value, pos
        shift += 7
        if shift > 28:
            break
    return None, pos


def _varint_encode(value):
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def parse_header(pkt):
    """-> (cmd, flags, seq, length, header_len) oder None."""
    if len(pkt) < 4:
        return None
    length, pos = _varint_decode(pkt, 3)
    if length is None:
        return None
    return pkt[0], pkt[1], pkt[2], length, pos


def is_simple(pkt, cmd=None):
    """True, wenn pkt ein vollständiges, nicht gechunktes GIP-Paket ist.

    Schützt davor, Fortsetzungsdaten (z. B. mitten im Auth-Blob) fälschlich
    als Input- oder Rumble-Paket zu interpretieren.
    """
    h = parse_header(pkt)
    if not h:
        return False
    c, flags, _seq, length, hlen = h
    if cmd is not None and c != cmd:
        return False
    if flags & (FLAG_CHUNKED | FLAG_CHUNK_START):
        return False
    return hlen + length == len(pkt)


def next_seq(seq):
    """Sequenznummern laufen 1..255, die 0 wird übersprungen."""
    return 1 if seq >= 0xFF else seq + 1


def build_packet(cmd, flags, seq, payload):
    return bytes([cmd, flags, seq]) + _varint_encode(len(payload)) + bytes(payload)


@dataclass
class PadState:
    buttons: int = 0
    lt: int = 0      # 0..1023
    rt: int = 0      # 0..1023
    lx: int = 0      # -32768..32767
    ly: int = 0      # positiv = oben
    rx: int = 0
    ry: int = 0

    def as_tuple(self):
        return (self.buttons, self.lt, self.rt, self.lx, self.ly, self.rx, self.ry)


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else int(v)


def parse_input(pkt):
    """-> (PadState, flags, extra_bytes) oder None."""
    if not is_simple(pkt, CMD_INPUT):
        return None
    _c, flags, _s, length, hlen = parse_header(pkt)
    if length < INPUT_BASE_LEN:
        return None
    payload = pkt[hlen:hlen + length]
    vals = struct.unpack_from(_INPUT_FMT, payload, 0)
    return PadState(*vals), flags, bytes(payload[INPUT_BASE_LEN:])


def build_input(seq, state, flags=0x00, extra=b""):
    payload = struct.pack(
        _INPUT_FMT,
        state.buttons & 0xFFFF,
        _clamp(state.lt, 0, 1023),
        _clamp(state.rt, 0, 1023),
        _clamp(state.lx, -32768, 32767),
        _clamp(state.ly, -32768, 32767),
        _clamp(state.rx, -32768, 32767),
        _clamp(state.ry, -32768, 32767),
    ) + bytes(extra)
    return build_packet(CMD_INPUT, flags, seq, payload)


def parse_rumble(pkt):
    """Rumble-Payload: [0x00][motor_mask][LT][RT][strong][weak][dur][delay][repeat]
    -> (lt, rt, strong, weak) jeweils 0..100, oder None."""
    if not is_simple(pkt, CMD_RUMBLE):
        return None
    _c, _f, _s, length, hlen = parse_header(pkt)
    if length < 6:
        return None
    p = pkt[hlen:]
    return p[2], p[3], p[4], p[5]


def silence_rumble(pkt):
    """Gleiches Paket mit Motorstärken = 0 (Protokoll bleibt intakt)."""
    h = parse_header(pkt)
    if not h:
        return pkt
    hlen = h[4]
    out = bytearray(pkt)
    for i in range(2, 6):
        if hlen + i < len(out):
            out[hlen + i] = 0
    return bytes(out)


def describe(pkt):
    h = parse_header(pkt)
    if not h:
        return f"?? {bytes(pkt).hex(' ')}"
    cmd, flags, seq, length, _ = h
    name = CMD_NAMES.get(cmd, f"0x{cmd:02x}")
    return f"{name:<8} f=0x{flags:02x} seq={seq:3d} len={length:3d} | {bytes(pkt).hex(' ')}"
