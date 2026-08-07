"""Config flow for TOPDON BatteryLab devices."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import CONF_MODEL, DOMAIN
from .devices import DeviceProfile, profile_for


class TopdonConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle discovery and manual setup."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, str] = {}
        self._address: str | None = None
        self._profile: DeviceProfile | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a device found by HA's Bluetooth discovery."""
        profile = profile_for(discovery_info.name)
        if profile is None:
            return self.async_abort(reason="not_supported")
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address
        self._profile = profile
        self.context["title_placeholders"] = {"name": profile.model}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered device."""
        assert self._address is not None and self._profile is not None
        if user_input is not None:
            return self._create(self._address, self._profile)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "model": self._profile.model,
                "address": self._address,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick from supported devices currently in range."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            profile = profile_for(self._discovered.get(address))
            if profile is None:
                return self.async_abort(reason="not_supported")
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self._create(address, profile)

        current = self._async_current_ids()
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in current or profile_for(info.name) is None:
                continue
            self._discovered[info.address] = info.name

        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            addr: f"{name} ({addr})"
                            for addr, name in self._discovered.items()
                        }
                    )
                }
            ),
        )

    def _create(self, address: str, profile: DeviceProfile) -> ConfigFlowResult:
        return self.async_create_entry(
            title=profile.model,
            data={CONF_ADDRESS: address, CONF_MODEL: profile.model},
        )
