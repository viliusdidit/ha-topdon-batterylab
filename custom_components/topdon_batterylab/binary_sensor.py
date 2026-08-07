"""Binary sensors for TOPDON BatteryLab devices."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TopdonConfigEntry
from .devices import FLOAT_STEPS
from .entity import TopdonEntity

DESCRIPTION = BinarySensorEntityDescription(
    key="charging",
    translation_key="charging",
    device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TopdonConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the charging binary sensor."""
    coordinator = entry.runtime_data
    if DESCRIPTION.key in coordinator.profile.supported_keys:
        async_add_entities([TopdonCharging(coordinator, DESCRIPTION)])


class TopdonCharging(TopdonEntity, BinarySensorEntity):
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
        attrs: dict[str, str | bool] = {"raw_payload": data.raw}
        if data.step is not None:
            # Steps 8/9 alternate during float; distinguishes "still bulk
            # charging" from "topped off and maintaining".
            attrs["maintaining"] = data.step in FLOAT_STEPS
        return attrs
