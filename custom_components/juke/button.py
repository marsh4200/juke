"""Reboot button for each physical Juke device."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import JukeApiClient, JukeApiError
from .const import DOMAIN, MANUFACTURER
from .coordinator import JukeCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Juke device reboot button from a config entry."""
    store = hass.data[DOMAIN][entry.entry_id]
    coordinator: JukeCoordinator = store["coordinator"]
    client: JukeApiClient = store["client"]

    known_device_ids: set[str] = set()

    @callback
    def _add_new_devices() -> None:
        new_entities = []
        for device_id in coordinator.data.devices:
            if device_id in known_device_ids:
                continue
            known_device_ids.add(device_id)
            new_entities.append(
                JukeRebootButton(coordinator, client, entry.entry_id, device_id)
            )
        if new_entities:
            async_add_entities(new_entities)

    _add_new_devices()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_devices))


class JukeRebootButton(CoordinatorEntity[JukeCoordinator], ButtonEntity):
    """Reboots the physical Juke device this entity belongs to."""

    _attr_has_entity_name = True
    _attr_translation_key = "reboot"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: JukeCoordinator,
        client: JukeApiClient,
        entry_id: str,
        device_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._device_id = device_id
        self._attr_unique_id = f"{entry_id}_device_{device_id}_reboot"

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

    async def async_press(self) -> None:
        """Reboot the device. This drops audio on every zone it serves."""
        try:
            await self._client.reboot_device(self._device_id)
        except JukeApiError as err:
            _LOGGER.error("Failed to reboot device %s: %s", self._device_id, err)
