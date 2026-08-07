"""Sensors for TOPDON BatteryLab devices."""

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

from . import TopdonConfigEntry
from .devices import DeviceState
from .entity import TopdonEntity


@dataclass(frozen=True, kw_only=True)
class TopdonSensorDescription(SensorEntityDescription):
    """Sensor description with a value extractor."""

    value_fn: Callable[[DeviceState], float | int | None]


SENSORS: tuple[TopdonSensorDescription, ...] = (
    TopdonSensorDescription(
        key="voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=2,
        value_fn=lambda s: s.voltage,
    ),
    TopdonSensorDescription(
        key="step",
        translation_key="charge_step",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:stairs",
        value_fn=lambda s: s.step,
    ),
    TopdonSensorDescription(
        key="mode",
        translation_key="mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:tune",
        value_fn=lambda s: s.mode,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: TopdonConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors the connected model actually supports."""
    coordinator = entry.runtime_data
    supported = coordinator.profile.supported_keys
    async_add_entities(
        TopdonSensor(coordinator, d) for d in SENSORS if d.key in supported
    )


class TopdonSensor(TopdonEntity, SensorEntity):
    """A single decoded field."""

    entity_description: TopdonSensorDescription

    def __init__(self, coordinator, description: TopdonSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | None:
        if (data := self.coordinator.data) is None:
            return None
        return self.entity_description.value_fn(data)
