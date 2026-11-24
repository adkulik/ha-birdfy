"""Base entity for Birdfy."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BirdfyCoordinator, BirdfyDeviceState


class BirdfyEntity(CoordinatorEntity[BirdfyCoordinator]):
    """An entity that belongs to one Birdfy camera."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BirdfyCoordinator, serial: str, key: str) -> None:
        super().__init__(coordinator)
        self._serial = serial
        self._attr_unique_id = f"{serial}_{key}"
        self._attr_translation_key = key
        device = self.state_data.device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=device.name,
            manufacturer="Birdfy (Netvue)",
            model=device.model,
            sw_version=device.firmware,
            serial_number=serial,
        )

    @property
    def state_data(self) -> BirdfyDeviceState:
        return self.coordinator.states[self._serial]

    @property
    def available(self) -> bool:
        return super().available and self._serial in self.coordinator.states
