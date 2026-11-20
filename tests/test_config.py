import unittest

from helpers import load_config
from main import deep_merge


class TestConfig(unittest.TestCase):
    def test_config_toml_has_all_sections(self):
        cfg = load_config()
        for section in ("wheel", "steering", "pedals", "buttons", "ffb", "controller", "report", "web", "gadget"):
            self.assertIn(section, cfg)

    def test_deep_merge_nested(self):
        base = {"wheel": {"steering_degrees": 270, "gain": 1.0}}
        out = deep_merge(base, {"wheel": {"steering_degrees": 360}})
        self.assertEqual(out["wheel"], {"steering_degrees": 360, "gain": 1.0})
        self.assertEqual(base["wheel"]["steering_degrees"], 270)   # Basis unverändert

    def test_deep_merge_replaces_mapping_tables(self):
        base = {"buttons": {"A1": "A", "B1": "B"}, "hshifter": {"gears": {"G1": 1}, "enabled": False}}
        out = deep_merge(base, {"buttons": {"A1": "X"}, "hshifter": {"gears": {}}})
        self.assertEqual(out["buttons"], {"A1": "X"})               # ersetzt, nicht gemischt
        self.assertEqual(out["hshifter"], {"gears": {}, "enabled": False})

    def test_deep_merge_none_deletes(self):
        self.assertEqual(deep_merge({"a": 1, "b": 2}, {"a": None}), {"b": 2})


if __name__ == "__main__":
    unittest.main()
