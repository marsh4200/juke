"""Per-input binary sensors for Juke Audio.

Exposes the two fields on `GET /inputs/info` that are actually useful as
automation triggers/state: `streaming` (is audio actively flowing right now
- the closest thing this API has to a "now playing" signal) and `enabled`
(is the input turned on in the system at all). Everything else on an input
(type, credentials, threshold, sampling rate) is setup-time configuration
that belongs in the Juke app, not in Home Assistant.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import JukeCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class JukeInputBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a Juke input binary sensor."""

    value_fn: Callable[[dict], bool | None] = lambda input_info: None


SENSOR_DESCRIPTIONS: tuple[JukeInputBinarySensorDescription, ...] = (
    JukeInputBinarySensorDescription(
        key="streaming",
        translation_key="streaming",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda input_info: input_info.get("streaming"),
    ),
    JukeInputBinarySensorDescription(
        key="enabled",
        translation_key="input_enabled",
        value_fn=lambda input_info: input_info.get("enabled"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Juke input binary sensors from a config entry."""
    store = hass.data[DOMAIN][entry.entry_id]
    coordinator: JukeCoordinator = store["coordinator"]

    known_input_ids: set[str] = set()

    @callback
    def _add_new_inputs() -> None:
        new_entities = []
        for input_id in coordinator.data.inputs:
            if input_id in known_input_ids:
                continue
            known_input_ids.add(input_id)
            for description in SENSOR_DESCRIPTIONS:
                new_entities.append(
                    JukeInputBinarySensor(coordinator, entry.entry_id, input_id, description)
                )
        if new_entities:
            async_add_entities(new_entities)

    _add_new_inputs()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_inputs))


class JukeInputBinarySensor(CoordinatorEntity[JukeCoordinator], BinarySensorEntity):
    """Streaming/enabled state for a single Juke input."""

    _attr_has_entity_name = True
    entity_description: JukeInputBinarySensorDescription

    def __init__(
        self,
        coordinator: JukeCoordinator,
        entry_id: str,
        input_id: str,
        description: JukeInputBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._input_id = input_id
        self._attr_unique_id = f"{entry_id}_input_{input_id}_{description.key}"

    @property
    def _input(self) -> dict:
        return self.coordinator.data.inputs.get(self._input_id, {})

    @property
    def available(self) -> bool:
        return super().available and self._input_id in self.coordinator.data.inputs

    @property
    def device_info(self) -> DeviceInfo:
        input_info = self._input
        return DeviceInfo(
            identifiers={(DOMAIN, f"input_{self._input_id}")},
            name=input_info.get("name") or self._input_id,
            manufacturer=MANUFACTURER,
            model="Juke Input",
        )

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self._input)
