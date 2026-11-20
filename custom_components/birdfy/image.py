"""Image entity: snapshot of the latest visit."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import BirdfyConfigEntry
from .entity import BirdfyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BirdfyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(BirdfyLastVisitImage(hass, coordinator, serial) for serial in coordinator.states)


class BirdfyLastVisitImage(BirdfyEntity, ImageEntity):
    """The snapshot is downloaded once per visit and served from memory."""

    _attr_content_type = "image/jpeg"

    def __init__(self, hass: HomeAssistant, coordinator, serial: str) -> None:
        BirdfyEntity.__init__(self, coordinator, serial, "last_visit_image")
        ImageEntity.__init__(self, hass)
        self._shown_event_id: str | None = None
        self._update_from_state()

    def _update_from_state(self) -> None:
        state = self.state_data
        if state.image and state.image_event_id != self._shown_event_id:
            self._shown_event_id = state.image_event_id
            event = state.last_event
            ts = event.timestamp if event and event.alarm_id == state.image_event_id else None
            self._attr_image_last_updated = (
                dt_util.utc_from_timestamp(ts) if ts else dt_util.utcnow()
            )

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_from_state()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        return self.state_data.image

    @property
    def image_last_updated(self) -> datetime | None:
        return self._attr_image_last_updated
