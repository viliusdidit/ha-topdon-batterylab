"""Constants for the TOPDON BatteryLab integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "topdon_batterylab"

MANUFACTURER = "TOPDON"

CONF_MODEL = "model"

# Hold one BLE link for the lifetime of the entry instead of connecting and
# disconnecting around every poll.
#
# Required to observe a charge at all: the TB6000Pro stops advertising the
# moment a charge starts, so a coordinator that lets go after each poll can
# never reconnect mid-session. The phone app copes precisely because it holds
# the link across that transition.
#
# Trade-off, deliberate: these chargers accept a SINGLE BLE connection, so while
# HA holds it the phone app is locked out, and one proxy connection slot is
# consumed permanently. Set False to restore connect / poll / disconnect.
KEEPALIVE = True

# A charge runs for hours, so a slow cadence loses nothing. With KEEPALIVE this
# doubles as the link keepalive - traffic every interval on the held link.
UPDATE_INTERVAL = timedelta(seconds=60)

# Time to wait for the poll response after writing the request.
NOTIFY_TIMEOUT = 10.0
