"""Ensure schema drift and unavailable readings fail closed."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "custom_components/roborock_z1_monitor/protocol.py"
spec = importlib.util.spec_from_file_location("z1_protocol", path)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class ProtocolTests(unittest.TestCase):
    def product(self, model="roborock.cd.a188"):
        return {"model": model, "schema": [
            {"id": key, "code": code, "mode": "ro", "type": "VALUE"}
            for key, code in p.FIELDS.items()
        ] + [{"id": 10000, "code": "id_query"}]}

    def test_observed_dryer_values_preserved_without_enum_guess(self):
        p.validate_schema(self.product())
        self.assertEqual(p.validate_values({203: 1, 218: 138, 220: 0}), {203: 1, 218: 138, 220: 0})

    def test_missing_invalid_data_never_becomes_zero(self):
        for invalid in ({203: 1}, {203: True, 218: 138, 220: 0}, {203: 1, 218: -1, 220: 0}):
            with self.assertRaises(ValueError):
                p.validate_values(invalid)

    def test_wrong_model_or_changed_schema_rejected(self):
        with self.assertRaises(ValueError):
            p.validate_schema(self.product("roborock.cd.unknown"))
        for field, value in (("code", "start"), ("mode", "rw"), ("type", "BOOL")):
            product = self.product()
            product["schema"][0][field] = value
            with self.assertRaises(ValueError):
                p.validate_schema(product)

    def test_unknown_state_is_preserved(self):
        self.assertEqual(p.validate_values({203: 99, 218: 0, 220: 88})[203], 99)

    def test_a204_read_only_schema_does_not_enable_start(self):
        product = self.product("roborock.cd.a204")
        p.validate_schema(product)
        self.assertFalse(p.supports_start(product))
        self.assertEqual(p.validate_values({203: 99, 218: 138, 220: 88}),
                         {203: 99, 218: 138, 220: 88})

    def test_a204_missing_or_changed_read_fields_are_rejected(self):
        for index in range(3):
            for field, value in (("code", "unexpected"), ("mode", "rw"), ("type", "BOOL")):
                with self.subTest(index=index, field=field):
                    product = self.product("roborock.cd.a204")
                    product["schema"][index][field] = value
                    with self.assertRaises(ValueError):
                        p.validate_schema(product)
            product = self.product("roborock.cd.a204")
            product["schema"].pop(index)
            with self.assertRaises(ValueError):
                p.validate_schema(product)
        for query in ([], [{"id": 10000, "code": "unexpected"}]):
            product = self.product("roborock.cd.a204")
            product["schema"] = product["schema"][:-1] + query
            with self.assertRaises(ValueError):
                p.validate_schema(product)

    def test_a204_allowlist_is_exact(self):
        for model in ("a204", "roborock.wm.a204", "roborock.cd.a204x"):
            with self.assertRaises(ValueError):
                p.validate_schema(self.product(model))


if __name__ == "__main__":
    unittest.main()
