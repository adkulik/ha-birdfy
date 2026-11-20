"""Diagnostics: shows the raw event fields (secrets removed) to help adapt to new models."""

from __future__ import annotations

import json
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL
from homeassistant.core import HomeAssistant

from .const import CONF_PASSWORD_HASH, CONF_UDID
from .coordinator import BirdfyConfigEntry

TO_REDACT = {CONF_EMAIL, CONF_PASSWORD_HASH, CONF_UDID}

# Any key containing one of these fragments is redacted (case-insensitive).
SENSITIVE_FRAGMENTS = (
    "email", "owner", "nickname", "mac", "serial", "sn", "user", "token",
    "url", "pic", "endpoint", "ssid", "wifi", "deviceid", "groupid", "phone",
)


def _redact(value: Any) -> Any:
    """Recursively redact anything that could identify the account or device."""
    if isinstance(value, dict):
        out = {}
        for key, val in value.items():
            k = str(key).lower()
            if k in ("ip", "ipaddress", "localip") or any(
                frag in k for frag in SENSITIVE_FRAGMENTS
            ):
                out[key] = "**REDACTED**"
            else:
                out[key] = _redact(val)
        return out
    if isinstance(value, list):
        return [_redact(v) for v in value]
    if isinstance(value, str) and ("http" in value or "@" in value or "/" in value):
        return "**REDACTED**"
    return value


def _event_summary(raw: dict[str, Any]) -> dict[str, Any]:
    data = dict(raw)
    desc = data.get("description")
    if isinstance(desc, str):
        try:
            data["description"] = json.loads(desc)
        except ValueError:
            data["description"] = "<not json>"
    return _redact(data)



async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BirdfyConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    devices = []
    for state in coordinator.states.values():
        last = state.last_visit
        status_counts: dict[str, int] = {}
        for e in state.recent_events:
            key = f"type={e.raw.get('type')} ai={e.raw.get('aiRecognitionStatus')}"
            status_counts[key] = status_counts.get(key, 0) + 1
        devices.append(
            {
                "device": _redact(state.device.raw),
                "visits_today": state.visits_today,
                "motion_events_today": state.motion_events_today,
                "has_photo": state.photo is not None,
                "species_today": state.species_today,
                "last_visit_species": last.species if last else None,
                "recent_status_counts": status_counts,
                "recent_events": [_event_summary(e.raw) for e in state.recent_events],
            }
        )
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options),
        "devices": devices,
    }
