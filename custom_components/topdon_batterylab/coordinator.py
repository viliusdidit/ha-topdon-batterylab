"""Polling coordinator for TOPDON BatteryLab devices.

Transport mode is chosen by KEEPALIVE in const.py:

* KEEPALIVE = True  - open one BLE link and hold it for the lifetime of the
  entry, polling over it. Required to observe a charge: the TB6000Pro stops
  advertising the moment a charge starts, so a coordinator that disconnects
  after each poll can never get back in. Holding the link is also what the
  phone app does. Cost: the app (and any other client) is locked out while HA
  holds the single connection, and one proxy connection slot is consumed
  permanently.
* KEEPALIVE = False - the original connect / poll / disconnect behaviour.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, KEEPALIVE, NOTIFY_TIMEOUT, UPDATE_INTERVAL
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
    """Poll a TOPDON device, over a held link or a per-poll one."""

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
        # The charger accepts one BLE connection, so polling, button presses and
        # service calls must never overlap.
        self._conn_lock = asyncio.Lock()
        self._client: BleakClient | None = None
        self._char = None
        # Resolved by the notify handler with the next decodable state frame.
        self._pending: asyncio.Future[DeviceState] | None = None
        # Collects every raw notification while a capture is in progress.
        self._capture: list[str] | None = None

    # --- link management -----------------------------------------------------

    def _ble_device(self) -> BLEDevice:
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise UpdateFailed(_NOT_FOUND)
        return device

    def _on_disconnect(self, _client: BleakClient) -> None:
        """Bleak calls this from its own task when the link drops."""
        _LOGGER.debug("%s: BLE link dropped", self.address)
        self._client = None
        self._char = None

    def _handle_notify(self, _handle, data: bytearray) -> None:
        raw = bytes(data)
        if self._capture is not None:
            self._capture.append(raw.hex(" "))
        # Devices also emit unsolicited frames; decode() returns None for
        # anything that is not a state reply.
        state = decode(self.profile, raw)
        if state is None:
            return
        if self._pending is not None and not self._pending.done():
            self._pending.set_result(state)
        elif KEEPALIVE:
            # Held link: the device may push state we did not ask for. Publish
            # it rather than throw it away.
            self.async_set_updated_data(state)

    async def _connect(self) -> BleakClient:
        """Open a link and subscribe to notifications."""
        device = self._ble_device()
        try:
            client = await establish_connection(
                BleakClient,
                device,
                self.address,
                disconnected_callback=self._on_disconnect if KEEPALIVE else None,
                max_attempts=3,
            )
        except (BleakError, TimeoutError, OSError) as err:
            # Without this the helpful _NOT_FOUND hint never fires and the log
            # collects a full traceback on every update interval.
            raise UpdateFailed(f"could not connect: {err}") from err
        char = self._resolve_char(client)
        await client.start_notify(char, self._handle_notify)
        self._client = client
        self._char = char
        return client

    async def _ensure_link(self) -> BleakClient:
        """Return a live client, reconnecting if the held link went away."""
        if self._client is not None and self._client.is_connected:
            return self._client
        return await self._connect()

    async def _release(self) -> None:
        """Drop the held link, ignoring errors from an already-dead socket."""
        client, self._client, self._char = self._client, None, None
        if client is None:
            return
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001 - tearing down regardless
            _LOGGER.debug("%s: error during disconnect", self.address, exc_info=True)

    async def async_shutdown(self) -> None:
        """Release the BLE link when the entry unloads."""
        await super().async_shutdown()
        async with self._conn_lock:
            await self._release()

    # --- exchanges -----------------------------------------------------------

    async def _write(self, frame: bytes) -> None:
        assert self._char is not None
        try:
            await self._client.write_gatt_char(self._char, frame, response=False)
        except (BleakError, OSError) as err:
            await self._release()
            raise UpdateFailed(f"write failed: {err}") from err

    async def _request(self) -> DeviceState:
        """Write the poll frame and wait for the matching state reply."""
        future: asyncio.Future[DeviceState] = self.hass.loop.create_future()
        self._pending = future
        try:
            await self._write(self.profile.poll_frame)
            async with asyncio.timeout(NOTIFY_TIMEOUT):
                return await future
        except TimeoutError as err:
            # A held link that stops answering is dead in practice; drop it so
            # the next cycle reconnects instead of writing into the void.
            if KEEPALIVE:
                await self._release()
            raise UpdateFailed("no response within timeout") from err
        finally:
            self._pending = None

    async def _async_update_data(self) -> DeviceState:
        async with self._conn_lock:
            await self._ensure_link()
            try:
                return await self._request()
            finally:
                if not KEEPALIVE:
                    await self._release()

    async def async_send_command(
        self, frames: Sequence[bytes], gap: float = 2.5
    ) -> None:
        """Write a sequence of command frames.

        Used by the charge-control buttons. Takes the same lock as polling so the
        two never contend for the charger's single BLE connection. The device
        stops advertising once a charge starts, so a start must be issued while it
        is idle; a failure here surfaces to the caller.
        """
        async with self._conn_lock:
            await self._ensure_link()
            try:
                for i, frame in enumerate(frames):
                    if i:
                        await asyncio.sleep(gap)
                    await self._write(frame)
            finally:
                if not KEEPALIVE:
                    await self._release()

    async def async_exchange(
        self, frames: Sequence[bytes], listen: float, gap: float = 2.5
    ) -> list[str]:
        """Write frames and return every raw notification seen while listening.

        Protocol-exploration hook: unlike _request() this does not care whether a
        reply decodes, so it can be used on opcodes whose payload layout is not
        known yet (BF0C stop, the DE06/DE07 load-test pair, FE04 battery info).
        """
        async with self._conn_lock:
            await self._ensure_link()
            self._capture = []
            try:
                for i, frame in enumerate(frames):
                    if i:
                        await asyncio.sleep(gap)
                    await self._write(frame)
                await asyncio.sleep(listen)
                return list(self._capture)
            finally:
                self._capture = None
                if not KEEPALIVE:
                    await self._release()

    @staticmethod
    def _resolve_char(client: BleakClient):
        """Return the read/write/notify characteristic for either GATT revision."""
        for uuid in CHAR_UUIDS:
            if (char := client.services.get_characteristic(uuid)) is not None:
                return char
        raise UpdateFailed("no known TOPDON characteristic on this device")
