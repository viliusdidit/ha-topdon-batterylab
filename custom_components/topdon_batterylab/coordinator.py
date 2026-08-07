"""Polling coordinator for TOPDON BatteryLab devices."""

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
from .devices import DeviceProfile, DeviceState, decode
from .protocol import CHAR_UUIDS

_LOGGER = logging.getLogger(__name__)

# Surfaced when the device is not advertising. Using the phone app leaves the
# charger bonded and silent to everything else until it is fully power-cycled,
# which is unguessable, so say so explicitly.
_NOT_FOUND = (
    "Device not advertising. If the TOPDON BatteryLab app has been used since "
    "the device was last powered up, disconnect it from the battery for about "
    "30 seconds to clear the pairing, then reconnect."
)


class TopdonCoordinator(DataUpdateCoordinator[DeviceState]):
    """Connect, poll once, disconnect."""

    def __init__(
        self, hass: HomeAssistant, address: str, profile: DeviceProfile
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {address}",
            update_interval=UPDATE_INTERVAL,
        )
        self.address = address
        self.profile = profile

    def _ble_device(self) -> BLEDevice:
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise UpdateFailed(_NOT_FOUND)
        return device

    async def _async_update_data(self) -> DeviceState:
        device = self._ble_device()
        client = await establish_connection(
            BleakClient, device, self.address, max_attempts=3
        )
        try:
            return await self._poll(client)
        finally:
            await client.disconnect()

    async def _poll(self, client: BleakClient) -> DeviceState:
        char = self._resolve_char(client)
        future: asyncio.Future[DeviceState] = self.hass.loop.create_future()

        def _on_notify(_handle, data: bytearray) -> None:
            # Devices also emit unsolicited frames; decode() returns None for
            # anything that is not the reply we asked for.
            state = decode(self.profile, bytes(data))
            if state is not None and not future.done():
                future.set_result(state)

        await client.start_notify(char, _on_notify)
        try:
            await client.write_gatt_char(char, self.profile.poll_frame, response=False)
            async with asyncio.timeout(NOTIFY_TIMEOUT):
                return await future
        except TimeoutError as err:
            raise UpdateFailed("no response within timeout") from err
        finally:
            try:
                await client.stop_notify(char)
            except Exception:  # noqa: BLE001 - disconnecting anyway
                pass

    @staticmethod
    def _resolve_char(client: BleakClient):
        """Return the read/write/notify characteristic for either GATT revision."""
        for uuid in CHAR_UUIDS:
            if (char := client.services.get_characteristic(uuid)) is not None:
                return char
        raise UpdateFailed("no known TOPDON characteristic on this device")
