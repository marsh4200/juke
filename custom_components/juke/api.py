"""Thin async client for the Juke Audio local REST API (v3).

Reference: https://sim.jukeaudio.com/api/v3/apidocs/

The Juke box exposes a Flask/Flasgger API on the local network, secured with
HTTP Basic Auth (default credentials are Admin/Admin). This client only wraps
the handful of endpoints the Home Assistant integration needs: zones,
devices, and inputs.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
from aiohttp import BasicAuth, ClientTimeout

from .const import API_BASE_PATH

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = ClientTimeout(total=10)


class JukeApiError(Exception):
    """Generic error talking to a Juke device."""


class JukeAuthError(JukeApiError):
    """Raised on HTTP 401/403 - bad username/password."""


class JukeConnectionError(JukeApiError):
    """Raised when the device can't be reached at all."""


class JukeApiClient:
    """Minimal async wrapper around the Juke v3 REST API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int = 80,
        username: str = "Admin",
        password: str = "Admin",
        use_ssl: bool = False,
        verify_ssl: bool = True,
    ) -> None:
        self._session = session
        scheme = "https" if use_ssl else "http"
        self._base_url = f"{scheme}://{host}:{port}{API_BASE_PATH}"
        self._auth = BasicAuth(username, password)
        self._ssl = None if verify_ssl else False

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict | None = None,
        auth: bool = True,
    ) -> Any:
        url = f"{self._base_url}{path}"
        try:
            async with self._session.request(
                method,
                url,
                json=json,
                params=params,
                auth=self._auth if auth else None,
                timeout=DEFAULT_TIMEOUT,
                ssl=self._ssl,
            ) as resp:
                if resp.status in (401, 403):
                    raise JukeAuthError(f"Authentication failed for {url} (HTTP {resp.status})")
                if resp.status >= 400:
                    body = await resp.text()
                    raise JukeApiError(f"Juke API error {resp.status} for {method} {url}: {body}")
                if resp.content_type == "application/json":
                    return await resp.json()
                return await resp.text()
        except JukeApiError:
            raise
        except (TimeoutError, aiohttp.ClientConnectorError) as err:
            raise JukeConnectionError(f"Could not reach Juke device at {url}") from err
        except aiohttp.ClientError as err:
            raise JukeApiError(f"Unexpected error calling {url}: {err}") from err

    # ------------------------------------------------------------------
    # Ping (unauthenticated connectivity check)
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Return True if the device answers /ping."""
        await self._request("GET", "/ping", auth=False)
        return True

    # ------------------------------------------------------------------
    # Zones
    # ------------------------------------------------------------------

    async def get_zone_ids(self) -> list[str]:
        data = await self._request("GET", "/zones")
        return data.get("zone_ids", [])

    async def get_zones_info(self) -> list[dict]:
        """Return the full ZoneInfo list for every zone."""
        return await self._request("GET", "/zones/info")

    async def get_zone_info(self, zone_id: str) -> dict:
        return await self._request("GET", f"/zones/{zone_id}")

    async def set_zone_enabled(self, zone_id: str, enable: bool) -> None:
        await self._request("PUT", f"/zones/{zone_id}/enable", json={"enable": enable})

    async def set_zone_volume(self, zone_id: str, volume: int) -> None:
        volume = max(0, min(100, int(volume)))
        await self._request("PUT", f"/zones/{zone_id}/volume", json={"volume": volume})

    async def set_zone_volume_eq(self, zone_id: str, volume_eq: list[int]) -> None:
        await self._request("PUT", f"/zones/{zone_id}/volume_eq", json={"volume_eq": volume_eq})

    async def set_zone_muted(self, zone_id: str, enable: bool) -> None:
        await self._request("PUT", f"/zones/{zone_id}/mute", json={"enable": enable})

    async def set_zone_mono(self, zone_id: str, enable: bool) -> None:
        await self._request("PUT", f"/zones/{zone_id}/mono", json={"enable": enable})

    async def set_zone_name(self, zone_id: str, name: str) -> None:
        await self._request("PUT", f"/zones/{zone_id}/name", json={"name": name})

    async def get_zone_active_input(self, zone_id: str) -> str:
        return await self._request("GET", f"/zones/{zone_id}/input/active")

    async def set_zone_active_input(self, zone_id: str, input_id: str) -> None:
        await self._request("PUT", f"/zones/{zone_id}/input/active", json={"input_id": input_id})

    async def set_zone_inputs(self, zone_id: str, input_ids: list[str]) -> None:
        await self._request("PUT", f"/zones/{zone_id}/input", json={"input_ids": input_ids})

    async def add_zone_input(self, zone_id: str, input_ids: list[str]) -> None:
        await self._request("PUT", f"/zones/{zone_id}/input/add", json={"input_ids": input_ids})

    async def remove_zone_input(self, zone_id: str, input_ids: list[str]) -> None:
        await self._request("PUT", f"/zones/{zone_id}/input/remove", json={"input_ids": input_ids})

    async def get_zone_warnings(self, zone_id: str) -> dict:
        return await self._request("GET", f"/zones/{zone_id}/warnings")

    # ------------------------------------------------------------------
    # Inputs
    # ------------------------------------------------------------------

    async def get_input_ids(self, class_filter: int | None = None) -> list[str]:
        params = {"class_filter": class_filter} if class_filter is not None else None
        data = await self._request("GET", "/inputs", params=params)
        return data.get("input_ids", [])

    async def get_inputs_info(self, class_filter: int | None = None) -> list[dict]:
        """Return the full InputInfo list for every input."""
        params = {"class_filter": class_filter} if class_filter is not None else None
        return await self._request("GET", "/inputs/info", params=params)

    async def get_input_info(self, input_id: str) -> dict:
        return await self._request("GET", f"/inputs/{input_id}")

    async def set_input_name(self, input_id: str, name: str) -> None:
        await self._request("PUT", f"/inputs/{input_id}/name", json={"name": name})

    async def set_input_enabled(self, input_id: str, enable: bool) -> None:
        await self._request("PUT", f"/inputs/{input_id}/enable", json={"enable": enable})

    async def set_input_volume(self, input_id: str, volume: int) -> None:
        volume = max(0, min(100, int(volume)))
        await self._request("PUT", f"/inputs/{input_id}/volume", json={"volume": volume})

    async def set_input_type(self, input_id: str, input_type: str) -> None:
        await self._request("PUT", f"/inputs/{input_id}/type", json={"type": input_type})

    # ------------------------------------------------------------------
    # Devices
    # ------------------------------------------------------------------

    async def get_device_ids(self) -> list[str]:
        data = await self._request("GET", "/devices")
        return data.get("device_ids", [])

    async def get_devices_info(self) -> list[dict]:
        """Return the full DeviceInfo list (attributes/config/connection/metrics)."""
        return await self._request("GET", "/devices/info")

    async def get_device_attributes(self, device_id: str) -> dict:
        return await self._request("GET", f"/devices/{device_id}/attributes")

    async def get_device_metrics(self, device_id: str) -> dict:
        return await self._request("GET", f"/devices/{device_id}/metrics")

    async def get_device_model(self, device_id: str) -> str:
        return await self._request("GET", f"/devices/{device_id}/model")

    async def set_device_name(self, device_id: str, name: str) -> None:
        await self._request("PUT", f"/devices/{device_id}/name", json={"name": name})

    async def reboot_device(self, device_id: str) -> None:
        await self._request("POST", f"/devices/{device_id}/reboot")
