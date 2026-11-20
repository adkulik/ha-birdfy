"""Diagnostics: shows the raw event fields (secrets removed) to help adapt to new models."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD_HASH, CONF_UDID
from .coordinator import BirdfyConfigEntry

TO_REDACT = {
    CONF_EMAIL,
    CONF_PASSWORD_HASH,
    CONF_UDID,
    "serialNumber",
    "deviceSn",
    "sn",
    "addxSn",
    "serial",
    "mac",
    "macAddress",
    "ip",
    "wifiName",
    "ssid",
    "userId",
    "userID",
    "ownerId",
    "token",
    "url",
    "recordUrl",
    "picUrl",
    "imageUrl",
    "thumbnail",
    "description",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BirdfyConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    devices = []
    for state in coordinator.states.values():
        last = state.last_event
        devices.append(
            {
                "device": async_redact_data(state.device.raw, TO_REDACT),
                "visits_today": state.visits_today,
                "has_image": state.image is not None,
                "last_event_label": last.label if last else None,
                "last_event_raw": async_redact_data(last.raw, TO_REDACT) if last else None,
            }
        )
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "devices": devices,
    }
