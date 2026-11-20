"""The Birdfy integration: bird visit events from Birdfy feeder cameras."""

from __future__ import annotations

from homeassistant.const import CONF_EMAIL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BirdfyApi
from .const import CONF_PASSWORD_HASH, CONF_UDID
from .coordinator import BirdfyConfigEntry, BirdfyCoordinator

PLATFORMS: list[Platform] = [Platform.EVENT, Platform.IMAGE, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: BirdfyConfigEntry) -> bool:
    """Set up Birdfy from a config entry."""
    api = BirdfyApi(
        async_get_clientsession(hass),
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD_HASH],
        entry.data[CONF_UDID],
    )
    coordinator = BirdfyCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: BirdfyConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: BirdfyConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
