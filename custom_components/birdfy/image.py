"""Image entity: photo of the latest bird visit."""

from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import BirdfyConfigEntry
from .entity import BirdfyEntity
from .event import visit_attributes


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BirdfyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        BirdfyLastVisitPhoto(hass, coordinator, serial) for serial in coordinator.states
    )


class BirdfyLastVisitPhoto(BirdfyEntity, ImageEntity):
    """The photo is downloaded once per visit and served from memory."""

    _attr_content_type = "image/jpeg"

    def __init__(self, hass: HomeAssistant, coordinator, serial: str) -> None:
        BirdfyEntity.__init__(self, coordinator, serial, "last_visit_photo")
        ImageEntity.__init__(self, hass)
        self._shown: str | None = None
        self._sync()

    def _sync(self) -> None:
        event = self.state_data.photo_event
        if event is None or event.alarm_id == self._shown:
            return
        self._shown = event.alarm_id
        self._attr_image_last_updated = dt_util.utc_from_timestamp(event.timestamp)
        self._attr_extra_state_attributes = visit_attributes(event, self.coordinator.language)

    @callback
    def _handle_coordinator_update(self) -> None:
        self._sync()
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        return self.state_data.photo
