"""Offline checks using the real pinned SDK, with in-memory MQTT transport."""
import asyncio
import importlib.util
import json
from importlib.metadata import version
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from roborock.protocols.a01_protocol import decode_rpc_response, encode_mqtt_payload
from roborock.web_api import PreparedRequest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/roborock_z1_monitor"
package = types.ModuleType("z1_sdk_test")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p = load("z1_sdk_test.protocol", "protocol.py")
c = load("z1_sdk_test.client", "client.py")


class MemoryChannel:
    """Respond to query packets only; no connection to MQTT or an appliance."""
    def __init__(self):
        self.callbacks = []
        self.sent = []
        self.health_manager = types.SimpleNamespace(on_success=AsyncMock(), on_timeout=AsyncMock())

    async def subscribe(self, callback):
        self.callbacks.append(callback)
        return lambda: self.callbacks.remove(callback)

    async def publish(self, message, **kwargs):
        values = decode_rpc_response(message)
        self.sent.append(values)
        if 10000 in values:
            # The query's list is serialized as JSON by the integration's encoder.
            requested = json.loads(values[10000])
            sample = {203: 1, 218: 18, 220: 0, 204: 4, 205: 9, 209: 1}
            reply = encode_mqtt_payload({key: sample[key] for key in requested})
            for callback in tuple(self.callbacks):
                callback(reply)


class SDKTests(unittest.IsolatedAsyncioTestCase):
    def client(self):
        data = {"username": "test@example.invalid", "base_url": "https://example.invalid",
                "user_data": {"token": "fake", "rriot": {"u": "fake-user", "s": "fake-s",
                              "h": "fake-h", "k": "fake-k", "r": {"a": "https://example.invalid",
                              "m": "ssl://example.invalid:8883"}}}}
        return c.ReadOnlyClient(data, Mock())

    async def test_real_sdk_account_parsing_and_discovery(self):
        self.assertEqual(version("python-roborock"), "7.4.2")
        client = self.client()
        schema = [{"id": k, "code": code, "mode": "ro", "type": "VALUE"}
                  for k, code in p.FIELDS.items()] + [{"id": 10000, "code": "id_query"}]
        home = {"products": [{"id": "test-product", "model": "roborock.cd.a204", "schema": schema}],
                "devices": [{"duid": "test-device", "name": "test", "localKey": "0" * 16,
                             "productId": "test-product", "pv": "A01"}]}
        session = types.SimpleNamespace(close=AsyncMock())
        channel = MemoryChannel()
        # Keep actual UserData, HomeDataDevice, PreparedRequest and SDK imports.
        with patch.object(client.api, "_get_home_id", AsyncMock(return_value=1)), \
             patch.object(PreparedRequest, "request", AsyncMock(return_value={"success": True, "result": home})) as request, \
             patch.object(c, "create_lazy_mqtt_session", AsyncMock(return_value=session)), \
             patch.object(c, "create_mqtt_channel", Mock(return_value=channel)):
            await client.setup()
        self.assertEqual(client.devices["test-device"]["model"], "roborock.cd.a204")
        self.assertFalse(client.devices["test-device"]["supports_start"])
        request.assert_awaited_once_with("get", "/v3/user/homes/1")
        await client.close()
        session.close.assert_awaited_once()
        self.assertEqual(channel.callbacks, [])

    async def test_real_query_codec_and_guarded_start_packet(self):
        client = self.client()
        channel = MemoryChannel()
        client.devices = {"test": {"supports_start": True}}
        client.channels = {"test": channel}
        client.locks = {"test": asyncio.Lock()}
        self.assertEqual(await client.query("test"), {203: 1, 218: 18, 220: 0})
        self.assertEqual(json.loads(channel.sent[0][10000]), [203, 218, 220])
        await client.start_current_program("test")
        self.assertEqual(channel.sent[-1], {204: 4, 205: 9, 209: 1, 200: 1})
        count = len(channel.sent)
        with self.assertRaises(ValueError):
            await client.start_current_program("test")
        self.assertEqual(len(channel.sent), count)


if __name__ == "__main__":
    unittest.main()
