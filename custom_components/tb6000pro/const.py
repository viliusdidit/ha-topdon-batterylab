"""Constants for the TOPDON TB6000Pro integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "tb6000pro"

MANUFACTURER = "TOPDON"
MODEL = "TB6000Pro"
LOCAL_NAME = "TB6000Pro"

# The charger appears to accept a single BLE connection, and the phone app needs
# it too. Connect, poll, disconnect - never hold the link - so the app is not
# locked out. A charge runs for hours, so a slow cadence loses nothing.
UPDATE_INTERVAL = timedelta(seconds=60)

# Time to wait for the BF00 notification after writing the poll frame.
NOTIFY_TIMEOUT = 10.0

# Steps 8 and 9 alternate during float maintenance.
FLOAT_STEPS = (8, 9)
