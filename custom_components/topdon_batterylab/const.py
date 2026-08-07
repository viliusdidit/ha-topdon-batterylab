"""Constants for the TOPDON BatteryLab integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "topdon_batterylab"

MANUFACTURER = "TOPDON"

CONF_MODEL = "model"

# These chargers appear to accept a single BLE connection, and the phone app
# needs it too. Connect, poll, disconnect - never hold the link - so the app is
# not locked out. A charge runs for hours, so a slow cadence loses nothing.
UPDATE_INTERVAL = timedelta(seconds=60)

# Time to wait for the poll response after writing the request.
NOTIFY_TIMEOUT = 10.0
