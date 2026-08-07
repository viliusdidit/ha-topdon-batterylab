"""Protocol and decode tests using frames actually captured from a TB6000Pro.

Run: python3 tests/test_protocol.py      (or: python3 -m pytest tests/ -q)
"""

import importlib.util
import sys
import types
from pathlib import Path

# protocol.py and devices.py use relative imports, so load them as a synthetic
# package. Importing the real package would execute __init__.py, which pulls in
# Home Assistant - unnecessary for testing pure protocol logic.
_PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "topdon_batterylab"
_pkg = types.ModuleType("_tbl")
_pkg.__path__ = [str(_PKG_DIR)]
sys.modules["_tbl"] = _pkg


def _load(name):
    spec = importlib.util.spec_from_file_location(f"_tbl.{name}", _PKG_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"_tbl.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


_protocol = _load("protocol")
_devices = _load("devices")

build, unpack, xor_ok = _protocol.build, _protocol.unpack, _protocol.xor_ok
TB6000PRO, decode, profile_for = _devices.TB6000PRO, _devices.decode, _devices.profile_for


def _reply(status, body):
    """Assemble a BF00 reply frame with a correct XOR."""
    return build((0xBF, 0x00), status, *body)


# --- transport ---------------------------------------------------------------


def test_poll_frame_matches_device():
    # Verified accepted by the charger.
    assert TB6000PRO.poll_frame.hex() == "55aa0007fff8bf00bf"


def test_build_checksum():
    # The start-charge frame the device accepted.
    assert build((0xBF, 0x0B), 1, 1).hex() == "55aa0009fff6bf0b0101b4"


def test_xor_and_unpack():
    frame = _reply(0x00, [0] * 13)
    assert xor_ok(frame)
    opcode, status, payload = unpack(frame)
    assert opcode == (0xBF, 0x00)
    assert status == 0x00
    assert len(payload) == 13


def test_unpack_rejects_bad_checksum():
    frame = bytearray(_reply(0x00, [0] * 13))
    frame[-1] ^= 0xFF
    assert unpack(bytes(frame)) is None


def test_unpack_rejects_short_and_foreign():
    assert unpack(b"\x55\xaa\x00") is None
    assert unpack(b"") is None
    assert unpack(b"\x11\x22\x33\x44\x55\x66\x77\x88\x99") is None


# --- TB6000Pro decode --------------------------------------------------------


def test_idle_state():
    s = decode(TB6000PRO, _reply(0x00, [0] * 13))
    assert s is not None
    assert s.voltage == 0.0
    assert s.step == 0
    assert s.charging is False


def test_charging_state():
    # Real sample: 12.802 V, step 9, mode 1, active byte 0x39
    body = [0, 0, 2, 1, 9, 0, 0, 0, 0, 0x39, 0x32, 0x02, 1]
    s = decode(TB6000PRO, _reply(0x00, body))
    assert s is not None
    assert s.voltage == 12.802
    assert s.step == 9
    assert s.mode == 1
    assert s.charging is True


def test_voltage_no_battery():
    # 0x0032 = 50 mV, what the charger reports with nothing connected
    body = [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0x00, 0x32, 0]
    s = decode(TB6000PRO, _reply(0x00, body))
    assert s is not None and s.voltage == 0.05


def test_rejects_error_status():
    assert decode(TB6000PRO, _reply(0x02, [0] * 13)) is None


def test_rejects_unsolicited_push():
    # F1F2 status push the charger emits after connect
    assert decode(TB6000PRO, build((0xF1, 0xF2), 0x11)) is None


def test_rejects_truncated_payload():
    assert decode(TB6000PRO, _reply(0x00, [0] * 5)) is None


# --- registry ----------------------------------------------------------------


def test_profile_lookup():
    assert profile_for("TB6000Pro") is TB6000PRO
    assert profile_for("SomethingElse") is None
    assert profile_for(None) is None


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
