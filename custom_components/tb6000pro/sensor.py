"""Sensors for the TB6000Pro."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfElectricPotential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import TB6000ConfigEntry
from .entity import TB6000Entity
from .protocol import ChargerState


@dataclass(frozen=True, kw_only=True)
class TB6000SensorDescription(SensorEntityDescription):
    """Sensor description with a value extractor."""

    value_fn: Callable[[ChargerState], float | int | str | None]


SENSORS: tuple[TB6000SensorDescription, ...] = (
    TB6000SensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
        value_fn=lambda s: s.voltage,
    ),
    TB6000SensorDescription(
        key="charge_step",
        translation_key="charge_step",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:stairs",
        value_fn=lambda s: s.step,
    ),
    TB6000SensorDescription(
        key="mode",
        translation_key="mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:tune",
        value_fn=lambda s: s.mode,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TB6000ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    async_add_entities(TB6000Sensor(coordinator, d) for d in SENSORS)


class TB6000Sensor(TB6000Entity, SensorEntity):
    """A single decoded field."""

    entity_description: TB6000SensorDescription

    def __init__(self, coordinator, description: TB6000SensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | str | None:
        if (data := self.coordinator.data) is None:
            return None
        return self.entity_description.value_fn(data)
