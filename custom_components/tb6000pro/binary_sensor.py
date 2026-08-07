"""Binary sensors for the TB6000Pro."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TB6000ConfigEntry
from .const import FLOAT_STEPS
from .entity import TB6000Entity

DESCRIPTION = BinarySensorEntityDescription(
    key="charging",
    translation_key="charging",
    device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TB6000ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the charging binary sensor."""
    async_add_entities([TB6000Charging(entry.runtime_data, DESCRIPTION)])


class TB6000Charging(TB6000Entity, BinarySensorEntity):
    """True while a charge session is active."""

    def __init__(self, coordinator, description) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        if (data := self.coordinator.data) is None:
            return None
        return data.charging

    @property
    def extra_state_attributes(self) -> dict[str, str | bool]:
        if (data := self.coordinator.data) is None:
            return {}
        return {
            # Steps 8/9 alternate during float; useful for distinguishing
            # "still bulk charging" from "topped off and maintaining".
            "maintaining": data.step in FLOAT_STEPS,
            "raw_payload": data.raw,
        }
