# presence-app — Copyright (c) 2026 House of Solance. PolyForm Noncommercial 1.0.0. Required Notice: Copyright (c) 2026 House of Solance (https://github.com/SolanceLab)
"""The set lists each room once; each plugin is pinned to the same tag the Makefile fetches; the README names every pin."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class SetTest(unittest.TestCase):
    def setUp(self):
        self.market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
        self.make = dict(re.findall(r"^([A-Z_]+)\s*=\s*(\S+)", (ROOT / "Makefile").read_text(), re.M))

    def test_name_and_version(self):
        self.assertEqual(self.market["name"], "presence-app")
        heading = re.search(r"^## (\S+)", (ROOT / "CHANGELOG.md").read_text(), re.M).group(1)
        self.assertEqual(self.market["metadata"]["version"], heading)

    def test_each_plugin_pinned_to_the_make_release(self):
        names = [p["name"] for p in self.market["plugins"]]
        self.assertEqual(sorted(names), ["antechamber", "scriptorium"])
        for p in self.market["plugins"]:
            src = p["source"]
            self.assertEqual(src["source"], "git-subdir")
            self.assertEqual(src["url"], f"https://github.com/SolanceLab/{p['name']}.git")
            self.assertEqual(src["path"], "plugin")
            self.assertEqual(src["ref"], self.make[p["name"].upper()])

    def test_make_get_fetches_every_room_by_its_pin(self):
        make = (ROOT / "Makefile").read_text()
        for room, var in (("scriptorium", "SCRIPTORIUM"), ("antechamber", "ANTECHAMBER"), ("vault-map", "VAULT_MAP")):
            self.assertIn(f"{room}:$({var})", make)
        self.assertIn("--branch $$tag https://github.com/SolanceLab/$$room.git", make)

    def test_readme_names_no_fixed_version(self):
        readme = (ROOT / "README.md").read_text()
        for room in ("Scriptorium", "Antechamber", "vault-map"):
            self.assertIsNone(re.search(room + r" v\d+\.\d+\.\d+", readme), room)


if __name__ == "__main__":
    unittest.main()
