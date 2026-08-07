"""The TOPDON TB6000Pro integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .coordinator import TB6000Coordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

type TB6000ConfigEntry = ConfigEntry[TB6000Coordinator]


async def async_setup_entry(hass: HomeAssistant, entry: TB6000ConfigEntry) -> bool:
    """Set up TB6000Pro from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    coordinator = TB6000Coordinator(hass, address)

    # The charger is only reachable when it is in range of an adapter or proxy;
    # if the first poll fails HA will retry rather than leaving dead entities.
    await coordinator.async_config_entry_first_refresh()
    if coordinator.data is None:
        raise ConfigEntryNotReady(f"no data from {address}")

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TB6000ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
