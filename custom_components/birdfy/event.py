"""Event entity: one event per bird visit."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import EVENT_TYPE_VISIT
from .coordinator import BirdfyConfigEntry
from .entity import BirdfyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BirdfyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(BirdfyVisitEvent(coordinator, serial) for serial in coordinator.states)


class BirdfyVisitEvent(BirdfyEntity, EventEntity):
    """Fires when a new visit shows up in the Birdfy cloud."""

    _attr_event_types = [EVENT_TYPE_VISIT]

    def __init__(self, coordinator, serial: str) -> None:
        super().__init__(coordinator, serial, "visit")

    @callback
    def _handle_coordinator_update(self) -> None:
        for event in self.state_data.new_events:
            self._trigger_event(
                EVENT_TYPE_VISIT,
                {
                    "species": event.label,
                    "visit_time": dt_util.utc_from_timestamp(event.timestamp).isoformat(),
                    "event_id": event.alarm_id,
                },
            )
        super()._handle_coordinator_update()
