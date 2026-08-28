"""Juke zones and inputs exposed as Home Assistant media_player entities.

The Juke API has no transport/playback state (no play/pause/track info) -
a zone is really an audio output with volume, mute, mono and a selectable
input ("source"). We map that as closely as possible onto the media_player
entity model: on/off = zone enabled, source = active input, source_list =
the inputs assigned to that zone.

Inputs (General / Restricted General classes) get their own media_player
entity too - on/off = input enabled, volume where the API supports it
(USB/RCA/Optical), and source/source_list = the input's type, selectable
only for General-class inputs (the API rejects type changes on Restricted
General ones). Zone-based Spotify/AirPlay2 pseudo-inputs (classes 1/2) are
skipped - they're tightly coupled to a single zone and aren't independently
useful as an entity.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
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

# Input classes the Juke API documents as freely usable/mappable:
# 0 = General, 3 = Restricted General. Classes 1/2 (Spotify/AirPlay2
# zone-based pseudo-inputs) are excluded - see module docstring.
INPUT_ENTITY_CLASSES = (0, 3)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Juke zone and input media_player entities from a config entry."""
    store = hass.data[DOMAIN][entry.entry_id]
    coordinator: JukeCoordinator = store["coordinator"]
    client: JukeApiClient = store["client"]

    known_zone_ids: set[str] = set()
    known_input_ids: set[str] = set()

    @callback
    def _add_new_entities() -> None:
        new_entities = []
        for zone_id in coordinator.data.zones:
            if zone_id in known_zone_ids:
                continue
            known_zone_ids.add(zone_id)
            new_entities.append(JukeZoneMediaPlayer(coordinator, client, entry.entry_id, zone_id))

        for input_id, info in coordinator.data.inputs.items():
            if input_id in known_input_ids:
                continue
            known_input_ids.add(input_id)
            if info.get("input_class") not in INPUT_ENTITY_CLASSES:
                continue
            new_entities.append(JukeInputMediaPlayer(coordinator, client, entry.entry_id, input_id))

        if new_entities:
            async_add_entities(new_entities)

    _add_new_entities()
    entry.async_on_unload(coordinator.async_add_listener(_add_new_entities))


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
            action = "enable" if enable else "disable"
            _LOGGER.error("Failed to %s zone %s: %s", action, self._zone_id, err)
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


class JukeInputMediaPlayer(CoordinatorEntity[JukeCoordinator], MediaPlayerEntity):
    """A single Juke input (General or Restricted General class)."""

    _attr_has_entity_name = True
    _attr_device_class = MediaPlayerDeviceClass.RECEIVER

    def __init__(
        self,
        coordinator: JukeCoordinator,
        client: JukeApiClient,
        entry_id: str,
        input_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._input_id = input_id
        self._attr_unique_id = f"{entry_id}_input_{input_id}"

    @property
    def _input(self) -> dict:
        return self.coordinator.data.inputs.get(self._input_id, {})

    @property
    def available(self) -> bool:
        return super().available and self._input_id in self.coordinator.data.inputs

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"input_{self._input_id}")},
            name=self._input.get("name") or self._input_id,
            manufacturer=MANUFACTURER,
            model="Juke Input",
        )

    @property
    def name(self) -> str | None:
        return self._input.get("name") or self._input_id

    @property
    def state(self) -> MediaPlayerState:
        if not self._input.get("enabled", True):
            return MediaPlayerState.OFF
        return MediaPlayerState.ON

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        features = MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF
        # The API only allows changing an input's type on General (class 0)
        # inputs - Restricted General (class 3) rejects it outright.
        if self._input.get("input_class") == 0:
            features |= MediaPlayerEntityFeature.SELECT_SOURCE
        # Volume only applies to USB/RCA/Optical inputs per the API docs;
        # everything else reports volume as null.
        if self._input.get("volume") is not None:
            features |= MediaPlayerEntityFeature.VOLUME_SET
        return features

    @property
    def volume_level(self) -> float | None:
        volume = self._input.get("volume")
        if volume is None:
            return None
        return volume / JUKE_VOLUME_MAX

    @property
    def source(self) -> str | None:
        return self._input.get("input_type")

    @property
    def source_list(self) -> list[str]:
        types = list(self._input.get("available_types") or [])
        current = self.source
        if current and current not in types:
            types.append(current)
        return types

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        input_info = self._input
        return {
            "input_class": input_info.get("input_class"),
            "streaming": input_info.get("streaming"),
            "zones": input_info.get("zones"),
        }

    async def async_turn_on(self) -> None:
        await self._set_enabled(True)

    async def async_turn_off(self) -> None:
        await self._set_enabled(False)

    async def _set_enabled(self, enable: bool) -> None:
        try:
            await self._client.set_input_enabled(self._input_id, enable)
        except JukeApiError as err:
            action = "enable" if enable else "disable"
            _LOGGER.error("Failed to %s input %s: %s", action, self._input_id, err)
            return
        await self.coordinator.async_request_refresh()

    async def async_set_volume_level(self, volume: float) -> None:
        try:
            await self._client.set_input_volume(self._input_id, round(volume * JUKE_VOLUME_MAX))
        except JukeApiError as err:
            _LOGGER.error("Failed to set volume for input %s: %s", self._input_id, err)
            return
        await self.coordinator.async_request_refresh()

    async def async_select_source(self, source: str) -> None:
        try:
            await self._client.set_input_type(self._input_id, source)
        except JukeApiError as err:
            _LOGGER.error("Failed to set type for input %s: %s", self._input_id, err)
            return
        await self.coordinator.async_request_refresh()
