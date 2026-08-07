"""Diagnostics for the TB6000Pro."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from . import TB6000ConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: TB6000ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "address": coordinator.address,
        "last_update_success": coordinator.last_update_success,
        "state": asdict(coordinator.data) if coordinator.data else None,
    }
