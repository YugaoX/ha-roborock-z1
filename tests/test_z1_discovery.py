"""Exercise the actual discovery loop against synthetic cloud data, without SDK/network."""
import ast
import asyncio
import copy
import importlib.util
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1] / "custom_components/roborock_z1_monitor"
spec = importlib.util.spec_from_file_location("discovery_protocol", ROOT / "protocol.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
tree = ast.parse((ROOT / "client.py").read_text(encoding="utf-8"))
tree.body = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ReadOnlyClient"]
logger = logging.getLogger("z1_discovery_tests")
ns = {"asyncio": asyncio, "_LOGGER": logger, "version": Mock(return_value="7.4.2"),
      "MODELS": p.MODELS, "FIELDS": p.FIELDS, "START_FIELDS": p.START_FIELDS,
      "validate_schema": p.validate_schema, "supports_start": p.supports_start}
exec(compile(tree, "client_discovery", "exec"), ns)


class DiscoveryTests(unittest.IsolatedAsyncioTestCase):
    def home(self, model="roborock.cd.a204", shared=False):
        schema = [{"id": k, "code": code, "mode": "ro", "type": "VALUE"}
                  for k, code in p.FIELDS.items()] + [{"id": 10000, "code": "id_query"}]
        device = {"productId": "product", "pv": "A01", "duid": "private-device"}
        return {"products": [{"id": "product", "model": model, "schema": schema}],
                "devices": [] if shared else [device],
                "receivedDevices": [device] if shared else []}

    async def discover(self, home, sdk="7.4.2"):
        client = object.__new__(ns["ReadOnlyClient"])
        client.user = SimpleNamespace(rriot=SimpleNamespace(r=SimpleNamespace(a="endpoint")))
        client.api = SimpleNamespace(_get_home_id=AsyncMock(return_value="private-home"))
        client.http_session = object()
        client.devices = {}; client.channels = {}; client.locks = {}; client.unsubscribers = []
        request = Mock(return_value=SimpleNamespace(request=AsyncMock(
            return_value={"success": True, "result": home})))
        channel = SimpleNamespace(subscribe=AsyncMock(return_value=Mock()))
        dependencies = {"version": Mock(return_value=sdk), "PreparedRequest": request,
                        "_get_hawk_authentication": Mock(return_value="private-token"),
                        "create_mqtt_params": Mock(), "create_lazy_mqtt_session": AsyncMock(),
                        "HomeDataDevice": SimpleNamespace(from_dict=lambda raw: SimpleNamespace(duid=raw["duid"])),
                        "create_mqtt_channel": Mock(return_value=channel)}
        self.client = client; self.request = request; self.channel = channel
        with patch.dict(ns, dependencies), self.assertLogs(logger, level="INFO") as captured:
            try:
                await client.setup()
            finally:
                self.messages = "\n".join(captured.output)
        return client

    async def test_owned_and_shared_a204_discovered_read_only(self):
        for shared in (False, True):
            with self.subTest(shared=shared):
                client = await self.discover(self.home(shared=shared))
                self.assertEqual(client.devices["private-device"]["model"], "roborock.cd.a204")
                self.assertFalse(client.devices["private-device"]["supports_start"])
                self.assertIn("a204=1", self.messages)
                for private in ("private-device", "private-home", "private-token"):
                    self.assertNotIn(private, self.messages)

    async def test_cloud_reported_cd_a204_and_a180_in_same_account(self):
        home = self.home()
        product = copy.deepcopy(home["products"][0])
        product.update(id="a180-product", model="roborock.wm.a180")
        home["products"].append(product)
        home["devices"].append({"productId": "a180-product", "pv": "A01", "duid": "other-device"})
        client = await self.discover(home)
        self.assertEqual(len(client.devices), 2)
        self.assertEqual({info["model"] for info in client.devices.values()},
                         {"roborock.cd.a204", "roborock.wm.a180"})
        self.assertIn("accepted=2 a204=1", self.messages)

    async def test_unknown_model_and_missing_product_have_visible_reason(self):
        # No compatible devices still raises, as in the original adapter.
        with self.assertRaisesRegex(ValueError, "No supported"):
            await self.discover(self.home("roborock.wm.other"))
        self.assertIn("not in allowlist", self.messages)
        home = self.home(); home["products"] = []
        with self.assertRaisesRegex(ValueError, "No supported"):
            await self.discover(home)
        self.assertIn("no matching product metadata", self.messages)

    async def test_a204_schema_and_protocol_still_rejected(self):
        home = self.home(); home["products"][0]["schema"][0]["mode"] = "rw"
        with self.assertRaisesRegex(ValueError, "Unexpected read-only schema"):
            await self.discover(home)
        self.channel.subscribe.assert_not_awaited()
        self.assertIn("schema mismatch", self.messages)
        home = self.home(); home["devices"][0]["pv"] = "B01"
        with self.assertRaisesRegex(ValueError, "Unexpected device protocol"):
            await self.discover(home)
        self.channel.subscribe.assert_not_awaited()
        self.assertIn("expected A01, got B01", self.messages)

    async def test_sdk_mismatch_stops_before_discovery(self):
        with self.assertRaisesRegex(ValueError, "requires review"):
            await self.discover(self.home(), sdk="4.8.0")
        self.client.api._get_home_id.assert_not_awaited()
        self.request.assert_not_called()
        self.assertIn("expected SDK 7.4.2, got 4.8.0", self.messages)


if __name__ == "__main__":
    unittest.main()
