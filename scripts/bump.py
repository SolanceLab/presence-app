# presence-app — Copyright (c) 2026 House of Solance. PolyForm Noncommercial 1.0.0. Required Notice: Copyright (c) 2026 House of Solance (https://github.com/SolanceLab)
"""Move every pinned plugin in the store to its repository's newest published GitHub Release (tag vX.Y.Z); a bare tag is never enough."""
import copy
import json
import os
import re
import sys
import urllib.request

STORES = {"claude": (".claude-plugin", "marketplace.json"), "codex": (".agents", "plugins", "marketplace.json")}
MAKE_VAR = re.compile(r"^([ \t]*)([A-Za-z_][A-Za-z0-9_]*)([ \t]*[:?]?=[ \t]*)(v\d+\.\d+\.\d+)([ \t]*)$", re.M)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOWN_ROOMS = {"antechamber", "scriptorium", "vault-map", "stack-guard"}  # repos a Makefile may pin
SHA40 = r"[0-9a-fA-F]{40}"
SEMVER = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
OWNER_URL = re.compile(r"^https://github\.com/SolanceLab/([A-Za-z0-9._-]+)\.git$")


def parse_semver(tag):
    """'v1.2.3' -> (1, 2, 3); anything else (pre-release, no v, branch) -> None."""
    m = SEMVER.match(tag or "")
    return tuple(int(x) for x in m.groups()) if m else None


def latest_tag(tags):
    """Highest strict vX.Y.Z tag, or None."""
    good = [t for t in tags if parse_semver(t)]
    return max(good, key=parse_semver) if good else None


def _pages(url):
    """Every JSON item of a GitHub list endpoint, following Link pages."""
    headers = {"User-Agent": "solancelab-plugins-bump", "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    items = []
    while url:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
            items += json.load(r)
            link = r.headers.get("Link") or ""
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else None
    return items


def fetch_tags(repo):
    """All (tag name, commit sha) pairs of SolanceLab/<repo>, following GitHub's Link pages."""
    items = _pages("https://api.github.com/repos/SolanceLab/%s/tags?per_page=100" % repo)
    return [(t["name"], (t.get("commit") or {}).get("sha")) for t in items]


def fetch_releases(repo):
    """Tag names of SolanceLab/<repo>'s PUBLISHED releases (not draft, not prerelease)."""
    items = _pages("https://api.github.com/repos/SolanceLab/%s/releases?per_page=100" % repo)
    return {r["tag_name"] for r in items if not r.get("draft") and not r.get("prerelease")}


def sha_of(tags, name):
    """The commit sha the tag `name` points at, or None when the tag is not there."""
    for n, sha in tags:
        if n == name:
            return sha
    return None


def _make_sha_re(var):
    return re.compile(r"^([ \t]*)%s_SHA([ \t]*[:?]?=[ \t]*)(%s)([ \t]*)$" % (re.escape(var), SHA40), re.M)


def make_sha(text, var):
    """The 40-hex commit recorded as `<var>_SHA = ...` in the Makefile, or None."""
    m = _make_sha_re(var).search(text or "")
    return m.group(3) if m else None


def set_make_sha(text, var, sha):
    """Write `<var>_SHA = sha` into the Makefile text: replace the line, or add it right after the `<var> = vX.Y.Z` line."""
    m = _make_sha_re(var).search(text)
    if m:
        return text[:m.start(3)] + sha + text[m.end(3):]
    for v in MAKE_VAR.finditer(text):
        if v.group(2) == var:
            return text[:v.end()] + "\n" + v.group(1) + var + "_SHA" + v.group(3) + sha + text[v.end():]
    return text


def _norm(path):
    return (path or "").lstrip("./")


def _short(sha):
    return (sha or "")[:12]


def plan_bumps(store_docs, makefile_text, fetch_tags, fetch_releases):
    """Return one change dict per entry.

    status is bumped / current / skipped / error / tampered (a pinned tag moved or vanished)
    / needs-pin (an entry with no sha yet; it is never moved). Nothing is mutated.
    A pin moves only to a tag that has a published Release; a higher bare tag is reported as `ignored`.
    store_docs: {"claude": doc, "codex": doc} (any subset).
    """
    cache = {}

    def remote(repo):
        if repo not in cache:
            try:
                cache[repo] = ((fetch_tags(repo), set(fetch_releases(repo))), None)
            except Exception as exc:  # one repo failing must not stop the others
                cache[repo] = (None, "%s: %s" % (type(exc).__name__, str(exc)[:80]))
        return cache[repo]

    def judge(where, name, repo, old, sha):
        got, err = remote(repo)
        base = {"where": where, "name": name, "repo": repo, "old": old}
        if err:
            return dict(base, status="error", reason=err)
        tags, released = got
        now = sha_of(tags, old)
        if sha and (now or "").lower() != sha.lower():
            return dict(base, status="tampered", was=sha, now=now)
        if not sha and where != "makefile":
            return dict(base, status="needs-pin", pin=now)
        names = [n for n, _ in tags]
        new = latest_tag([n for n in names if n in released])
        top = latest_tag(names)
        ignored = top if top and top not in released and parse_semver(top) > parse_semver(old) else None
        if new and parse_semver(new) > parse_semver(old):
            return dict(base, status="bumped", new=new, new_sha=sha_of(tags, new), ignored=ignored)
        return dict(base, status="current", ignored=ignored)

    changes = []
    marketplace_shas = {}  # (repo, ref) -> sha recorded in a marketplace entry
    for key, doc in store_docs.items():
        for p in doc.get("plugins", []):
            src = p.get("source") or {}
            m = OWNER_URL.match(src.get("url") or "")
            if src.get("source") != "git-subdir" or not m:
                changes.append({"status": "skipped", "where": key, "name": p.get("name"), "reason": "not a SolanceLab git-subdir"})
            elif not parse_semver(src.get("ref")):
                changes.append({"status": "skipped", "where": key, "name": p.get("name"), "reason": "no release ref"})
            else:
                if src.get("sha"):
                    marketplace_shas.setdefault((m.group(1), src["ref"]), src["sha"])
                c = judge(key, p["name"], m.group(1), src["ref"], src.get("sha"))
                c["path"] = _norm(src.get("path"))
                changes.append(c)
    for m in MAKE_VAR.finditer(makefile_text or ""):
        short = m.group(2).lower().replace("_", "-")
        if short in KNOWN_ROOMS:
            own = make_sha(makefile_text, m.group(2))
            mkt = marketplace_shas.get((short, m.group(4)))  # cross-check against the store's pin
            if own and mkt and own.lower() != mkt.lower():
                changes.append({"where": "makefile", "name": short, "repo": short, "old": m.group(4), "var": m.group(2),
                                "status": "tampered", "was": own, "now": mkt, "reason": "Makefile sha differs from the store's sha"})
                continue
            sha = own or mkt
            c = judge("makefile", short, short, m.group(4), sha)
            c["var"], c["make_sha"] = m.group(2), own
            got, _ = remote(short)
            c["now_sha"] = sha_of(got[0], m.group(4)) if got else None
            if not sha:
                c["unpinned"] = True
            changes.append(c)
    return changes


def _each_entry(docs):
    for key, doc in docs.items():
        for p in doc.get("plugins", []):
            src = p.get("source") or {}
            m = OWNER_URL.match(src.get("url") or "")
            if m:
                yield key, p, src, (m.group(1), _norm(src.get("path")), src.get("ref"))


def apply(store_docs, makefile_text, changes):
    """Return (new_docs, new_makefile_text) with the 'bumped' changes written in (ref and sha)."""
    docs = copy.deepcopy(store_docs)
    moves = {(c["where"], c["repo"], c.get("path"), c["old"]): c for c in changes if c["status"] == "bumped" and c["where"] != "makefile"}
    moved = False
    for key, p, src, k in _each_entry(docs):
        c = moves.get((key,) + k)
        if c:
            src["ref"] = c["new"]
            if c.get("new_sha"):
                src["sha"] = c["new_sha"]
            if key == "claude" and "version" in p:
                p["version"] = c["new"][1:]
            moved = True
    if moved and "claude" in docs:
        meta = docs["claude"].setdefault("metadata", {})
        parts = (meta.get("version") or "1.0.0").split(".")
        if len(parts) == 3 and all(x.isdigit() for x in parts):
            meta["version"] = "%s.%s.%d" % (parts[0], parts[1], int(parts[2]) + 1)
    make_moves = {c["name"]: c["new"] for c in changes if c["status"] == "bumped" and c["where"] == "makefile"}

    def swap(m):
        new = make_moves.get(m.group(2).lower().replace("_", "-"))
        return m.group(1) + m.group(2) + m.group(3) + (new or m.group(4)) + m.group(5)

    text = MAKE_VAR.sub(swap, makefile_text or "")
    for c in changes:
        if c["status"] == "bumped" and c["where"] == "makefile" and c.get("new_sha"):
            text = set_make_sha(text, c["var"], c["new_sha"])
    return docs, text


def apply_make_pins(makefile_text, changes):
    """Add `<VAR>_SHA` (the current ref's commit) to every Makefile pin that has none."""
    text = makefile_text or ""
    for c in changes:
        if c["where"] == "makefile" and c["status"] in ("bumped", "current") and not c.get("make_sha") and c.get("now_sha"):
            text = set_make_sha(text, c["var"], c["now_sha"])
    return text


def moved_pins(changes):
    """'name vA -> vB' pairs of the bumped pins, each once (the Codex list repeats the Claude entries)."""
    out = []
    for c in changes:
        if c["status"] == "bumped":
            pair = "%s %s \u2192 %s" % (c["name"], c["old"], c["new"])
            if pair not in out:
                out.append(pair)
    return out


def changelog_with(text, version, changes):
    """The CHANGELOG with a `## version` block for the moved pins, unless that heading is already the newest."""
    moved = moved_pins(changes)
    first = re.search(r"^## .*$", text, re.M)
    if not moved or (first and first.group(0).strip() == "## " + version):
        return text
    block = "## %s\n\nPins moved to the newest releases: %s.\n\n" % (version, ", ".join(moved))
    if not re.match(r"# ", text):
        return block + text
    if first:
        return text[:first.start()] + block + text[first.start():]
    return text.rstrip("\n") + "\n\n" + block.rstrip("\n") + "\n"


def apply_pins(store_docs, changes):
    """Record the current sha of every needs-pin entry's present ref (no version moves)."""
    docs = copy.deepcopy(store_docs)
    pins = {(c["repo"], c.get("path"), c["old"]): c["pin"] for c in changes if c["status"] == "needs-pin" and c.get("pin")}
    for _, _, src, k in _each_entry(docs):
        if k in pins and not src.get("sha"):
            src["sha"] = pins[k]
    return docs


def describe(c):
    skip = " [ignored %s (no published release)]" % c["ignored"] if c.get("ignored") else ""
    if c["status"] == "bumped":
        return "bumped %s: %s -> %s%s%s" % (c["name"], c["old"], c["new"], " (unpinned)" if c.get("unpinned") else "", skip)
    if c["status"] == "current":
        return "up to date %s %s%s" % (c["name"], c["old"], skip)
    if c["status"] == "skipped":
        return "skipped %s (%s)" % (c["name"], c["reason"])
    if c["status"] == "needs-pin":
        return "needs-pin %s %s (no sha recorded; not moved)" % (c["name"], c["old"])
    if c["status"] == "tampered":
        if c.get("reason"):
            return "REFUSED: %s: %s (%s vs %s)" % (c["name"], c["reason"], _short(c["was"]), _short(c["now"]))
        if not c["now"]:
            return "REFUSED: %s tag %s vanished" % (c["name"], c["old"])
        return "REFUSED: %s tag %s moved from %s to %s" % (c["name"], c["old"], _short(c["was"]), _short(c["now"]))
    return "error %s: %s" % (c["repo"], c["reason"])


def _write_docs(docs, paths):
    for k, doc in docs.items():
        with open(paths[k], "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.write("\n")


def main(argv=None, root=ROOT, fetch=fetch_tags, releases=fetch_releases):
    argv = sys.argv[1:] if argv is None else argv
    dry, check, pin = "--dry-run" in argv, "--check" in argv, "--pin-shas" in argv
    paths = {k: os.path.join(root, *parts) for k, parts in STORES.items()}
    docs = {}
    for k, path in paths.items():
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                docs[k] = json.load(fh)
    make_path = os.path.join(root, "Makefile")
    make_text = open(make_path, encoding="utf-8").read() if os.path.exists(make_path) else ""
    changes = plan_bumps(docs, make_text, fetch, releases)
    seen = set()
    for c in changes:
        line = describe(c)
        if line not in seen:  # the Codex list repeats the Claude entries
            seen.add(line)
            print(line)
    if any(c["status"] == "tampered" for c in changes):
        return 2  # a moved or vanished tag changes nothing, whatever else is pending
    if any(c["status"] == "error" for c in changes):
        return 2  # a failed lookup must fail the run before anything is written
    unpinned = any(c["status"] == "needs-pin" for c in changes)
    if unpinned and not pin:
        print("run: python3 scripts/bump.py --pin-shas")
    if pin:
        if not dry:
            _write_docs(apply_pins(docs, changes), paths)
            new_make = apply_make_pins(make_text, changes)
            if new_make != make_text:
                with open(make_path, "w", encoding="utf-8") as fh:
                    fh.write(new_make)
        return 0
    todo = any(c["status"] == "bumped" for c in changes)
    if check:
        return 1 if todo else 0
    if todo and not dry:
        new_docs, new_make = apply(docs, make_text, changes)
        _write_docs(new_docs, paths)
        if new_make != make_text:
            with open(make_path, "w", encoding="utf-8") as fh:
                fh.write(new_make)
        old_v = (docs.get("claude", {}).get("metadata") or {}).get("version")
        new_v = (new_docs.get("claude", {}).get("metadata") or {}).get("version")
        if new_v and new_v != old_v:
            # the bundle plugin carries the store version too (tests/test_set.py checks they match)
            for side in (".claude-plugin", ".codex-plugin"):
                ppath = os.path.join(root, "plugin", side, "plugin.json")
                if os.path.exists(ppath):
                    with open(ppath, encoding="utf-8") as fh:
                        pdoc = json.load(fh)
                    pdoc["version"] = new_v
                    with open(ppath, "w", encoding="utf-8") as fh:
                        fh.write(json.dumps(pdoc, indent=2, ensure_ascii=False) + "\n")
        log_path = os.path.join(root, "CHANGELOG.md")
        if new_v and new_v != old_v and os.path.exists(log_path):
            with open(log_path, encoding="utf-8") as fh:
                log = fh.read()
            new_log = changelog_with(log, new_v, changes)
            if new_log != log:
                with open(log_path, "w", encoding="utf-8") as fh:
                    fh.write(new_log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
