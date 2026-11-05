# presence-app — Copyright (c) 2026 House of Solance. PolyForm Noncommercial 1.0.0. Required Notice: Copyright (c) 2026 House of Solance (https://github.com/SolanceLab)
"""The auto-bump moves pins to the newest release tag, never down, never off-list, with no network."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import bump  # noqa: E402


def entry(name, repo, ref, path="plugin", owner="SolanceLab", **extra):
    src = {"source": "git-subdir", "url": "https://github.com/%s/%s.git" % (owner, repo), "path": path}
    if ref:
        src["ref"] = ref
    return dict(name=name, source=src, **extra)


def docs():
    return {
        "claude": {"metadata": {"version": "1.0.0"}, "plugins": [
            entry("antechamber", "antechamber", "v1.0.0", version="1.0.0"),
            entry("scriptorium", "scriptorium", "v1.0.0"),
            entry("discord", "tertulia", None),
            entry("other", "thing", "v1.0.0", owner="Someone"),
        ]},
        "codex": {"plugins": [entry("antechamber", "antechamber", "v1.0.0", path="./plugin")]},
    }


TAGS = {"antechamber": ["v1.0.0", "v1.1.0", "v1.1.0-rc1", "v2", "main", "v0.9.0"], "scriptorium": ["v1.0.0"]}


def fetch(repo):
    return TAGS[repo]


class Pick(unittest.TestCase):
    def test_highest_semver_only(self):
        self.assertEqual(bump.latest_tag(["v1.9.0", "v1.10.0", "v1.10.0-beta", "1.11.0", "latest"]), "v1.10.0")
        self.assertIsNone(bump.latest_tag(["main", "v1"]))


class Plan(unittest.TestCase):
    def run_plan(self, d=None, make="", f=fetch):
        d = d or docs()
        ch = bump.plan_bumps(d, make, f)
        return ch, bump.apply(d, make, ch)

    def test_bumps_both_lists_in_step_and_version_and_metadata_once(self):
        ch, (new, _) = self.run_plan()
        self.assertEqual(new["claude"]["plugins"][0]["source"]["ref"], "v1.1.0")
        self.assertEqual(new["codex"]["plugins"][0]["source"]["ref"], "v1.1.0")
        self.assertEqual(new["claude"]["plugins"][0]["version"], "1.1.0")
        self.assertEqual(new["claude"]["metadata"]["version"], "1.0.1")

    def test_no_move_leaves_metadata_alone(self):
        d = docs()
        for p in d["claude"]["plugins"]:
            if p["name"] == "antechamber":
                p["source"]["ref"] = "v1.1.0"
        d["codex"]["plugins"][0]["source"]["ref"] = "v1.1.0"
        d["claude"]["plugins"][1]["source"]["ref"] = "v1.0.0"
        _, (new, _) = self.run_plan(d)
        self.assertEqual(new["claude"]["metadata"]["version"], "1.0.0")

    def test_never_downgrades(self):
        d = docs()
        d["claude"]["plugins"][0]["source"]["ref"] = "v3.0.0"
        d["codex"]["plugins"][0]["source"]["ref"] = "v3.0.0"
        ch, (new, _) = self.run_plan(d)
        self.assertEqual(new["claude"]["plugins"][0]["source"]["ref"], "v3.0.0")

    def test_skips_no_ref_and_other_owners(self):
        ch, (new, _) = self.run_plan()
        status = {c["name"]: c["status"] for c in ch if c["where"] == "claude"}
        self.assertEqual(status["discord"], "skipped")
        self.assertEqual(status["other"], "skipped")
        self.assertNotIn("ref", new["claude"]["plugins"][2]["source"])

    def test_makefile_var_bumped_and_others_left(self):
        make = "ANTECHAMBER = v1.0.0\nOTHER = v1.0.0\nVAULT_MAP = v2.0.0\n"
        _, (_, text) = self.run_plan(make=make)
        self.assertEqual(text, "ANTECHAMBER = v1.1.0\nOTHER = v1.0.0\nVAULT_MAP = v2.0.0\n")

    def test_fetch_error_leaves_that_repo_and_others_bump(self):
        def flaky(repo):
            if repo == "scriptorium":
                raise OSError("down")
            return fetch(repo)
        ch, (new, _) = self.run_plan(f=flaky)
        self.assertEqual(new["claude"]["plugins"][1]["source"]["ref"], "v1.0.0")
        self.assertEqual(new["claude"]["plugins"][0]["source"]["ref"], "v1.1.0")
        self.assertTrue(any(c["status"] == "error" and c["repo"] == "scriptorium" for c in ch))


class Main(unittest.TestCase):
    def setUp(self):
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)
        self.tmp = tempfile.mkdtemp()
        for parts in bump.STORES.values():
            os.makedirs(os.path.join(self.tmp, *parts[:-1]), exist_ok=True)
        d = docs()
        for k, parts in bump.STORES.items():
            with open(os.path.join(self.tmp, *parts), "w", encoding="utf-8") as fh:
                json.dump(d[k], fh, indent=2)
        self.addCleanup(shutil.rmtree, self.tmp)

    def snapshot(self):
        out = []
        for p in bump.STORES.values():
            with open(os.path.join(self.tmp, *p), encoding="utf-8") as fh:
                out.append(fh.read())
        return out

    def test_check_exits_1_and_writes_nothing(self):
        before = self.snapshot()
        self.assertEqual(bump.main(["--check"], self.tmp, fetch), 1)
        self.assertEqual(self.snapshot(), before)

    def test_dry_run_writes_nothing(self):
        before = self.snapshot()
        self.assertEqual(bump.main(["--dry-run"], self.tmp, fetch), 0)
        self.assertEqual(self.snapshot(), before)

    def test_real_run_writes_then_check_is_clean(self):
        self.assertEqual(bump.main([], self.tmp, fetch), 0)
        self.assertIn("v1.1.0", self.snapshot()[0])
        self.assertEqual(bump.main(["--check"], self.tmp, fetch), 0)

    def test_lookup_error_exits_nonzero_and_writes_nothing(self):
        def flaky(repo):
            if repo == "scriptorium":
                raise OSError("rate limited")
            return TAGS[repo]

        before = self.snapshot()
        for argv in ([], ["--check"], ["--dry-run"]):
            self.assertNotEqual(bump.main(argv, self.tmp, flaky), 0)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
