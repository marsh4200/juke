"""Config flow for the Juke Audio integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

try:  # HA >= 2024.6
    from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
except ImportError:  # pragma: no cover - older HA
    from homeassistant.components.dhcp import DhcpServiceInfo

try:  # HA >= 2024.5
    from homeassistant.config_entries import ConfigFlowResult
except ImportError:  # pragma: no cover - older HA
    from homeassistant.data_entry_flow import FlowResult as ConfigFlowResult

from .api import JukeApiClient, JukeAuthError, JukeConnectionError, JukeApiError
from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_PASSWORD,
    DEFAULT_PORT,
    DEFAULT_SSL,
    DEFAULT_USERNAME,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _user_schema(host_default: str | None = None) -> vol.Schema:
    host_key = vol.Required(CONF_HOST, default=host_default) if host_default else vol.Required(CONF_HOST)
    return vol.Schema(
        {
            host_key: str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
            vol.Required(CONF_USERNAME, default=DEFAULT_USERNAME): str,
            vol.Required(CONF_PASSWORD, default=DEFAULT_PASSWORD): str,
            vol.Optional(CONF_SSL, default=DEFAULT_SSL): bool,
            vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
        }
    )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Returns a dict with a `title` key on success, raises CannotConnect or
    InvalidAuth otherwise.
    """
    session = async_get_clientsession(hass, verify_ssl=data.get(CONF_VERIFY_SSL, True))
    client = JukeApiClient(
        session,
        host=data[CONF_HOST],
        port=data[CONF_PORT],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        use_ssl=data.get(CONF_SSL, False),
        verify_ssl=data.get(CONF_VERIFY_SSL, True),
    )

    try:
        await client.ping()
    except JukeConnectionError as err:
        raise CannotConnect from err
    except JukeApiError as err:
        # ping is unauthenticated, so any other API failure here still
        # indicates the device isn't reachable/well-formed.
        raise CannotConnect from err

    try:
        zones = await client.get_zones_info()
    except JukeAuthError as err:
        raise InvalidAuth from err
    except JukeConnectionError as err:
        raise CannotConnect from err
    except JukeApiError as err:
        raise CannotConnect from err

    return {"title": f"Juke ({data[CONF_HOST]})", "zone_count": len(zones)}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Juke Audio."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_host: str | None = None

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Handle discovery via DHCP.

        Juke boxes run an embedded Linux/Shairport Sync stack that advertises
        itself over mDNS as `<hostname>.local` (observed as `jukeaudio.local`
        via its AirPlay/_raop._tcp record) - the same hostname string is what
        the device sends in its DHCP request, which is what manifest.json's
        `dhcp` matcher (`hostname: "jukeaudio*"`) keys off. `_raop._tcp.` itself
        is too generic (shared by every Shairport-based AirPlay receiver) to
        use as a zeroconf matcher, so hostname-based DHCP discovery is used
        instead.
        """
        host = discovery_info.ip

        # A device already configured by IP shouldn't get a second discovery
        # prompt just because DHCP saw it too.
        for entry in self._async_current_entries(include_ignore=False):
            if entry.data.get(CONF_HOST) == host:
                return self.async_abort(reason="already_configured")

        macaddress = discovery_info.macaddress
        if macaddress:
            await self.async_set_unique_id(macaddress)
            self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self._discovered_host = host
        self.context["title_placeholders"] = {"host": host}
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            if self.unique_id is None:
                # Not discovered via DHCP (which already claimed a mac-based
                # unique_id) - dedupe manual entries on host:port instead.
                unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

            try:
                info = await _validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception during Juke config flow")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(self._discovered_host),
            errors=errors,
            description_placeholders={
                "discovered_note": (
                    f"Auto-discovered a Juke device at {self._discovered_host} — "
                    "just confirm the credentials below."
                )
                if self._discovered_host
                else ""
            },
        )
