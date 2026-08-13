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

# How long to hold one link before deliberately dropping it (KEEPALIVE only).
#
# A connected BLE device stops advertising. While the link is held the device is
# therefore invisible to every OTHER scanner, so Home Assistant can never
# re-evaluate which radio is closest: whichever proxy happened to be nearest at
# connect time stays chosen forever, even after the hardware physically moves.
# Observed for real - a charger was held over a proxy at -98 dBm while a proxy
# at -74 dBm sat unused three metres away, because it could not see the device
# to be considered.
#
# Dropping the link lets the device advertise for one update interval, which is
# long enough for every scanner to hear it, so the next connect picks the best
# path. Costs one extra connect per interval below.
RECONNECT_INTERVAL = timedelta(minutes=30)

# Time to wait for the poll response after writing the request.
NOTIFY_TIMEOUT = 10.0
