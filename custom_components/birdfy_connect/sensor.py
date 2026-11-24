"""Sensors: last visitor, last visit time, visits today, motion events today."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import BirdfyConfigEntry, BirdfyDeviceState
from .entity import BirdfyEntity
from .event import visit_attributes
from .species import translate


@dataclass(frozen=True, kw_only=True)
class BirdfySensorDescription(SensorEntityDescription):
    value_fn: Callable[[BirdfyDeviceState, str], Any]
    attrs_fn: Callable[[BirdfyDeviceState, str], dict[str, Any] | None] = lambda s, lang: None
    daily: bool = False


def _last_time(state: BirdfyDeviceState) -> datetime | None:
    if state.last_visit is None or not state.last_visit.timestamp:
        return None
    return dt_util.utc_from_timestamp(state.last_visit.timestamp)


SENSORS: tuple[BirdfySensorDescription, ...] = (
    BirdfySensorDescription(
        key="last_visitor",
        value_fn=lambda s, lang: (
            (translate(s.last_visit.primary_species, lang) or "unknown") if s.last_visit else None
        ),
        attrs_fn=lambda s, lang: visit_attributes(s.last_visit, lang) if s.last_visit else None,
    ),
    BirdfySensorDescription(
        key="last_visit",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda s, lang: _last_time(s),
    ),
    BirdfySensorDescription(
        key="visits_today",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda s, lang: s.visits_today,
        attrs_fn=lambda s, lang: {"species": s.species_today(lang)},
        daily=True,
    ),
    BirdfySensorDescription(
        key="motion_events_today",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda s, lang: s.motion_events_today,
        entity_registry_enabled_default=False,
        daily=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BirdfyConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        BirdfySensor(coordinator, serial, description)
        for serial in coordinator.states
        for description in SENSORS
    )


class BirdfySensor(BirdfyEntity, SensorEntity):
    entity_description: BirdfySensorDescription

    def __init__(self, coordinator, serial: str, description: BirdfySensorDescription) -> None:
        super().__init__(coordinator, serial, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.state_data, self.coordinator.language)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self.entity_description.attrs_fn(self.state_data, self.coordinator.language)

    @property
    def last_reset(self) -> datetime | None:
        if not self.entity_description.daily:
            return None
        return dt_util.start_of_local_day()
