"""Per-device opcode tables and payload decoding.

Add a device by writing a DeviceProfile and registering it in DEVICES, keyed on
the name it advertises over BLE.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .protocol import STATUS_OK, build, u16, unpack

MAX_STEP = 9
FLOAT_STEPS = (8, 9)


@dataclass(slots=True)
class DeviceState:
    """Decoded telemetry. Fields a device cannot supply stay None."""

    voltage: float | None = None
    step: int | None = None
    mode: int | None = None
    charging: bool | None = None
    raw: str = ""


@dataclass(frozen=True)
class DeviceProfile:
    """What a model advertises, what to poll, and how to decode the reply."""

    local_name: str
    model: str
    poll_frame: bytes
    decode: Callable[[tuple[int, int], int, bytes], DeviceState | None]
    supported_keys: frozenset[str] = field(
        default_factory=lambda: frozenset({"voltage", "step", "mode", "charging"})
    )


# --- TB6000Pro ---------------------------------------------------------------
# Payload offsets are relative to frame[9], verified against the device LCD.
_TB_GET_VARIOUS_STATE = (0xBF, 0x00)
_TB_MODE = 3
_TB_STEP = 4
_TB_ACTIVE = 9  # 0x39 whenever a session is live, 0x00 idle
_TB_VOLT = 10  # 2 bytes, big-endian millivolts
_TB_MIN_PAYLOAD = 13


def _decode_tb6000pro(
    opcode: tuple[int, int], status: int, payload: bytes
) -> DeviceState | None:
    if opcode != _TB_GET_VARIOUS_STATE or status != STATUS_OK:
        return None
    if len(payload) < _TB_MIN_PAYLOAD:
        return None
    step = payload[_TB_STEP]
    return DeviceState(
        voltage=u16(payload, _TB_VOLT) / 1000.0,
        step=step if step <= MAX_STEP else None,
        mode=payload[_TB_MODE],
        # payload[2] looks like a charge flag but never clears after a stop;
        # the active byte is the reliable one.
        charging=payload[_TB_ACTIVE] != 0x00,
        raw=payload.hex(" "),
    )


TB6000PRO = DeviceProfile(
    local_name="TB6000Pro",
    model="TB6000Pro",
    poll_frame=build(_TB_GET_VARIOUS_STATE),
    decode=_decode_tb6000pro,
)

# Keyed by advertised BLE local name.
# TOPDON's BatteryLab app also covers the BT20 tester and V2200Plus jump
# starter. They are expected to share this transport, but neither has been
# observed on the wire - do not add them until someone captures one.
DEVICES: dict[str, DeviceProfile] = {TB6000PRO.local_name: TB6000PRO}


def profile_for(local_name: str | None) -> DeviceProfile | None:
    """Return the profile for an advertised name, if supported."""
    return DEVICES.get(local_name or "")


def decode(profile: DeviceProfile, frame: bytes) -> DeviceState | None:
    """Decode a notification with the given profile."""
    parts = unpack(frame)
    if parts is None:
        return None
    return profile.decode(*parts)
