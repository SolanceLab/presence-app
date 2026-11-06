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

    def test_codex_list_matches_the_claude_list(self):
        codex = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text())
        claude = {p["name"]: p["source"] for p in self.market["plugins"]}
        self.assertEqual(sorted(p["name"] for p in codex["plugins"]), sorted(claude))
        for p in codex["plugins"]:
            src, want = p["source"], claude[p["name"]]
            self.assertEqual((src["url"], src["ref"], src["sha"]), (want["url"], want["ref"], want["sha"]))
            self.assertEqual(p["policy"]["installation"], "AVAILABLE")

    def test_claude_bundle_depends_on_the_three_rooms(self):
        plugin = json.loads((ROOT / "plugin" / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(plugin["name"], "presence-app")
        self.assertEqual(plugin["version"], self.market["metadata"]["version"])
        self.assertEqual(sorted(plugin["dependencies"]), ["antechamber", "scriptorium", "vault-map"])

    def test_codex_bundle_is_one_plugin_with_all_three_rooms(self):
        plugin = json.loads((ROOT / "plugin" / ".codex-plugin" / "plugin.json").read_text())
        self.assertEqual(plugin["name"], "presence-app")
        self.assertEqual(plugin["version"], self.market["metadata"]["version"])
        skills = sorted(p.parent.name for p in (ROOT / "plugin" / "codex-skills").glob("*/SKILL.md"))
        self.assertEqual(skills, ["antechamber", "presence-app", "scriptorium", "vault-map"])
        servers = json.loads((ROOT / "plugin" / plugin["mcpServers"]).read_text())["mcpServers"]
        self.assertEqual(sorted(servers), ["antechamber", "scriptorium"])
        self.assertIn("@" + self.make["ANTECHAMBER_SHA"], " ".join(servers["antechamber"]["args"]))
        self.assertEqual(servers["scriptorium"]["bearer_token_env_var"], "SCRIPTORIUM_MCP_KEY")
        self.assertNotIn("headers", servers["scriptorium"])

    def test_codex_bundle_skills_are_the_rooms_skills_at_the_pins(self):
        rooms = ROOT / "rooms"
        if not rooms.is_dir():
            self.skipTest("run make get first: this compares the bundled skills with the pinned rooms")
        for room in ("antechamber", "scriptorium", "vault-map"):
            src = rooms / room / "plugin" / "skills" / room / "SKILL.md"
            if not src.is_file():
                self.skipTest(f"rooms/{room} not fetched")
            bundled = (ROOT / "plugin" / "codex-skills" / room / "SKILL.md").read_text()
            self.assertEqual(bundled, src.read_text(), room)

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
