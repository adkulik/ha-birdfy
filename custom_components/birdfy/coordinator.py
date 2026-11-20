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
    last_event: BirdfyEvent | None = None
    new_events: list[BirdfyEvent] = field(default_factory=list)
    today: date | None = None
    today_ids: set[str] = field(default_factory=set)
    image: bytes | None = None
    image_event_id: str | None = None
    seen_ids: set[str] = field(default_factory=set)
    recent_events: list[BirdfyEvent] = field(default_factory=list)
    initialized: bool = False

    @property
    def visits_today(self) -> int:
        return len(self.today_ids)


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

        if events and not state.initialized:
            # Log the shape of one event once, to help adapt to other models.
            _LOGGER.debug(
                "First Birdfy event for %s has fields: %s (label=%r)",
                state.device.name,
                sorted(events[0].raw.keys()),
                events[0].label,
            )

        today = dt_util.now().date()
        if state.today != today:
            state.today = today
            state.today_ids = set()
        state.today_ids.update(e.alarm_id for e in events if _local_date(e.timestamp) == today)

        if state.initialized:
            # Oldest first, so automations see visits in the order they happened.
            state.new_events = [e for e in reversed(events) if e.alarm_id not in state.seen_ids]
        else:
            state.new_events = []
        state.seen_ids.update(e.alarm_id for e in events)
        # Keep the set bounded.
        if len(state.seen_ids) > 2000:
            state.seen_ids = {e.alarm_id for e in events}
        state.initialized = True

        if events:
            state.last_event = events[0]
            if state.image_event_id != events[0].alarm_id:
                try:
                    image = await self.api.async_get_event_picture(
                        state.device.serial, events[0].alarm_id
                    )
                except BirdfyError as err:
                    _LOGGER.debug("Could not fetch snapshot: %s", err)
                    image = None
                if image:
                    state.image = image
                    state.image_event_id = events[0].alarm_id

        if state.new_events:
            _LOGGER.debug(
                "%s: %d new visit(s), latest %r",
                state.device.name,
                len(state.new_events),
                state.new_events[-1].label,
            )
