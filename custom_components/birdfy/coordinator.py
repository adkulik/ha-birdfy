"""Polling coordinator for Birdfy bird visits."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import BirdfyApi, BirdfyAuthError, BirdfyDevice, BirdfyError, BirdfyEvent
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEVICE_REFRESH_INTERVAL,
    DOMAIN,
    EVENT_FETCH_LIMIT,
)

_LOGGER = logging.getLogger(__name__)

type BirdfyConfigEntry = ConfigEntry[BirdfyCoordinator]


@dataclass
class BirdfyDeviceState:
    """What the integration knows about one camera."""

    device: BirdfyDevice
    last_visit: BirdfyEvent | None = None
    new_visits: list[BirdfyEvent] = field(default_factory=list)
    recent_events: list[BirdfyEvent] = field(default_factory=list)
    today: date | None = None
    today_visits: dict[str, BirdfyEvent] = field(default_factory=dict)
    today_motion_ids: set[str] = field(default_factory=set)
    seen_ids: set[str] = field(default_factory=set)
    initialized: bool = False
    photo: bytes | None = None
    photo_event: BirdfyEvent | None = None
    photo_attempts: dict[str, int] = field(default_factory=dict)

    @property
    def visits_today(self) -> int:
        return len(self.today_visits)

    @property
    def motion_events_today(self) -> int:
        return len(self.today_motion_ids)

    @property
    def species_today(self) -> dict[str, int]:
        """Visits per species today (by each visit's main species)."""
        counts: dict[str, int] = {}
        for visit in self.today_visits.values():
            name = visit.primary_species or "unknown"
            counts[name] = counts.get(name, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def _local_date(ts: float) -> date:
    return dt_util.as_local(dt_util.utc_from_timestamp(ts)).date()


class BirdfyCoordinator(DataUpdateCoordinator[dict[str, BirdfyDeviceState]]):
    """Fetches recent events for every camera on the account."""

    config_entry: BirdfyConfigEntry

    def __init__(self, hass: HomeAssistant, entry: BirdfyConfigEntry, api: BirdfyApi) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.api = api
        self.states: dict[str, BirdfyDeviceState] = {}
        self._devices_fetched_at = None

    async def _async_refresh_devices(self) -> None:
        now = dt_util.utcnow()
        if self._devices_fetched_at and now - self._devices_fetched_at < DEVICE_REFRESH_INTERVAL:
            return
        devices = await self.api.async_get_devices()
        self._devices_fetched_at = now
        for device in devices:
            if device.serial in self.states:
                self.states[device.serial].device = device
            else:
                self.states[device.serial] = BirdfyDeviceState(device=device)
        if not devices:
            _LOGGER.warning("No Birdfy camera found on this account")

    async def _async_update_data(self) -> dict[str, BirdfyDeviceState]:
        try:
            await self._async_refresh_devices()
            for state in self.states.values():
                await self._async_update_device(state)
        except BirdfyAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except BirdfyError as err:
            raise UpdateFailed(str(err)) from err
        return self.states

    async def _async_update_device(self, state: BirdfyDeviceState) -> None:
        events = await self.api.async_get_events(state.device.serial, EVENT_FETCH_LIMIT)
        state.recent_events = events
        visits = [e for e in events if e.is_bird]

        today = dt_util.now().date()
        if state.today != today:
            state.today = today
            state.today_visits = {}
            state.today_motion_ids = set()
        for event in events:
            if _local_date(event.timestamp) == today:
                state.today_motion_ids.add(event.alarm_id)
                if event.is_bird:
                    state.today_visits[event.alarm_id] = event

        if state.initialized:
            # Oldest first, so automations see visits in the order they happened.
            state.new_visits = [
                e for e in reversed(visits) if e.alarm_id not in state.seen_ids
            ]
        else:
            state.new_visits = []
        state.seen_ids.update(e.alarm_id for e in events)
        if len(state.seen_ids) > 5000:
            state.seen_ids = {e.alarm_id for e in events}
        state.initialized = True

        if visits:
            state.last_visit = visits[0]
            await self._async_update_photo(state, visits[0])

        if state.new_visits:
            _LOGGER.debug(
                "%s: %d new visit(s), latest %s",
                state.device.name,
                len(state.new_visits),
                state.new_visits[-1].species,
            )

    async def _async_update_photo(self, state: BirdfyDeviceState, visit: BirdfyEvent) -> None:
        """Download the photo of the latest visit once (a few tries at most)."""
        if state.photo_event and state.photo_event.alarm_id == visit.alarm_id:
            return
        tries = state.photo_attempts.get(visit.alarm_id, 0)
        if tries >= 3:
            return
        state.photo_attempts = {visit.alarm_id: tries + 1}
        try:
            photo = await self.api.async_get_event_picture(state.device.serial, visit)
        except BirdfyAuthError:
            raise
        except BirdfyError as err:
            _LOGGER.debug("Could not fetch the visit photo: %s", err)
            return
        if photo:
            state.photo = photo
            state.photo_event = visit
