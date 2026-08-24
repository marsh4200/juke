"""DataUpdateCoordinator for the Juke Audio integration."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import JukeApiClient, JukeApiError
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


@dataclass
class JukeData:
    """Snapshot of everything the integration polls, keyed by id."""

    zones: dict[str, dict] = field(default_factory=dict)
    devices: dict[str, dict] = field(default_factory=dict)
    inputs: dict[str, dict] = field(default_factory=dict)

    def input_name(self, input_id: str | None) -> str | None:
        """Look up a friendly input name for a source select widget."""
        if not input_id:
            return None
        info = self.inputs.get(input_id)
        return info["name"] if info else input_id


class JukeCoordinator(DataUpdateCoordinator[JukeData]):
    """Polls a Juke device for zones/devices/inputs state."""

    def __init__(self, hass: HomeAssistant, client: JukeApiClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> JukeData:
        try:
            async with asyncio.timeout(20):
                zones_info, devices_info, inputs_info = await asyncio.gather(
                    self.client.get_zones_info(),
                    self.client.get_devices_info(),
                    self.client.get_inputs_info(),
                )
        except JukeApiError as err:
            raise UpdateFailed(f"Error communicating with Juke device: {err}") from err

        return JukeData(
            zones={z["zone_id"]: z for z in zones_info},
            devices={d["device_id"]: d for d in devices_info},
            inputs={i["input_id"]: i for i in inputs_info},
        )
