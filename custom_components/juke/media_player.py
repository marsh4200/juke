"""Juke zones exposed as Home Assistant media_player entities.

The Juke API has no transport/playback state (no play/pause/track info) -
a zone is really an audio output with volume, mute, mono and a selectable
input ("source"). We map that as closely as possible onto the media_player
entity model: on/off = zone enabled, source = active input, source_list =
the inputs assigned to that zone.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import JukeApiClient, JukeApiError
from .const import DOMAIN, JUKE_VOLUME_MAX, MANUFACTURER
from .coordinator import JukeCoordinator

_LOGGER = logging.getLogger(__name__)

SUPPORTED_FEATURES = (
    MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.SELECT_SOURCE
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Juke zone media_player entities from a config entry."""
    store = hass.data[DOMAIN][entry.entry_id]
    coordinator: JukeCoordinator = store["coordinator"]
    client: JukeApiClient = store["client"]

    known_zone_ids: set[str] = set()

    @callback
    def _add_new_zones() -> None:
        new_entities = []
        for zone_id in coordinator.data.zones:
            if zone_id in known_zone_ids:
                continue
            known_zone_ids.add(zone_id)
            new_entities.append(JukeZoneMediaPlayer(coordinator, client, entry.entry_id, zone_id))
        if new_entities:
            async_add_entities(new_entities)

    _add_new_zones()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_zones))


class JukeZoneMediaPlayer(CoordinatorEntity[JukeCoordinator], MediaPlayerEntity):
    """A single Juke zone (physical audio output)."""

    _attr_has_entity_name = True
    _attr_supported_features = SUPPORTED_FEATURES
    _attr_name = None

    def __init__(
        self,
        coordinator: JukeCoordinator,
        client: JukeApiClient,
        entry_id: str,
        zone_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._zone_id = zone_id
        self._attr_unique_id = f"{entry_id}_zone_{zone_id}"

    @property
    def _zone(self) -> dict:
        return self.coordinator.data.zones.get(self._zone_id, {})

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"zone_{self._zone_id}")},
            name=self._zone.get("name") or self._zone.get("label") or self._zone_id,
            manufacturer=MANUFACTURER,
            model="Juke Zone",
        )

    @property
    def available(self) -> bool:
        return super().available and self._zone_id in self.coordinator.data.zones

    @property
    def name(self) -> str | None:
        return self._zone.get("name") or self._zone.get("label")

    @property
    def state(self) -> MediaPlayerState:
        if not self._zone.get("enabled", False):
            return MediaPlayerState.OFF
        return MediaPlayerState.ON

    @property
    def volume_level(self) -> float | None:
        volume = self._zone.get("volume")
        if volume is None:
            return None
        return volume / JUKE_VOLUME_MAX

    @property
    def is_volume_muted(self) -> bool | None:
        return self._zone.get("muted")

    @property
    def source(self) -> str | None:
        return self.coordinator.data.input_name(self._zone.get("active_input"))

    @property
    def source_list(self) -> list[str]:
        input_ids = self._zone.get("input") or []
        names = [self.coordinator.data.input_name(i) for i in input_ids]
        return [n for n in names if n]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        zone = self._zone
        return {
            "mono": zone.get("mono"),
            "volume_eq": zone.get("volume_eq"),
            "sampling_rate": zone.get("sampling_rate"),
            "warnings": zone.get("warnings"),
        }

    def _input_id_for_source(self, source: str) -> str | None:
        for input_id in self._zone.get("input") or []:
            if self.coordinator.data.input_name(input_id) == source:
                return input_id
        return None

    async def async_turn_on(self) -> None:
        await self._set_enabled(True)

    async def async_turn_off(self) -> None:
        await self._set_enabled(False)

    async def _set_enabled(self, enable: bool) -> None:
        try:
            await self._client.set_zone_enabled(self._zone_id, enable)
        except JukeApiError as err:
            _LOGGER.error("Failed to %s zone %s: %s", "enable" if enable else "disable", self._zone_id, err)
            return
        await self.coordinator.async_request_refresh()

    async def async_set_volume_level(self, volume: float) -> None:
        try:
            await self._client.set_zone_volume(self._zone_id, round(volume * JUKE_VOLUME_MAX))
        except JukeApiError as err:
            _LOGGER.error("Failed to set volume for zone %s: %s", self._zone_id, err)
            return
        await self.coordinator.async_request_refresh()

    async def async_mute_volume(self, mute: bool) -> None:
        try:
            await self._client.set_zone_muted(self._zone_id, mute)
        except JukeApiError as err:
            _LOGGER.error("Failed to mute zone %s: %s", self._zone_id, err)
            return
        await self.coordinator.async_request_refresh()

    async def async_select_source(self, source: str) -> None:
        input_id = self._input_id_for_source(source)
        if input_id is None:
            _LOGGER.warning("Unknown source %s for zone %s", source, self._zone_id)
            return
        try:
            await self._client.set_zone_active_input(self._zone_id, input_id)
        except JukeApiError as err:
            _LOGGER.error("Failed to set source for zone %s: %s", self._zone_id, err)
            return
        await self.coordinator.async_request_refresh()
