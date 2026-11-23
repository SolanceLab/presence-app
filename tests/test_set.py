# presence-app — Copyright (c) 2026 House of Solance. PolyForm Noncommercial 1.0.0. Required Notice: Copyright (c) 2026 House of Solance (https://github.com/SolanceLab)
"""The set lists each room once; each plugin is pinned to the same tag the Makefile fetches; the README names every pin."""
import importlib.util
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("bundle", ROOT / "scripts" / "bundle.py")
bundle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bundle)


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
        self.assertEqual(sorted(names), ["antechamber", "scriptorium", "vault-map", "work-map"])
        for p in self.market["plugins"]:
            src = p["source"]
            self.assertEqual(src["source"], "git-subdir")
            self.assertEqual(src["url"], f"https://github.com/SolanceLab/{p['name']}.git")
            self.assertEqual(src["path"], "plugin")
            self.assertEqual(src["ref"], self.make[p["name"].upper().replace("-", "_")])
            self.assertEqual(src["sha"], self.make[p["name"].upper().replace("-", "_") + "_SHA"])

    def test_codex_list_matches_the_claude_list(self):
        codex = json.loads((ROOT / ".agents" / "plugins" / "marketplace.json").read_text())
        claude = {p["name"]: p["source"] for p in self.market["plugins"]}
        self.assertEqual(sorted(p["name"] for p in codex["plugins"]), sorted(claude))
        for p in codex["plugins"]:
            src, want = p["source"], claude[p["name"]]
            self.assertEqual((src["url"], src["ref"], src["sha"]), (want["url"], want["ref"], want["sha"]))
            self.assertEqual(p["policy"]["installation"], "AVAILABLE")

    def test_claude_bundle_depends_on_the_four_rooms(self):
        plugin = json.loads((ROOT / "plugin" / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(plugin["name"], "presence-app")
        self.assertEqual(plugin["version"], self.market["metadata"]["version"])
        self.assertEqual(sorted(plugin["dependencies"]), ["antechamber", "scriptorium", "vault-map", "work-map"])

    def test_codex_bundle_is_one_plugin_with_all_four_rooms(self):
        plugin = json.loads((ROOT / "plugin" / ".codex-plugin" / "plugin.json").read_text())
        self.assertEqual(plugin["name"], "presence-app")
        self.assertEqual(plugin["version"], self.market["metadata"]["version"])
        skills = sorted(p.parent.name for p in (ROOT / "plugin" / "codex-skills").glob("*/SKILL.md"))
        self.assertEqual(skills, ["antechamber", "presence-app", "scriptorium", "vault-map", "work-map"])
        servers = json.loads((ROOT / "plugin" / plugin["mcpServers"]).read_text())["mcpServers"]
        self.assertEqual(sorted(servers), ["antechamber", "scriptorium"])
        self.assertIn("@" + self.make["ANTECHAMBER_SHA"], " ".join(servers["antechamber"]["args"]))
        self.assertEqual(servers["scriptorium"]["bearer_token_env_var"], "SCRIPTORIUM_MCP_KEY")
        self.assertNotIn("headers", servers["scriptorium"])

    def test_codex_bundle_skills_are_the_rooms_skills_at_the_pins(self):
        rooms = ROOT / "rooms"
        if not rooms.is_dir():
            self.skipTest("run make get first: this compares the bundled skills with the pinned rooms")
        for room in ("antechamber", "scriptorium", "vault-map", "work-map"):
            src = rooms / room / "plugin" / "skills" / room / "SKILL.md"
            if not src.is_file():
                self.skipTest(f"rooms/{room} not fetched")
            bundled = (ROOT / "plugin" / "codex-skills" / room / "SKILL.md").read_text()
            self.assertEqual(bundled, bundle.codex_text(room, src.read_text()), room)

    def test_codex_overview_matches_the_claude_overview(self):
        a = (ROOT / "plugin" / "skills" / "presence-app" / "SKILL.md").read_text()
        b = (ROOT / "plugin" / "codex-skills" / "presence-app" / "SKILL.md").read_text()
        self.assertEqual(a, b)
        self.assertIn("work-map", b)

    def test_work_map_scripts_are_bundled_for_its_skill(self):
        for name in ("decisions.py", "pipeline.py", "ships.py", "work_map.py", "_writelock.py"):
            self.assertTrue((ROOT / "plugin" / "scripts" / name).is_file(), name)

    def test_bundle_copies_scripts_from_the_pinned_tree_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            room, out = Path(tmp) / "room", Path(tmp) / "out"
            (room / "plugin" / "scripts").mkdir(parents=True)
            (room / "plugin" / "scripts" / "a.py").write_text("print('pinned')\n")
            git = lambda *a: subprocess.run(["git", "-C", str(room), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)
            git("init", "-q")
            git("add", ".")
            git("commit", "-q", "-m", "pin")
            sha = subprocess.run(["git", "-C", str(room), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
            (room / "plugin" / "scripts" / "a.py").write_text("print('edited')\n")
            (room / "plugin" / "scripts" / "untracked.py").write_text("print('stray')\n")
            bundle.copy_pinned_scripts(room, sha, out)
            self.assertEqual((out / "a.py").read_text(), "print('pinned')\n")
            self.assertFalse((out / "untracked.py").exists())

    def test_work_map_codex_skill_promises_no_unbundled_hook(self):
        text = (ROOT / "plugin" / "codex-skills" / "work-map" / "SKILL.md").read_text()
        self.assertNotIn("WORK_MAP_SHIP_REMINDER", text)
        self.assertNotIn("hook", text.lower())

    def test_make_get_fetches_every_room_by_its_pin(self):
        make = (ROOT / "Makefile").read_text()
        for room, var in (("scriptorium", "SCRIPTORIUM"), ("antechamber", "ANTECHAMBER"), ("vault-map", "VAULT_MAP"), ("work-map", "WORK_MAP")):
            self.assertIn(f"{room}:$({var})", make)
        self.assertIn("--branch $$tag https://github.com/SolanceLab/$$room.git", make)

    def test_readme_names_no_fixed_version(self):
        readme = (ROOT / "README.md").read_text()
        for room in ("Scriptorium", "Antechamber", "vault-map", "work-map"):
            self.assertIsNone(re.search(room + r" v\d+\.\d+\.\d+", readme), room)


if __name__ == "__main__":
    unittest.main()
