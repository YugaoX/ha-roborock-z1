"""Control guard/transport and cycle edge cases without operating appliances."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1] / "custom_components/roborock_z1_monitor"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p = load("z1_control_protocol", "protocol.py")
cycle = load("z1_cycle", "cycle.py")


class ControlTests(unittest.TestCase):
    def test_start_schema_is_exact_model_scoped(self):
        for model in p.MODELS:
            product = {"model": model, "schema": [{"id": 200, "code": "start", "mode": "rw", "type": "BOOL"}]
                       + [{"id": k, "code": code, "mode": "rw", "type": "VALUE"} for k,code in p.START_FIELDS.items()]}
            self.assertTrue(p.supports_start(product))
            for key, val in (("id", 140), ("code", "lockdoor"), ("type", "VALUE"), ("mode", "ro")):
                changed = json.loads(json.dumps(product))
                changed["schema"][0][key] = val
                self.assertFalse(p.supports_start(changed))
        self.assertFalse(p.supports_start({"model": "unknown"}))

    def test_a204_control_schema_drift_preserves_read_only_support(self):
        readonly = [{"id": k, "code": code, "mode": "ro", "type": "VALUE"}
                    for k, code in p.FIELDS.items()] + [{"id": 10000, "code": "id_query"}]
        controls = [{"id": 200, "code": "start", "mode": "rw", "type": "BOOL"}]
        controls += [{"id": k, "code": code, "mode": "rw", "type": "VALUE"}
                     for k, code in p.START_FIELDS.items()]
        for index in range(len(controls)):
            for field, value in (("code", "unexpected"), ("mode", "ro"), ("type", "STRING"),
                                 ("id", -1)):
                with self.subTest(index=index, field=field):
                    changed = json.loads(json.dumps(controls))
                    changed[index][field] = value
                    product = {"model": "roborock.wm.a204", "schema": readonly + changed}
                    p.validate_schema(product)
                    self.assertFalse(p.supports_start(product))
            product = {"model": "roborock.wm.a204",
                       "schema": readonly + controls[:index] + controls[index + 1:]}
            p.validate_schema(product)
            self.assertFalse(p.supports_start(product))

    def test_start_only_fresh_fault_free_standby(self):
        self.assertEqual(p.start_payload({203: 1, 218: 10, 220: 0, 204:4,205:9,209:1}), {204:4,205:9,209:1,200:1})
        for values in ({203: 7, 218: 138, 220: 0}, {203: 1, 218: 138, 220: 3}, {}, {203: True, 218: 0, 220: 0}):
            with self.assertRaises(ValueError):
                p.start_payload(values)

    def test_missing_or_invalid_program_parameters_do_not_start(self):
        for extra in ({}, {204:4,205:9,209:True}, {204:4,205:0,209:1}):
            with self.assertRaises(ValueError):
                p.start_payload({203:1,218:10,220:0,**extra})


class CycleTests(unittest.TestCase):
    def feed(self, seq, initial=None):
        state, events = initial, []
        for now, code, error in seq:
            state, event = cycle.advance(state, None if code is None else {203: code, 218: 0, 220: error}, now)
            if event:
                events.append(event)
        return state, events

    def test_normal_completion_once_and_restore_deduplication(self):
        state, events = self.feed([(0, 4, 0), (60, 7, 0), (120, 10, 0), (180, 10, 0), (240, 10, 0)])
        self.assertEqual(len(events), 1)
        _, again = self.feed([(300, 10, 0), (360, 8, 0), (420, 10, 0)], json.loads(json.dumps(state)))
        self.assertEqual(again, [])

    def test_cancel_pause_fault_offline_unknown_and_stale_never_complete(self):
        for middle in (1, None, 99, 9):
            _, events = self.feed([(0, 4, 0), (60, 7, 0), (120, middle, 0), (180, 10, 0), (240, 10, 0)])
            self.assertEqual(events, [])
        for seq in ([(0, 10, 0), (60, 10, 0)], [(0, 4, 0), (60, 4, 0), (120, 4, 0)],
                    [(0, 4, 0), (60, 7, 0), (120, 10, 3), (180, 10, 0)],
                    [(0, 4, 0), (60, 7, 0), (400, 10, 0), (460, 10, 0)],
                    [(0, 4, 0), (60, 10, 0), (120, 10, 0)]):
            self.assertEqual(self.feed(seq)[1], [])

    def test_restart_during_run_and_new_cycle(self):
        state, _ = self.feed([(0, 4, 0), (60, 7, 0)])
        state, events = self.feed([(120, 10, 0), (180, 10, 0)], json.loads(json.dumps(state)))
        self.assertEqual(len(events), 1)
        _, events2 = self.feed([(240, 1, 0), (300, 4, 0), (360, 6, 0), (420, 10, 0), (480, 10, 0)], state)
        self.assertEqual(len(events2), 1)
        self.assertNotEqual(events, events2)

    def test_test_message_and_real_completion_are_distinct(self):
        self.assertIn("测试", cycle.completion_text("roborock.cd.a188", "dryer", True)[0])
        self.assertIn("程序完成", cycle.completion_text("roborock.cd.a188", "dryer")[0])

    def test_actual_washer_five_second_done_after_standby(self):
        state, events = self.feed([(0,6,0),(60,6,0),(120,6,0),(150,1,0),(150.055,10,0),(155,1,0)])
        self.assertEqual(len(events),1)

    def test_standby_without_done_or_late_done_never_notifies(self):
        self.assertEqual(self.feed([(0,6,0),(60,6,0),(120,1,0),(125,10,0)])[1],[])


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_payload_no_automatic_retry_after_uncertain_timeout(self):
        modules = {}
        for name in ("roborock", "roborock.data", "roborock.devices", "roborock.devices.rpc", "roborock.devices.rpc.a01_channel", "roborock.devices.transport", "roborock.devices.transport.mqtt_channel", "roborock.mqtt", "roborock.mqtt.roborock_session", "roborock.protocol", "roborock.protocols", "roborock.protocols.a01_protocol", "roborock.web_api", "z1_fake"):
            modules[name] = types.ModuleType(name)
        for name, attrs in {
            "roborock.data": ["HomeDataDevice", "UserData"],
            "roborock.devices.rpc.a01_channel": ["send_decoded_command"],
            "roborock.devices.transport.mqtt_channel": ["create_mqtt_channel"],
            "roborock.mqtt.roborock_session": ["create_lazy_mqtt_session"],
            "roborock.protocol": ["create_mqtt_params"],
            "roborock.protocols.a01_protocol": ["decode_rpc_response"],
            "roborock.web_api": ["PreparedRequest", "RoborockApiClient", "_get_hawk_authentication"],
        }.items():
            for attr in attrs:
                setattr(modules[name], attr, object)
        modules["z1_fake.protocol"] = p
        with patch.dict(sys.modules, modules):
            client_module = load("z1_fake.client", "client.py")
        client = object.__new__(client_module.ReadOnlyClient)
        client.devices = {"test": {"supports_start": True}}
        client.locks = {"test": asyncio.Lock()}
        client.channels = {"test": object()}
        client.last_start = {}
        client._query = AsyncMock(return_value={203: 1, 218: 10, 220: 0, 204:4,205:9,209:1})
        sent = AsyncMock(side_effect=TimeoutError)
        with patch.object(client_module, "send_decoded_command", sent):
            with self.assertRaises(TimeoutError):
                await client.start_current_program("test")
            with self.assertRaises(ValueError):
                await client.start_current_program("test")
        self.assertEqual(sent.await_count, 1)
        self.assertEqual(sent.call_args.args[1], {204:4,205:9,209:1,200:1})
        self.assertEqual(sent.call_args.kwargs["value_encoder"](1), 1)


if __name__ == "__main__":
    unittest.main()
