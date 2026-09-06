"""Raw readouts until their semantics are verified against the actual appliance."""

from homeassistant.components.sensor import SensorEntity
from .entity import Z1Entity

FIELDS = {203: ("状态", "mdi:state-machine"),
          218: ("程序时间", "mdi:timer-outline"),
          220: ("故障码", "mdi:alert-circle-outline")}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    async_add_entities(Z1Sensor(coordinator, device_id, field)
        for device_id in coordinator.client.devices for field in FIELDS)


class Z1Sensor(Z1Entity, SensorEntity):
    def __init__(self, coordinator, device_id, field):
        super().__init__(coordinator, device_id, str(field))
        self.field = field
        self.model = coordinator.client.devices[device_id]["model"]
        self._attr_name, self._attr_icon = FIELDS[field]
        if field == 218:
            if self.model == "roborock.cd.a188":
                self._attr_native_unit_of_measurement = "min"
            else:
                self._attr_name = "程序时间原始值"

    @property
    def available(self):
        return super().available and self.sample.get("available", False)

    @property
    def native_value(self):
        value = self.sample.get("values", {}).get(self.field)
        if self.field == 203 and value is not None:
            observed = {"roborock.wm.a180": {1:"待机/关机",4:"洗涤中",6:"脱水中",10:"程序完成"},
                        "roborock.cd.a188": {1:"待机/关机",7:"烘干/护理中",8:"冷却中",10:"程序完成"}}
            return observed.get(self.model, {}).get(value, f"状态码 {value}")
        return value

    @property
    def extra_state_attributes(self):
        return {"data_point": self.field, "sampled_at": self.sample.get("sampled_at"),
                "raw_value": self.sample.get("values", {}).get(self.field),
                "time_note": ("待机时为所选程序预计时长，不表示正在运行"
                              if self.model == "roborock.cd.a188" else "字段单位和含义尚未核实，显示原始值")
                             if self.field == 218 else None}
