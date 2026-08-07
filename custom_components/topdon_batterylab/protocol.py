"""Shared TOPDON BLE transport.

Framing and GATT details are common to TOPDON's BatteryLab BLE devices: the app
implements them in product-agnostic packages (`com/topdon/ble`, `UUIDManager`)
rather than per model. Device-specific opcodes and payload layouts live in
devices.py.

Frame:  55 AA 00 <len-2> FF <~(len-2)> <op_hi> <op_lo> [args...] <XOR>
        XOR covers bytes[2 .. len-2].
Reply:  bytes[6:8] opcode, [8] status (0 = OK), [9:] payload, 16-bit big-endian.

NOTE: only the TB6000Pro has been observed on the wire. The shared-transport
claim is an inference from the app's code structure, not an observation of a
second device.
"""

from __future__ import annotations

# Telink's generic service UUID. NOT TOPDON-specific - never use it alone to
# identify a device, plenty of unrelated Telink hardware advertises it.
SERVICE_UUID = "0000fee7-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"

# Alternate GATT map the app carries for a different hardware revision.
# Untested - no device seen using it.
SERVICE_UUID_V1 = "0000ff03-0405-0607-0809-0a0b0c0d1912"
CHAR_UUID_V1 = "0000ff00-0405-0607-0809-0a0b0c0d2b12"

CHAR_UUIDS = (CHAR_UUID, CHAR_UUID_V1)

HEADER = (0x55, 0xAA)
STATUS_OK = 0x00
_MIN_FRAME = 9


def build(opcode: tuple[int, int], *args: int) -> bytes:
    """Assemble a command frame (port of the app's CmdUtil.assembleCmd)."""
    payload = bytes(opcode) + bytes(args)
    n = len(payload) + 7
    f = bytearray(n)
    f[0], f[1], f[2] = HEADER[0], HEADER[1], 0x00
    f[3] = (n - 2) & 0xFF
    f[4] = 0xFF
    f[5] = (~f[3]) & 0xFF
    f[6 : 6 + len(payload)] = payload
    x = 0
    for i in range(2, n - 1):
        x ^= f[i]
    f[n - 1] = x
    return bytes(f)


def xor_ok(frame: bytes) -> bool:
    """Verify the trailing XOR checksum."""
    x = 0
    for b in frame[2:-1]:
        x ^= b
    return x == frame[-1]


def unpack(frame: bytes) -> tuple[tuple[int, int], int, bytes] | None:
    """Split a reply into (opcode, status, payload), or None if not a valid frame.

    Rejects anything that is not a well-formed, checksum-valid TOPDON frame,
    which includes the unsolicited F1F2 push the TB6000Pro emits after connect.
    """
    if len(frame) < _MIN_FRAME:
        return None
    if (frame[0], frame[1]) != HEADER:
        return None
    if not xor_ok(frame):
        return None
    return (frame[6], frame[7]), frame[8], frame[9:-1]


def u16(payload: bytes, offset: int) -> int:
    """Read a big-endian 16-bit field from a payload (payload[0] == frame[9])."""
    return int.from_bytes(payload[offset : offset + 2], "big")
