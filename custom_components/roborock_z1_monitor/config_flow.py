"""Reuse an existing account without duplicating any credentials."""

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow
from .protocol import DOMAIN, SOURCE_ENTRY


class Z1ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        accounts = {e.entry_id: e.title for e in self.hass.config_entries.async_entries("roborock")}
        if not accounts:
            return self.async_abort(reason="no_source")
        if user_input is not None:
            selected = user_input.get(SOURCE_ENTRY)
            if selected in accounts:
                await self.async_set_unique_id(selected)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="石头 Z1 Max", data={SOURCE_ENTRY: selected})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({vol.Required(SOURCE_ENTRY): vol.In(accounts)}))
