"""Explicit user start and harmless notification-channel test."""
from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from .entity import Z1Entity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(Z1Button(coordinator, device_id, action)
                       for device_id in coordinator.client.devices for action in ("start", "test_notification"))


class Z1Button(Z1Entity, ButtonEntity):
    def __init__(self, coordinator, device_id, action):
        super().__init__(coordinator, device_id, action)
        self.action = action
        self._attr_name = "启动当前程序" if action == "start" else "测试完成提醒"
        self._attr_icon = "mdi:play-circle-outline" if action == "start" else "mdi:bell-check-outline"

    @property
    def available(self):
        return self.action != "start" or (self.sample.get("available", False)
            and self.coordinator.client.devices[self.device_id]["supports_start"])

    async def async_press(self):
        if self.action == "test_notification":
            self.coordinator.notify(self.device_id, test=True)
            return
        try:
            await self.coordinator.client.start_current_program(self.device_id)
        except ValueError as ex:
            raise HomeAssistantError(str(ex)) from None
        except Exception:
            raise HomeAssistantError("启动应答未确认，设备可能已经收到命令。请先查看石头 App，不要立即重复启动。") from None
        finally:
            await self.coordinator.async_request_refresh()
