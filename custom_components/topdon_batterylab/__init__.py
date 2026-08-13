"""The TOPDON BatteryLab integration."""

from __future__ import annotations

import re

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ConfigEntryError, HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import CONF_MODEL, DOMAIN
from .coordinator import TopdonCoordinator
from .devices import DEVICES
from .protocol import build

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR]

type TopdonConfigEntry = ConfigEntry[TopdonCoordinator]

SERVICE_EXCHANGE = "exchange"

EXCHANGE_SCHEMA = vol.Schema(
    {
        vol.Required("commands"): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional("listen", default=5.0): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=120)
        ),
        vol.Optional("gap", default=2.5): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=30)
        ),
    }
)


def _parse_command(text: str) -> bytes:
    """Turn hex into a framed command (opcode is the first two bytes).

    Accepts any of "BF00", "BF 00", "bf05 01", "BF:05:01" - separators and an
    0x prefix are ignored, so a two-byte opcode may be written either as one
    token or as two.
    """
    cleaned = re.sub(r"(?i)0x|[\s,:;_-]", "", text)
    if len(cleaned) < 4 or len(cleaned) % 2:
        raise HomeAssistantError(
            f"{text!r} must be an even number of hex digits, at least a "
            "two-byte opcode"
        )
    try:
        data = bytes.fromhex(cleaned)
    except ValueError as err:
        raise HomeAssistantError(f"{text!r} is not hex") from err
    return build((data[0], data[1]), *data[2:])


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
    _async_register_services(hass)
    return True


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the protocol-exploration service once."""
    if hass.services.has_service(DOMAIN, SERVICE_EXCHANGE):
        return

    async def _async_exchange(call: ServiceCall) -> dict[str, list[str]]:
        """Write raw commands and return every notification heard afterwards.

        Deliberately does not require the reply to decode, so it works on
        opcodes whose payload layout is still unknown.
        """
        loaded = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.state is ConfigEntryState.LOADED
        ]
        if not loaded:
            raise HomeAssistantError("no loaded TOPDON entry")
        coordinator: TopdonCoordinator = loaded[0].runtime_data
        frames = [_parse_command(c) for c in call.data["commands"]]
        heard = await coordinator.async_exchange(
            frames, listen=call.data["listen"], gap=call.data["gap"]
        )
        return {"frames": heard}

    hass.services.async_register(
        DOMAIN,
        SERVICE_EXCHANGE,
        _async_exchange,
        schema=EXCHANGE_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


async def async_unload_entry(hass: HomeAssistant, entry: TopdonConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded and not [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED and e.entry_id != entry.entry_id
    ]:
        hass.services.async_remove(DOMAIN, SERVICE_EXCHANGE)
    return unloaded
