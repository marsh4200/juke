"""Per-device diagnostic sensors (CPU/RAM/disk/temperature, input status) for
Juke Audio.

Inputs are intentionally *not* their own entities/devices - a system with a
handful of inputs would otherwise spawn a device and two entities per input,
which is a lot of clutter for what's fundamentally diagnostic information.
Instead, streaming/enabled state for every input is rolled into a single
"Streaming inputs" sensor's attributes, alongside the existing device metrics.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import JukeCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class JukeSensorDescription(SensorEntityDescription):
    """Describes a Juke device metric sensor."""

    value_fn: Callable[[dict], float | int | None] = lambda metrics: None


SENSOR_DESCRIPTIONS: tuple[JukeSensorDescription, ...] = (
    JukeSensorDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda metrics: metrics.get("cpu_usage"),
    ),
    JukeSensorDescription(
        key="ram_usage",
        translation_key="ram_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda metrics: metrics.get("ram_usage"),
    ),
    JukeSensorDescription(
        key="disk_usage",
        translation_key="disk_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda metrics: metrics.get("disk_usage"),
    ),
    JukeSensorDescription(
        key="internal_temp",
        translation_key="internal_temp",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda metrics: metrics.get("internal_temp"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Juke device metric sensors from a config entry."""
    store = hass.data[DOMAIN][entry.entry_id]
    coordinator: JukeCoordinator = store["coordinator"]

    known_device_ids: set[str] = set()

    @callback
    def _add_new_devices() -> None:
        new_entities = []
        for device_id in coordinator.data.devices:
            if device_id in known_device_ids:
                continue
            known_device_ids.add(device_id)
            for description in SENSOR_DESCRIPTIONS:
                new_entities.append(
                    JukeDeviceSensor(coordinator, entry.entry_id, device_id, description)
                )
            new_entities.append(
                JukeInputsSensor(coordinator, entry.entry_id, device_id)
            )
        if new_entities:
            async_add_entities(new_entities)

    _add_new_devices()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_devices))


class JukeDeviceSensor(CoordinatorEntity[JukeCoordinator], SensorEntity):
    """A single metric (CPU/RAM/disk/temp) for a Juke physical device."""

    _attr_has_entity_name = True
    entity_description: JukeSensorDescription

    def __init__(
        self,
        coordinator: JukeCoordinator,
        entry_id: str,
        device_id: str,
        description: JukeSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_device_{device_id}_{description.key}"

    @property
    def _device(self) -> dict:
        return self.coordinator.data.devices.get(self._device_id, {})

    @property
    def available(self) -> bool:
        return super().available and self._device_id in self.coordinator.data.devices

    @property
    def device_info(self) -> DeviceInfo:
        device = self._device
        attributes = device.get("attributes") or {}
        config = device.get("config") or {}
        return DeviceInfo(
            identifiers={(DOMAIN, f"device_{self._device_id}")},
            name=config.get("name") or self._device_id,
            manufacturer=MANUFACTURER,
            model="Juke Audio Device",
            sw_version=attributes.get("firmware_version"),
            serial_number=attributes.get("serial_number"),
        )

    @property
    def native_value(self) -> float | int | None:
        metrics = self._device.get("metrics") or {}
        return self.entity_description.value_fn(metrics)


class JukeInputsSensor(CoordinatorEntity[JukeCoordinator], SensorEntity):
    """Summarizes every input's streaming/enabled state as one entity.

    The state is how many inputs are actively streaming right now; the full
    per-input breakdown (streaming + enabled) lives in the attributes, so
    it's still there for automations/templates without needing its own
    entity per input.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "streaming_inputs"
    _attr_icon = "mdi:audio-input-rca"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "inputs"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: JukeCoordinator,
        entry_id: str,
        device_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_device_{device_id}_streaming_inputs"

    @property
    def _device(self) -> dict:
        return self.coordinator.data.devices.get(self._device_id, {})

    @property
    def available(self) -> bool:
        return super().available and self._device_id in self.coordinator.data.devices

    @property
    def device_info(self) -> DeviceInfo:
        device = self._device
        attributes = device.get("attributes") or {}
        config = device.get("config") or {}
        return DeviceInfo(
            identifiers={(DOMAIN, f"device_{self._device_id}")},
            name=config.get("name") or self._device_id,
            manufacturer=MANUFACTURER,
            model="Juke Audio Device",
            sw_version=attributes.get("firmware_version"),
            serial_number=attributes.get("serial_number"),
        )

    @property
    def native_value(self) -> int:
        return sum(1 for i in self.coordinator.data.inputs.values() if i.get("streaming"))

    @property
    def extra_state_attributes(self) -> dict[str, dict]:
        return {
            (info.get("name") or input_id): {
                "streaming": bool(info.get("streaming")),
                "enabled": bool(info.get("enabled")),
            }
            for input_id, info in self.coordinator.data.inputs.items()
        }
