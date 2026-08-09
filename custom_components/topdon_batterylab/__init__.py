"""The TOPDON BatteryLab integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError

from .const import CONF_MODEL
from .coordinator import TopdonCoordinator
from .devices import DEVICES

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

type TopdonConfigEntry = ConfigEntry[TopdonCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: TopdonConfigEntry) -> bool:
    """Set up a TOPDON device from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    model: str = entry.data[CONF_MODEL]

    profile = DEVICES.get(model)
    if profile is None:
        raise ConfigEntryError(f"unsupported model {model!r}")

    coordinator = TopdonCoordinator(hass, address, profile)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TopdonConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
