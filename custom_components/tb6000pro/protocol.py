"""TB6000Pro BLE wire protocol.

Reverse-engineered from the TOPDON BatteryLab app (com.topdon.tb6000.pro
v1.81.002) and verified against hardware. See docs/PROTOCOL.md.

Frame:  55 AA 00 <len-2> FF <~(len-2)> <op_hi> <op_lo> [args...] <XOR>
        XOR covers bytes[2 .. len-2].
Reply:  bytes[6:8] opcode, [8] status (0 = OK), [9:] payload, 16-bit big-endian.
"""

from __future__ import annotations

from dataclasses import dataclass

SERVICE_UUID = "0000fee7-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"

# Alternate GATT map used by a different hardware revision. Not seen in the
# wild by us, but the app carries it, so try it as a fallback.
SERVICE_UUID_V1 = "0000ff03-0405-0607-0809-0a0b0c0d1912"
CHAR_UUID_V1 = "0000ff00-0405-0607-0809-0a0b0c0d2b12"

GET_VARIOUS_STATE = (0xBF, 0x00)
GET_VERSION = (0xFF, 0x01)

# BF00 payload offsets, verified against the device LCD.
_IDX_MODE = 12
_IDX_STEP = 13
_IDX_CURRENT = 18  # 0x39 while active; current x0.1 A or a fixed limit (unresolved)
_IDX_VOLT = 19  # 2 bytes, big-endian millivolts
_MIN_BF00_LEN = 22

MAX_STEP = 9


def build(opcode: tuple[int, int], *args: int) -> bytes:
    """Assemble a command frame (port of the app's CmdUtil.assembleCmd)."""
    payload = bytes(opcode) + bytes(args)
    n = len(payload) + 7
    f = bytearray(n)
    f[0], f[1], f[2] = 0x55, 0xAA, 0x00
    f[3] = (n - 2) & 0xFF
    f[4] = 0xFF
    f[5] = (~f[3]) & 0xFF
    f[6 : 6 + len(payload)] = payload
    x = 0
    for i in range(2, n - 1):
        x ^= f[i]
    f[n - 1] = x
    return bytes(f)


POLL_FRAME = build(GET_VARIOUS_STATE)


@dataclass(slots=True)
class ChargerState:
    """Decoded BF00 response."""

    voltage: float          # volts
    step: int               # 0-9, the 9-step profile stage
    mode: int               # selected mode register
    charging: bool
    raw: str                # hex of the payload, for diagnostics


def _xor_ok(frame: bytes) -> bool:
    x = 0
    for b in frame[2:-1]:
        x ^= b
    return x == frame[-1]


def parse_state(frame: bytes) -> ChargerState | None:
    """Decode a BF00 notification. Returns None if it is not one, or is corrupt."""
    if len(frame) < _MIN_BF00_LEN or frame[0] != 0x55 or frame[1] != 0xAA:
        return None
    if (frame[6], frame[7]) != GET_VARIOUS_STATE or frame[8] != 0x00:
        return None
    if not _xor_ok(frame):
        return None
    mv = int.from_bytes(frame[_IDX_VOLT : _IDX_VOLT + 2], "big")
    step = frame[_IDX_STEP]
    # [11] is 0 before the first charge of a power cycle and 2 afterwards; it does
    # not clear on stop, so step activity is the more reliable liveness signal.
    charging = frame[_IDX_CURRENT] != 0x00
    return ChargerState(
        voltage=mv / 1000.0,
        step=step if step <= MAX_STEP else 0,
        mode=frame[_IDX_MODE],
        charging=charging,
        raw=frame[9:-1].hex(" "),
    )
