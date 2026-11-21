import unittest

from helpers import ROOT  # noqa: F401
from updater import parse_version, pick_latest


class TestUpdater(unittest.TestCase):
    def test_parse_and_order(self):
        self.assertIsNone(parse_version("main"))
        self.assertIsNone(parse_version(""))
        self.assertGreater(parse_version("v0.4.0"), parse_version("0.3.0"))
        self.assertGreater(parse_version("0.3.0"), parse_version("0.3.0-rc1"))   # Final > Vorabversion
        self.assertGreater(parse_version("v0.10.0"), parse_version("v0.9.9"))   # numerisch, nicht alphabetisch
        self.assertEqual(parse_version("v1.2.3"), parse_version("1.2.3"))

    def test_pick_latest(self):
        rels = [
            {"tag_name": "v0.3.0", "prerelease": True},
            {"tag_name": "v0.5.0", "draft": True},                # Entwürfe nie
            {"tag_name": "v0.4.0", "prerelease": True},
            {"tag_name": "nightly"},                               # kein Versions-Tag
            {"tag_name": "v0.3.5", "prerelease": False},
        ]
        self.assertEqual(pick_latest(rels)["tag_name"], "v0.4.0")
        self.assertEqual(pick_latest(rels, include_prerelease=False)["tag_name"], "v0.3.5")
        self.assertIsNone(pick_latest([]))


if __name__ == "__main__":
    unittest.main()
