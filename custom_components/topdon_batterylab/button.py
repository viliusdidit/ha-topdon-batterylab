"""Charge-control buttons for TOPDON BatteryLab devices."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TopdonConfigEntry
from .entity import TopdonEntity
from .protocol import build

# Proven on TB6000Pro hardware (tools/tb6000pro/charge_session.py): three frames,
# written ~2.5 s apart while the device is idle, start a 12 V-Norm charge.
# Mode byte 1 = the 12 V Norm family (the app remaps its UI index 0/3 -> 1).
_MODE_12V_NORM = 1
_START_CHARGE_FRAMES = (
    build((0xBF, 0x05), _MODE_12V_NORM),  # SET_CHARGING_MODE
    build((0xBF, 0x04), 1),               # SET_FUNCTION_MODE
    build((0xBF, 0x0B), 1, 1),            # SET_START_CHARGE
)
# No stop button by design: BF0C SET_END_CHARGING only ACKs — BF00[11] never
# returns to its pre-charge value, so a stop cannot be confirmed (see repo
# docs/PROTOCOL.md). Stop the charger by cutting its mains power (a Shelly smart
# plug with metering), not over BLE.


@dataclass(frozen=True, kw_only=True)
class TopdonButtonDescription(ButtonEntityDescription):
    """A button that writes a fixed sequence of command frames."""

    frames: tuple[bytes, ...]


BUTTONS: tuple[TopdonButtonDescription, ...] = (
    TopdonButtonDescription(
        key="start_charge",
        translation_key="start_charge",
        frames=_START_CHARGE_FRAMES,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TopdonConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the charge-control buttons."""
    coordinator = entry.runtime_data
    async_add_entities(TopdonButton(coordinator, d) for d in BUTTONS)


class TopdonButton(TopdonEntity, ButtonEntity):
    """Writes a command sequence to the charger when pressed."""

    entity_description: TopdonButtonDescription

    def __init__(self, coordinator, description: TopdonButtonDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        # A press opens its own connection, so the button stays pressable even if
        # the last poll failed (e.g. a transient drop while the device is idle);
        # a failed press raises to the user instead of greying out.
        return True

    async def async_press(self) -> None:
        try:
            await self.coordinator.async_send_command(self.entity_description.frames)
        except HomeAssistantError:
            raise
        except Exception as err:  # noqa: BLE001 - surface any BLE failure to the user
            raise HomeAssistantError(
                "Could not reach the TOPDON charger — is it powered and "
                f"advertising (not already mid-charge)? {err}"
            ) from err
