"""Polling coordinator for the TB6000Pro."""

from __future__ import annotations

import asyncio
import logging

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, NOTIFY_TIMEOUT, UPDATE_INTERVAL
from .protocol import (
    CHAR_UUID,
    CHAR_UUID_V1,
    POLL_FRAME,
    ChargerState,
    parse_state,
)

_LOGGER = logging.getLogger(__name__)

# Surfaced when the device is not advertising. Using the phone app leaves the
# charger bonded and silent to everything else until it is fully power-cycled,
# which is unguessable, so say so explicitly.
_NOT_FOUND = (
    "TB6000Pro not advertising. If the TOPDON BatteryLab app has been used "
    "since the charger was last powered up, disconnect it from the battery "
    "for ~30 seconds to clear the pairing, then reconnect."
)


class TB6000Coordinator(DataUpdateCoordinator[ChargerState]):
    """Connect, read BF00, disconnect."""

    def __init__(self, hass: HomeAssistant, address: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {address}",
            update_interval=UPDATE_INTERVAL,
        )
        self.address = address

    def _ble_device(self) -> BLEDevice:
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise UpdateFailed(_NOT_FOUND)
        return device

    async def _async_update_data(self) -> ChargerState:
        device = self._ble_device()
        client = await establish_connection(
            BleakClient, device, self.address, max_attempts=3
        )
        try:
            return await self._poll(client)
        finally:
            await client.disconnect()

    async def _poll(self, client: BleakClient) -> ChargerState:
        char = self._resolve_char(client)
        future: asyncio.Future[ChargerState] = self.hass.loop.create_future()

        def _on_notify(_handle, data: bytearray) -> None:
            # The charger also emits unsolicited frames (an F1F2 status push
            # right after connect); parse_state ignores anything that is not
            # a well-formed BF00, so wait for the one we asked for.
            state = parse_state(bytes(data))
            if state is not None and not future.done():
                future.set_result(state)

        await client.start_notify(char, _on_notify)
        try:
            await client.write_gatt_char(char, POLL_FRAME, response=False)
            async with asyncio.timeout(NOTIFY_TIMEOUT):
                return await future
        except TimeoutError as err:
            raise UpdateFailed("no BF00 response within timeout") from err
        finally:
            try:
                await client.stop_notify(char)
            except Exception:  # noqa: BLE001 - disconnecting anyway
                pass

    @staticmethod
    def _resolve_char(client: BleakClient):
        """Return the read/write/notify characteristic for either GATT revision."""
        for uuid in (CHAR_UUID, CHAR_UUID_V1):
            char = client.services.get_characteristic(uuid)
            if char is not None:
                return char
        raise UpdateFailed("no known TB6000Pro characteristic on this device")
