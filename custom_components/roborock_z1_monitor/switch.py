"""Per-appliance persisted notification preference."""
from homeassistant.components.switch import SwitchEntity
from .entity import Z1Entity
from .cycle import VERIFIED_COMPLETION_MODELS


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(Z1Notifications(coordinator, device_id, "completion_notification")
                       for device_id in coordinator.client.devices)


class Z1Notifications(Z1Entity, SwitchEntity):
    _attr_name = "程序结束提醒"
    _attr_icon = "mdi:bell-outline"

    @property
    def is_on(self):
        verified = self.coordinator.client.devices[self.device_id]["model"] in VERIFIED_COMPLETION_MODELS
        return self.coordinator.preferences.get(self.device_id, verified)

    async def async_turn_on(self, **kwargs):
        await self.coordinator.set_notifications(self.device_id, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        await self.coordinator.set_notifications(self.device_id, False)
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        verified = self.coordinator.client.devices[self.device_id]["model"] in VERIFIED_COMPLETION_MODELS
        return {"channel": "Home Assistant 内通知", "rule": "实时推送：已观察运行后收到完成信号，且无故障",
                "verification": ("此型号自然结束信号已实测；以实际运行记录和防重复条件判定"
                                 if verified else "此型号自然结束信号尚未实测；默认关闭，验证后可手动启用")}
