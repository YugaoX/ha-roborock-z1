from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .protocol import DOMAIN


class Z1Entity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, device_id, key):
        super().__init__(coordinator)
        self.device_id = device_id
        self._attr_unique_id = f"{device_id}_{key}"
        device = coordinator.client.devices[device_id]
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, device_id)},
            name=device["name"], manufacturer="Roborock", model=device["model"], sw_version=device["firmware"])

    @property
    def sample(self):
        return (self.coordinator.data or {}).get(self.device_id, {})
