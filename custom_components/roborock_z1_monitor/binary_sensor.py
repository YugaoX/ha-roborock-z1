from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from .entity import Z1Entity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(Z1Connection(coordinator, device_id, "connection")
                       for device_id in coordinator.client.devices)


class Z1Connection(Z1Entity, BinarySensorEntity):
    _attr_name = "状态通信"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def is_on(self):
        return self.sample.get("available", False)
