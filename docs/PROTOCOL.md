# TOPDON TB6000Pro — BLE protocol & tools

Reverse-engineered from the **BatteryLab** Android app (`com.topdon.tb6000.pro`
v1.81.002, decompiled with jadx) and **validated against real hardware 2026-08-06**.

Device: TOPDON TB6000Pro 6V/12V battery charger + tester. Telink BLE SoC.

## Files

| File | What |
|---|---|
| `tb6000_proto.py` | Framing, full command table, response parser. No dependencies. |
| `tb6000_ble.py` | Scanner / diff-finder / probe client. Needs `bleak`. |

```sh
python3 -m venv venv && ./venv/bin/pip install bleak
./venv/bin/python tb6000_ble.py scan 15
./venv/bin/python tb6000_ble.py baseline 15    # charger OFF
./venv/bin/python tb6000_ble.py compare 15     # charger ON -> shows the delta
./venv/bin/python tb6000_ble.py probe <address>
```

`baseline`/`compare` exist because the unit is only findable when you're next to it;
they diff two scans so the charger falls out even if you don't know its name.
`diff` does both passes interactively in one run.

## Discovery

Advertises under the literal name **`TB6000Pro`**. It advertises whenever mains-powered
and unpaired (BT LED flashes) — a battery does **not** need to be connected. Range is
short: -35 dBm standing at the car, invisible from indoors ~15 m away.

## GATT

Service `0000fee7-0000-1000-8000-00805f9b34fb`

| Characteristic | Properties | Use |
|---|---|---|
| `0000ff00-…` | notify, read, write-without-response | commands + responses (both directions) |
| `0000fec1-…` | notify, write-without-response | Telink OTA/mesh, unused by the app |

The app also carries a "v1" map (service `0000ff03-0405-0607-0809-0a0b0c0d1912`,
char `0000ff00-0405-0607-0809-0a0b0c0d2b12`) for a different hardware revision.
This unit is v0. Telink OTA service is `00010203-0405-0607-0809-0a0b0c0d1912`.

**No authentication, no bonding.** Connect, subscribe, write. `FF03 GET_RANDOM` looks
like a challenge but is just a fixed 6-char device code the app stores and never echoes.

## Framing

```
request   55 AA 00 <len-2> FF <~(len-2)> <op_hi> <op_lo> [args…] <XOR>
response  55 AA 00 <len-2> FF <~(len-2)> <op_hi> <op_lo> <status> [data…] <XOR>
                                            [6]     [7]     [8]     [9:]
```
XOR covers bytes `[2 .. len-2]`. `status` 0x00 = OK. 16-bit values big-endian;
voltages are ×100. `CRCTool` (CRC-16/CCITT-FALSE) is OTA-only, not used here.

## Verified capture (battery disconnected)

```
-> 55 AA 00 07 FF F8 FF 04 FB                     GET_BOOT_VERSION
<- …FF 04 00 "BOOT V1.00"                         10 bytes @ offset 9
<- 55 AA 00 08 FF F7 F1 F2 11 12                  unsolicited F1F2 status=0x11 (unknown)
-> 55 AA 00 07 FF F8 FF 01 FE                     GET_VERSION
<- …FF 01 00 35 "TOPDON6V1.01"                    version "1.01" @ offset 18, 4 bytes
-> 55 AA 00 07 FF F8 FF 03 FC                     GET_RANDOM
<- …FF 03 00 35 "5XU38B"                          6-byte device code @ offset 9
-> 55 AA 00 07 FF F8 FF 00 FF                     GET_MODULE_STATE   -> status 0
-> 55 AA 00 07 FF F8 FE 04 FA                     GET_BATTERY_INFO   -> status 0x02
-> 55 AA 00 07 FF F8 FE 02 FC                     GET_CLIP_STATE     -> 0x00
-> 55 AA 00 07 FF F8 BF 00 BF                     GET_VARIOUS_STATE
<- …BF 00 00 | 00 01 00 00 00 00 00 00 00 00 00 32 00
```
All XOR checksums validated in both directions. The APK's hardcoded byte offsets
(10 @ 9, 4 @ 18, 6 @ 9) match the wire exactly.

## Starting a charge over BLE — SOLVED (2026-08-07)

`BF05 SET_CHARGING_MODE` is the missing precondition. `BF0B` alone is silently
ignored because there is no committed mode to start. Working sequence:

```
55 AA 00 08 FF F7 BF 05 01 BB    SET_CHARGING_MODE(1)    <- the one that matters
55 AA 00 08 FF F7 BF 04 01 BA    SET_FUNCTION_MODE(1)
55 AA 00 09 FF F6 BF 0B 01 01 B4 SET_START_CHARGE(1,1)
```
Charging begins within seconds. `BF0B` returns `st=0x00` once a mode is committed and
a session can start; its earlier silence was a rejection, not a missing reply.
Observed on one session (2026-08-07): a flat AGM went from 11.5 V to full overnight.
Not yet repeated, so treat "reliable" as unestablished.

🛑 **Stopping is NOT verified — do not build a control on this without settling it first.**
`BF0C SET_END_CHARGING` ACKs, but `BF00[11]` did not return to its pre-charge value
afterwards and no other payload byte has been confirmed to report "session ended". The
ACK therefore proves the frame was accepted, **not** that charging stopped. Anyone wiring
up `BF0B` needs a confirmed stop path — verify against the LCD and a clamp meter, not
against the ACK.

⚠ **`BF05` is required to start, but does not appear to select the profile.** Writing
modes 2–6 is always acked and always lands in `BF00[12]`, yet the LCD keeps showing the
front-panel mode and the charging behaviour never changes — mode 5 behaved identically
to mode 1 (same float pulsing, same steps, same `b18`). So treat `BF05` as a
"mode is committed" gate that enables `BF0B`, **not** as working mode control. Do not
expose mode selection in an integration until this is understood; the physical MODE
button appears to remain authoritative over the actual profile.

## BF00 payload map (verified against the LCD, 2026-08-07)

```
idx    9  10  11  12  13  14 15 16 17  18  19  20  21
idle  00  00  00  00  00  00 00 00 00  00  31  66  00
chg   00  00  02  01  09  00 00 00 00  39  32  02  01
```

| Byte | Meaning |
|---|---|
| `[11]` | `0x00` before the first charge, `0x02` ever since — did **not** return to 0 after `BF0C SET_END_CHARGING`, so it is not a simple charge-active flag. Meaning unconfirmed. |
| `[12]` | **selected charging mode** — tracks `BF05 SET_CHARGING_MODE` exactly (verified 1–6). Note the **LCD does not follow** a BLE mode change; the display keeps showing the front-panel mode, so `[12]` and the screen can disagree. |
| `[13]` | **charge step / phase, 0–9** — confirmed against the LCD ("phase 3", "phase 9"); walks 0→1→2→3→4 then settles oscillating 8↔9 in float |
| `[18]` | `0x39` = 57 while a session is active, `0` idle. Never varied — not in float, not across modes. Possibly current ×0.1 A (5.7 A on a 6 A unit) or a fixed rating. **Unresolved:** a mode-5 test failed to move it, but that test was void because `BF05` does not change actual behaviour (below). Settle it during a real bulk charge on a discharged battery — measured current would differ from float, a limit would not. |
| `[19:21]` | **battery voltage, mV, big-endian** |
| `[21]` | function mode, set by `BF04` (`1` = charge) |
| `[9] [10] [14]–[17]` | always zero so far |

In float the voltage pulses ~12.8 V ↔ 14.3 V on a roughly 60–70 s cycle.

**SOC is not in `BF00`.** The LCD showed 35% then 100% while every byte above stayed
put, so percentage comes from elsewhere — most likely `FE04 GET_BATTERY_INFO` or
`FE05 GET_CHARGE_STEP`, which return status `0x02` when idle but were never polled
during an active charge.

## Older note: battery voltage confirmation

`BF00` returns 13 data bytes at `[9:22]`. **Bytes `[19:21]` are battery voltage in
millivolts, big-endian** — verified by polling with and without a battery attached:

```
no battery   00 01 00 00 00 00 00 00 00 00 00 32 00   [19:21]=0x0032 =    50 -> 0.05 V
battery on   00 00 00 00 00 00 00 00 00 00 2d 46 00   [19:21]=0x2D46 = 11590 -> 11.590 V
                                                              0x2D32 = 11570 -> 11.570 V
                                                              0x2D61 = 11617 -> 11.617 V
```
Consecutive polls jitter ±25 mV, i.e. a live ADC reading rather than a constant.
Byte `[10]` also flips `0x01` -> `0x00` when a battery is present. The remaining
bytes stayed zero while idle and are still unidentified — they most likely carry
charging current / step / timer once a charge is actually running.

**Correction:** status `0x02` does NOT mean "no battery". With a battery connected,
`FE04 GET_BATTERY_INFO` and `FE05 GET_CHARGE_STEP` both still return `0x02`, and
`FE02 GET_CLIP_STATE` still returns `0x00`. `0x02` appears to mean "no data / that
subsystem isn't active" — those reads only populate once a test or charge is running.

`FE01 GET_BATTERY_PARAMS` returns 6 bytes: `00 00 00 00 01 f4` (`0x01F4` = 500,
a round number that smells like a default capacity/CCA setting — unconfirmed).

## The battery this is wired to

**Banner, 12 V, 70 Ah, 720 A (EN), AGM.** Measured resting **11.55–11.62 V**
(2026-08-06) — deeply discharged; a healthy 12 V lead-acid rests at 12.6–12.7 V.

Mode choice matters here: the manual's `12V/6A Norm` explicitly covers "12V Wet, Gel,
MF, Cal, EFB, **and AGM**" via 9-step smart charging, and 6 A into 70 Ah is ~C/12 —
right in the normal 0.1C band. **`12V/1A Repair` is the wrong mode for this battery**:
it's aimed at sulfated flooded cells, pulse desulfation is contraindicated for sealed
AGM (can't replace lost electrolyte if overvoltage dries it out), and 1 A into 70 Ah is
C/70 — days to accomplish anything.

## ⚠ It stops advertising while charging

Observed 2026-08-06: the unit advertises continuously at -31…-35 dBm while **idle**,
but goes completely silent once a charge is running — no adverts, not connectable,
across repeated scans and direct connect attempts with the phone's Bluetooth off.
The BT indicator matches: flashing = advertising, steady = not.

The app gets away with it because it is already connected when the charge starts and
keeps that link through the transition. **If you drop the connection mid-charge you
cannot get back in until the charge ends.**

Design implication for any HA integration: connect while the charger is idle and
*hold* the connection for the whole session. A poll-on-demand design will not work —
by the time there is something interesting to read, the device is unreachable.

## Write path — first pass (2026-08-06) ⚠ PARTLY SUPERSEDED

> **The `BF0B` row below is superseded** by
> [Starting a charge over BLE — SOLVED (2026-08-07)](#starting-a-charge-over-ble--solved-2026-08-07).
> `BF0B` is not unconditionally ignored: it is rejected in silence only while no mode has
> been committed, and returns `st=0x00` once `BF05` has run first. This section is kept
> because the `BF04` and `BF10` findings still stand and the silence itself is a useful
> diagnostic signature.

| Command | Frame | Result |
|---|---|---|
| `BF04 SET_FUNCTION_MODE(1)` | `55 AA 00 08 FF F7 BF 04 01 BA` | **ACK `st=0x00`**, and `BF00[21]` flips `0x00`→`0x01`. Works. |
| `BF10 SET_TIME` | `55 AA 00 0D FF F2 BF 10 <epoch BE4> 00 78 <xor>` | ACK `st=0x00`, but `BF08 GET_TIME` still returns all zeros — payload format likely wrong. |
| `BF0B SET_START_CHARGE` | `55 AA 00 09 FF F6 BF 0B 01 01 B4` | ⚠ *superseded — see above.* **No response at all** at the time of this capture, with or without args, because no mode had been committed. |

`BF04` ACKing proves the framing/XOR is correct on the write path — so `BF0B`'s silence
is a rejection by the firmware, not a malformed frame. Payload is `{0x01, <function
mode>}`; the app always uses `1` (`setFunctionMode(1)` / `SET_FUNCTION_MODE(1)`), and
this byte is a *function* mode (charge vs test), not battery chemistry — chemistry comes
from `BF05` or the front-panel MODE button.

⚠ **The unit would not start a charge from its own MODE button either** — the LCD showed
the selected mode blinking indefinitely instead of committing (manual says it should
auto-start after 3 s). So the refusal is device-side and not a BLE problem.

## Charging logic lives in the firmware

The app is a parameter editor plus a dashboard — it never streams a waveform. It sends
one 22-field block via `BF09 SET_DIY_MODE`, then `BF0B` to start; the charger runs the
9-step state machine and generates the pulses itself (standalone mode works with no
phone). Good news for automation: configure and fire, no real-time loop needed.

Step 2 is the recovery/desulfation stage: `upperLimitPulse`, `pulseThreshold`,
`numberCyycles`, plus a duration. There is also a built-in **12V/1A Repair** mode
(pulse desulfation, selectable standalone) reachable via `BF05 SET_CHARGING_MODE` —
note the app remaps mode indices before sending: UI 0/3 → `1`, UI 1 → `5`, UI 2 → `3`.

### DIY parameter encoding (⚠ not yet verified on hardware)

Wire units are mV/mA; UI values are **offsets**, not absolutes:

```
s2MaxVoltage    (v + 6.0) * 1000        default 8.5 -> 14500 mV = 14.5 V
currentVoltage  (v + 4.0) * 1000
s3Voltage       (v + 5.5) * 1000
max current     (a + 1.0) A             steps 4/7/8 derived as 0.125/0.25/0.5/0.75 x max
upperLimitPulse ((v / 2) + 1.0) * 1000
pulseThreshold  ((v / 2) + 0.5) * 1000
times           (h + 1) * 3600 s        4 bytes
numberCyycles   (n + 100) / 100         1 byte, 0xFF = unlimited
```

Only the read path has been exercised against the device. Confirm these transforms
against a real app session before writing a hand-built DIY profile to a battery you
care about — a wrong offset here sets a genuinely wrong voltage ceiling.

Charging modes (manual Fig 3.1.1): 12V/6A Norm 14.2 V · 6V/3A 7.1 V · 12V/3A Small
14.2 V · 12V/6A Li-ion 14.6 V · 12V/1A Repair 14.2 V · 12V/6A Supply 13.5 V.
Errors: Er1 short/reverse polarity · Er2 overtemp · Er3 timeout · Er4 battery damaged ·
Er5 wrong mode.
