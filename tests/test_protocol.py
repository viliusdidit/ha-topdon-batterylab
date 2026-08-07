"""Protocol tests using frames actually captured from a TB6000Pro.

Run: python3 -m pytest tests/ -q     (or just: python3 tests/test_protocol.py)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "tb6000pro"))

from protocol import POLL_FRAME, build, parse_state  # noqa: E402

def _rebuild(status, body):
    """Assemble a BF00 reply frame with a correct XOR."""
    return build((0xBF, 0x00), status, *body)


def test_poll_frame_matches_device():
    # Verified accepted by the charger.
    assert POLL_FRAME.hex() == "55aa0007fff8bf00bf"


def test_build_checksum():
    f = build((0xBF, 0x0B), 1, 1)
    assert f.hex() == "55aa0009fff6bf0b0101b4"


def test_idle_state():
    s = parse_state(_rebuild(0x00, [0] * 13))
    assert s is not None
    assert s.voltage == 0.0
    assert s.step == 0
    assert s.charging is False


def test_charging_state():
    # 12.802 V, step 9, mode 1, current byte 0x39 -> session active
    body = [0, 0, 2, 1, 9, 0, 0, 0, 0, 0x39, 0x32, 0x02, 1]
    s = parse_state(_rebuild(0x00, body))
    assert s is not None
    assert s.voltage == 12.802
    assert s.step == 9
    assert s.mode == 1
    assert s.charging is True


def test_voltage_no_battery():
    # 0x0032 = 50 mV, what the charger reports with nothing connected
    body = [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0x00, 0x32, 0]
    s = parse_state(_rebuild(0x00, body))
    assert s is not None
    assert s.voltage == 0.05


def test_rejects_bad_checksum():
    frame = bytearray(_rebuild(0x00, [0] * 13))
    frame[-1] ^= 0xFF
    assert parse_state(bytes(frame)) is None


def test_rejects_short_and_foreign_frames():
    assert parse_state(b"\x55\xaa\x00") is None
    assert parse_state(b"") is None
    # F1F2 status push the charger emits unsolicited after connect
    assert parse_state(build((0xF1, 0xF2), 0x11)) is None


def test_rejects_error_status():
    assert parse_state(_rebuild(0x02, [0] * 13)) is None


if __name__ == "__main__":
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                passed += 1
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
    print(f"{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
