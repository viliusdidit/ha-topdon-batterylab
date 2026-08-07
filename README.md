# TOPDON BatteryLab for Home Assistant

Read-only Home Assistant integration for **TOPDON BatteryLab** Bluetooth LE battery
devices. No cloud, no account, no phone app.

The BLE protocol was reverse-engineered from TOPDON's app and verified against real
hardware — see **[docs/PROTOCOL.md](docs/PROTOCOL.md)**, a complete protocol description
that is probably more useful than this integration if you are building something else.

## Supported devices

| Device | Status |
|---|---|
| **TB6000Pro** — 6V/12V charger & tester | Supported, verified against firmware `TOPDON6V1.01` |
| BT20 battery tester | Not implemented |
| V2200Plus jump starter | Not implemented |

TOPDON's BatteryLab app covers all three, and the app implements its Bluetooth transport
in product-agnostic code — so the framing here is *expected* to be common across them.
That is an inference from the app's structure, **not** something observed on the wire.
Adding a device means writing a `DeviceProfile` in `devices.py`; the transport should
already work. Captures welcome.

## Entities

| Entity | Description |
|---|---|
| `sensor.tb6000pro_battery_voltage` | Battery voltage, volts |
| `sensor.tb6000pro_charge_step` | Stage of the 9-step charge profile (0–9) |
| `sensor.tb6000pro_mode` | Selected mode register (diagnostic) |
| `binary_sensor.tb6000pro_charging` | On while a charge session is active |

The charging sensor exposes a `maintaining` attribute — true when the charger is
alternating steps 8/9, which is float maintenance rather than active charging.

## Why read-only

Writing works — `BF05` + `BF04` + `BF0B` reliably starts a charge, and it is documented
in [docs/PROTOCOL.md](docs/PROTOCOL.md). It is deliberately **not exposed** here:
`BF05 SET_CHARGING_MODE` is required to start a charge but does **not** appear to select
the charging profile. Modes 2–6 were all accepted, all landed in the mode register, and
none changed the LCD or the actual charging behaviour. Until that is understood, mode
control would be a button that lies about what it does — on a device connected to a lead
acid battery.

**Recommended pairing:** put the charger's mains supply on a smart plug with power
metering (a Shelly 1PM Pro, for example). That gives reliable on/off control and real
charging power measured on the AC side, which is more trustworthy than anything the BLE
write path currently offers.

## Requirements

- Home Assistant 2024.12 or newer
- A Bluetooth adapter **or an ESPHome Bluetooth proxy with `active: true`** within range

Range is the practical constraint. The TB6000Pro is short-range — around -35 dBm standing
next to it, invisible from ~15 m away through a wall. If it lives in a garage or driveway,
you need a proxy out there. Passive-only proxies will not work: this integration connects,
subscribes and writes a poll frame.

## Installation

**HACS:** add this repository as a custom repository (type: Integration), install, restart.

**Manual:** copy `custom_components/topdon_batterylab` into your `config/custom_components/`,
restart.

The device is discovered automatically once it is in range and powered.

## Known gotcha: the phone app makes it disappear

If the TOPDON BatteryLab app connects to the charger, **the charger stops advertising to
everything else** and stays that way — surviving AC removal, because the unit is powered
from the battery it is clamped to.

To recover, disconnect it from the battery for about 30 seconds so it fully powers down,
then reconnect. It will advertise again.

This is device behaviour, not an integration bug, and it will make entities unavailable
until cleared.

## Polling behaviour

The integration connects, reads, and disconnects every 60 seconds rather than holding the
link. These devices accept a single connection, so holding it would lock the phone app out
entirely. Charging is an hours-long process; a slow cadence costs nothing.

## Unresolved

Documented in [docs/PROTOCOL.md](docs/PROTOCOL.md): state of charge is not exposed by any
command found so far, and the byte suspected of carrying charging current never varied.
Both should resolve on a genuinely discharged battery.

## Tests

```sh
python3 tests/test_protocol.py
```

Pure protocol tests, no Home Assistant required. Fixtures are real frames captured from
hardware.

## License

MIT
