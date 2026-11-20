"""Sensors: last visitor, last visit time, visits today."""

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


@dataclass(frozen=True, kw_only=True)
class BirdfySensorDescription(SensorEntityDescription):
    value_fn: Callable[[BirdfyDeviceState], Any]


def _last_time(state: BirdfyDeviceState) -> datetime | None:
    if state.last_event is None or not state.last_event.timestamp:
        return None
    return dt_util.utc_from_timestamp(state.last_event.timestamp)


SENSORS: tuple[BirdfySensorDescription, ...] = (
    BirdfySensorDescription(
        key="last_visitor",
        value_fn=lambda s: (s.last_event.label or "unknown") if s.last_event else None,
    ),
    BirdfySensorDescription(
        key="last_visit",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_time,
    ),
    BirdfySensorDescription(
        key="visits_today",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda s: s.visits_today,
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
        return self.entity_description.value_fn(self.state_data)

    @property
    def last_reset(self) -> datetime | None:
        if self.entity_description.key != "visits_today":
            return None
        return dt_util.start_of_local_day()
