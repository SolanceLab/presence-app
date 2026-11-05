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


TAGS = {
    "antechamber": {"v1.0.0": "a" * 40, "v1.1.0": "b" * 40, "v1.1.0-rc1": "c" * 40, "v2": "d" * 40, "main": "e" * 40, "v0.9.0": "f" * 40},
    "scriptorium": {"v1.0.0": "1" * 40},
}


def h(c):
    """A fake 40-hex commit sha."""
    return c * 40


def entry(name, repo, ref, path="plugin", owner="SolanceLab", sha="auto", **extra):
    src = {"source": "git-subdir", "url": "https://github.com/%s/%s.git" % (owner, repo), "path": path}
    if ref:
        src["ref"] = ref
        sha = TAGS.get(repo, {}).get(ref) if sha == "auto" else sha  # pinned to the tag's commit by default
        if sha:
            src["sha"] = sha
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


def fetch(repo):
    return list(TAGS[repo].items())


def releases(repo):
    """Every strict tag counts as a published release unless a test says otherwise."""
    return set(TAGS[repo])


class Pick(unittest.TestCase):
    def test_highest_semver_only(self):
        self.assertEqual(bump.sha_of([("v1", "x")], "v1"), "x")
        self.assertIsNone(bump.sha_of([("v1", "x")], "v2"))
        self.assertEqual(bump.latest_tag(["v1.9.0", "v1.10.0", "v1.10.0-beta", "1.11.0", "latest"]), "v1.10.0")
        self.assertIsNone(bump.latest_tag(["main", "v1"]))


class Plan(unittest.TestCase):
    def run_plan(self, d=None, make="", f=fetch, r=releases):
        d = d or docs()
        ch = bump.plan_bumps(d, make, f, r)
        return ch, bump.apply(d, make, ch)

    def test_bumps_both_lists_in_step_and_version_and_metadata_once(self):
        ch, (new, _) = self.run_plan()
        self.assertEqual(new["claude"]["plugins"][0]["source"]["ref"], "v1.1.0")
        self.assertEqual(new["codex"]["plugins"][0]["source"]["ref"], "v1.1.0")
        self.assertEqual(new["claude"]["plugins"][0]["version"], "1.1.0")
        self.assertEqual(new["claude"]["metadata"]["version"], "1.0.1")

    def test_bump_writes_new_sha_into_claude_and_codex(self):
        _, (new, _) = self.run_plan()
        self.assertEqual(new["claude"]["plugins"][0]["source"]["sha"], "b" * 40)
        self.assertEqual(new["codex"]["plugins"][0]["source"]["sha"], "b" * 40)

    def test_moved_tag_is_tampered(self):
        d = docs()
        d["claude"]["plugins"][1]["source"]["sha"] = "9" * 40
        ch = bump.plan_bumps(d, "", fetch, releases)
        c = [x for x in ch if x["status"] == "tampered"][0]
        self.assertEqual((c["name"], c["was"], c["now"]), ("scriptorium", "9" * 40, "1" * 40))

    def test_vanished_tag_is_tampered(self):
        gone = lambda repo: [(n, s) for n, s in fetch(repo) if n != "v1.0.0"]
        ch = bump.plan_bumps(docs(), "", gone, releases)
        self.assertTrue(any(c["status"] == "tampered" and c["now"] is None for c in ch))

    def test_legacy_entry_without_sha_is_needs_pin_and_not_moved(self):
        d = docs()
        del d["claude"]["plugins"][0]["source"]["sha"]
        ch, (new, _) = self.run_plan(d)
        c = [x for x in ch if x["where"] == "claude" and x["name"] == "antechamber"][0]
        self.assertEqual((c["status"], c["pin"]), ("needs-pin", "a" * 40))
        self.assertEqual(new["claude"]["plugins"][0]["source"]["ref"], "v1.0.0")

    def test_makefile_pin_checked_against_marketplace_sha(self):
        make = "ANTECHAMBER = v1.0.0\n"
        ch = bump.plan_bumps(docs(), make, fetch, releases)
        self.assertEqual([c for c in ch if c["where"] == "makefile"][0]["status"], "bumped")
        self.assertNotIn("unpinned", [c for c in ch if c["where"] == "makefile"][0])
        d = docs()
        d["claude"]["plugins"][0]["source"]["sha"] = "9" * 40
        ch = bump.plan_bumps(d, make, fetch, releases)
        self.assertTrue(any(c["where"] == "makefile" and c["status"] == "tampered" for c in ch))

    def test_makefile_pin_without_marketplace_entry_is_unpinned(self):
        ch = bump.plan_bumps({}, "ANTECHAMBER = v1.0.0\n", fetch, releases)
        self.assertTrue(ch[0]["unpinned"] and ch[0]["status"] == "bumped")

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
        self.assertEqual(text, "ANTECHAMBER = v1.1.0\nANTECHAMBER_SHA = %s\nOTHER = v1.0.0\nVAULT_MAP = v2.0.0\n" % ("b" * 40))

    def test_fetch_error_leaves_that_repo_and_others_bump(self):
        def flaky(repo):
            if repo == "scriptorium":
                raise OSError("down")
            return fetch(repo)
        ch, (new, _) = self.run_plan(f=flaky)
        self.assertEqual(new["claude"]["plugins"][1]["source"]["ref"], "v1.0.0")
        self.assertEqual(new["claude"]["plugins"][0]["source"]["ref"], "v1.1.0")
        self.assertTrue(any(c["status"] == "error" and c["repo"] == "scriptorium" for c in ch))


class Released(unittest.TestCase):
    def plan(self, rel):
        return bump.plan_bumps(docs(), "", fetch, rel)

    def ante(self, ch):
        return [c for c in ch if c["where"] == "claude" and c["name"] == "antechamber"][0]

    def test_bare_tag_without_release_is_ignored_and_reported(self):
        c = self.ante(self.plan(lambda repo: {"v1.0.0"}))
        self.assertEqual((c["status"], c["ignored"]), ("current", "v1.1.0"))
        self.assertIn("ignored v1.1.0 (no published release)", bump.describe(c))

    def test_published_release_moves(self):
        c = self.ante(self.plan(releases))
        self.assertEqual((c["status"], c["new"], c["ignored"]), ("bumped", "v1.1.0", None))

    def test_release_of_a_tag_missing_from_tags_is_ignored(self):
        c = self.ante(self.plan(lambda repo: {"v1.0.0", "v9.0.0"}))
        self.assertEqual(c["status"], "current")

    def test_current_pin_needs_no_release(self):
        c = self.ante(self.plan(lambda repo: set()))
        self.assertEqual(c["status"], "current")

    def test_draft_and_prerelease_are_ignored(self):
        class R:
            def __init__(s, body):
                s.body, s.headers = body, {}
            def __enter__(s):
                return s
            def __exit__(s, *a):
                pass
            def read(s, *a):
                return s.body
        body = json.dumps([
            {"tag_name": "v1.1.0", "draft": True, "prerelease": False},
            {"tag_name": "v1.2.0", "draft": False, "prerelease": True},
            {"tag_name": "v1.0.0", "draft": False, "prerelease": False}]).encode()
        orig = bump.urllib.request.urlopen
        bump.urllib.request.urlopen = lambda req, timeout=0: R(body)
        try:
            self.assertEqual(bump.fetch_releases("antechamber"), {"v1.0.0"})
        finally:
            bump.urllib.request.urlopen = orig

    def test_releases_fetch_error_is_an_error_for_that_repo_only(self):
        def flaky(repo):
            if repo == "scriptorium":
                raise OSError("down")
            return releases(repo)
        ch = self.plan(flaky)
        self.assertTrue(any(c["status"] == "error" and c["repo"] == "scriptorium" for c in ch))
        self.assertEqual(self.ante(ch)["status"], "bumped")


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
        self.assertEqual(bump.main(["--check"], self.tmp, fetch, releases), 1)
        self.assertEqual(self.snapshot(), before)

    def test_dry_run_writes_nothing(self):
        before = self.snapshot()
        self.assertEqual(bump.main(["--dry-run"], self.tmp, fetch, releases), 0)
        self.assertEqual(self.snapshot(), before)

    def test_real_run_writes_then_check_is_clean(self):
        self.assertEqual(bump.main([], self.tmp, fetch, releases), 0)
        self.assertIn("v1.1.0", self.snapshot()[0])
        self.assertEqual(bump.main(["--check"], self.tmp, fetch, releases), 0)

    def test_lookup_error_exits_nonzero_and_writes_nothing(self):
        def flaky(repo):
            if repo == "scriptorium":
                raise OSError("rate limited")
            return fetch(repo)

        before = self.snapshot()
        for argv in ([], ["--check"], ["--dry-run"]):
            self.assertNotEqual(bump.main(argv, self.tmp, flaky, releases), 0)
        self.assertEqual(self.snapshot(), before)

    def test_tampered_exits_2_and_writes_nothing_though_another_would_bump(self):
        d = docs()
        d["claude"]["plugins"][1]["source"]["sha"] = "9" * 40  # scriptorium moved; antechamber would bump
        with open(os.path.join(self.tmp, *bump.STORES["claude"]), "w", encoding="utf-8") as fh:
            json.dump(d["claude"], fh, indent=2)
        before = self.snapshot()
        for argv in ([], ["--check"], ["--dry-run"], ["--pin-shas"]):
            self.assertEqual(bump.main(argv, self.tmp, fetch, releases), 2)
        self.assertEqual(self.snapshot(), before)

    def test_pin_shas_records_current_sha_without_moving(self):
        d = docs()
        for key in d:
            for p in d[key]["plugins"]:
                p["source"].pop("sha", None)
        for k, parts in bump.STORES.items():
            with open(os.path.join(self.tmp, *parts), "w", encoding="utf-8") as fh:
                json.dump(d[k], fh, indent=2)
        self.assertEqual(bump.main([], self.tmp, fetch, releases), 0)  # legacy: not moved
        self.assertNotIn("v1.1.0", self.snapshot()[0])
        self.assertEqual(bump.main(["--pin-shas"], self.tmp, fetch, releases), 0)
        with open(os.path.join(self.tmp, *bump.STORES["claude"]), encoding="utf-8") as fh:
            doc = json.load(fh)
        self.assertEqual(doc["plugins"][0]["source"]["sha"], "a" * 40)
        self.assertEqual(doc["plugins"][0]["source"]["ref"], "v1.0.0")
        self.assertNotIn("sha", doc["plugins"][2]["source"])
        self.assertEqual(bump.main(["--check"], self.tmp, fetch, releases), 1)


class MakefileSha(unittest.TestCase):
    SHA = "a" * 40

    def plan(self, make, d=None, f=fetch):
        ch = bump.plan_bumps(d if d is not None else {}, make, f, releases)
        return ch, bump.apply(d if d is not None else {}, make, ch)[1]

    def test_sha_verified_and_not_unpinned(self):
        ch, _ = self.plan("ANTECHAMBER = v1.0.0\nANTECHAMBER_SHA = %s\n" % self.SHA)
        self.assertEqual(ch[0]["status"], "bumped")
        self.assertNotIn("unpinned", ch[0])

    def test_moved_makefile_tag_is_refused(self):
        ch, _ = self.plan("ANTECHAMBER = v1.0.0\nANTECHAMBER_SHA = %s\n" % ("9" * 40))
        self.assertEqual(ch[0]["status"], "tampered")

    def test_move_writes_new_sha_and_leaves_other_vars(self):
        make = "A = 1\nANTECHAMBER = v1.0.0\nANTECHAMBER_SHA = %s\nB = 2\n" % self.SHA
        _, text = self.plan(make)
        self.assertEqual(text, "A = 1\nANTECHAMBER = v1.1.0\nANTECHAMBER_SHA = %s\nB = 2\n" % ("b" * 40))

    def test_move_adds_missing_sha_line_after_the_pin(self):
        _, text = self.plan("A = 1\nANTECHAMBER = v1.0.0\nB = 2\n")
        self.assertEqual(text, "A = 1\nANTECHAMBER = v1.1.0\nANTECHAMBER_SHA = %s\nB = 2\n" % ("b" * 40))

    def test_pin_shas_adds_sha_for_current_ref(self):
        make = "ANTECHAMBER = v1.0.0\n"
        ch = bump.plan_bumps({}, make, fetch, releases)
        self.assertEqual(bump.apply_make_pins(make, ch), "ANTECHAMBER = v1.0.0\nANTECHAMBER_SHA = %s\n" % self.SHA)

    def test_sha_mismatch_with_marketplace_is_tampered(self):
        ch, _ = self.plan("ANTECHAMBER = v1.0.0\nANTECHAMBER_SHA = %s\n" % ("9" * 40), d=docs())
        mk = [c for c in ch if c["where"] == "makefile"][0]
        self.assertEqual(mk["status"], "tampered")
        self.assertIn("REFUSED", bump.describe(mk))


class ChangelogHeading(unittest.TestCase):
    LOG = "# Changelog\n\n## 1.0.0\n\nFirst.\n"

    def changes(self):
        return bump.plan_bumps(docs(), "", fetch, releases)

    def test_heading_added_after_title_with_moved_list(self):
        out = bump.changelog_with(self.LOG, "1.0.1", self.changes())
        self.assertEqual(out, "# Changelog\n\n## 1.0.1\n\nPins moved to the newest releases: antechamber v1.0.0 \u2192 v1.1.0.\n\n## 1.0.0\n\nFirst.\n")

    def test_not_duplicated_and_not_added_on_no_move(self):
        once = bump.changelog_with(self.LOG, "1.0.1", self.changes())
        self.assertEqual(bump.changelog_with(once, "1.0.1", self.changes()), once)
        self.assertEqual(bump.changelog_with(self.LOG, "1.0.1", []), self.LOG)

    def test_no_title_goes_on_top(self):
        self.assertTrue(bump.changelog_with("## 1.0.0\n", "1.0.1", self.changes()).startswith("## 1.0.1\n"))


class ChangelogMain(Main):
    def setUp(self):
        super().setUp()
        self.log = os.path.join(self.tmp, "CHANGELOG.md")
        with open(self.log, "w", encoding="utf-8") as fh:
            fh.write("# Changelog\n\n## 1.0.0\n\nFirst.\n")

    def text(self):
        with open(self.log, encoding="utf-8") as fh:
            return fh.read()

    def test_real_run_writes_heading_dry_run_and_check_do_not(self):
        before = self.text()
        bump.main(["--dry-run"], self.tmp, fetch, releases)
        bump.main(["--check"], self.tmp, fetch, releases)
        self.assertEqual(self.text(), before)
        bump.main([], self.tmp, fetch, releases)
        self.assertTrue(self.text().startswith("# Changelog\n\n## 1.0.1\n"))
        bump.main([], self.tmp, fetch, releases)  # nothing left to move
        self.assertEqual(self.text().count("## 1.0.1"), 1)


if __name__ == "__main__":
    unittest.main()
