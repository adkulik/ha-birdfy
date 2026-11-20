"""Constants for the Birdfy integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "birdfy"

CONF_PASSWORD_HASH: Final = "password_hash"
CONF_UDID: Final = "udid"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_SPECIES_LANGUAGE: Final = "species_language"
SPECIES_LANGUAGES: Final = ["auto", "hu", "en"]

DEFAULT_SCAN_INTERVAL: Final = 60  # seconds
MIN_SCAN_INTERVAL: Final = 30
MAX_SCAN_INTERVAL: Final = 900

# How many recent events are requested on each poll.
EVENT_FETCH_LIMIT: Final = 100

EVENT_TYPE_VISIT: Final = "bird_visit"

DEVICE_REFRESH_INTERVAL: Final = timedelta(hours=6)
