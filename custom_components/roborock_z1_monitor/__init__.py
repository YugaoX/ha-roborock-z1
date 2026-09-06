"""Independent Z1 Max monitoring. Does not modify built-in Roborock."""

import asyncio
import logging
import time
from datetime import timedelta

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.storage import Store
from homeassistant.components import persistent_notification
from homeassistant.util import dt as dt_util

from .client import ReadOnlyClient
from .protocol import DOMAIN, SOURCE_ENTRY, FIELDS
from .cycle import advance, completion_text

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SWITCH]


class Z1Coordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry,
                         update_interval=timedelta(seconds=60), always_update=False)
        self.client = client
        self.failures = {}
        self.next_query = {}
        self.store = Store(hass, 1, DOMAIN + ".cycles." + entry.entry_id)
        self.cycles = {}
        self.preferences = {}
        self.push_cache = {}
        self.cycle_lock = asyncio.Lock()
        self.entry = entry

    def receive_push(self, device_id, values):
        self.entry.async_create_background_task(self.hass,
            self.process_push(device_id, values, time.time()), "z1_state_push")

    async def process_push(self, device_id, values, now):
        async with self.cycle_lock:
            cache = self.push_cache.setdefault(device_id, {})
            cache.update({key: (value, now) for key,value in values.items()})
            if any(k not in cache or now-cache[k][1] > 180 for k in FIELDS):
                return
            merged = {k: cache[k][0] for k in FIELDS}
            self.cycles[device_id], event_id = advance(self.cycles.get(device_id), merged, now)
            await self.save()
            if event_id and self.preferences.get(device_id, True):
                self.notify(device_id, event_id)

    async def restore(self):
        saved = await self.store.async_load() or {}
        self.cycles = saved.get("cycles", {})
        self.preferences = saved.get("preferences", {})

    async def save(self):
        await self.store.async_save({"cycles": self.cycles, "preferences": self.preferences})

    async def set_notifications(self, device_id, enabled):
        self.preferences[device_id] = enabled
        await self.save()

    def notify(self, device_id, event_id="test", test=False):
        info = self.client.devices[device_id]
        title, message = completion_text(info["model"], info["name"], test)
        persistent_notification.async_create(self.hass, message, title,
            notification_id=f"{DOMAIN}_{device_id}_{event_id}")

    async def _async_update_data(self):
        result = dict(self.data or {})
        for device_id, info in self.client.devices.items():
            if time.monotonic() < self.next_query.get(device_id, 0):
                continue
            try:
                values = await self.client.query(device_id)
            except Exception as ex:
                # Failure remains visible as unavailable; never expose stale values as live.
                if not self.failures.get(device_id):
                    _LOGGER.warning("%s state query failed (%s); marking unavailable", info["model"], type(ex).__name__)
                self.failures[device_id] = self.failures.get(device_id, 0) + 1
                self.next_query[device_id] = time.monotonic() + min(300, 60 * self.failures[device_id])
                result[device_id] = {"available": False, "error": type(ex).__name__}
                async with self.cycle_lock:
                    self.push_cache.pop(device_id, None)
                    self.cycles[device_id], _ = advance(self.cycles.get(device_id), None, time.time())
                    await self.save()
            else:
                if self.failures.get(device_id):
                    _LOGGER.info("%s state query recovered", info["model"])
                self.failures[device_id] = 0
                self.next_query[device_id] = 0
                result[device_id] = {"available": True, "values": values,
                                     "sampled_at": dt_util.utcnow().isoformat()}
                # Query replies already feed the subscribed DPS handler. Reprocessing
                # a merged query here can overwrite a newer short-lived push event.
        return result


async def async_setup_entry(hass, entry):
    source = hass.config_entries.async_get_entry(entry.data[SOURCE_ENTRY])
    if source is None or source.domain != "roborock":
        raise ConfigEntryNotReady("Restore the source Roborock account entry")
    client = ReadOnlyClient(source.data, async_get_clientsession(hass))
    try:
        await client.setup()
        coordinator = Z1Coordinator(hass, entry, client)
        await coordinator.restore()
        client.push_callback = coordinator.receive_push
        await coordinator.async_config_entry_first_refresh()
    except Exception as ex:
        await client.close()
        raise ConfigEntryNotReady(f"Z1 monitor setup failed ({type(ex).__name__})") from None
    entry.runtime_data = coordinator
    if entry.title == "石头 Z1 Max 只读监测":
        hass.config_entries.async_update_entry(entry, title="石头 Z1 Max")
    async def close_on_stop(event):
        await client.close()
    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, close_on_stop))
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        await client.close()
        raise
    return True


async def async_unload_entry(hass, entry):
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.client.close()
    return unloaded
