# presence-app — Copyright (c) 2026 House of Solance. PolyForm Noncommercial 1.0.0. Required Notice: Copyright (c) 2026 House of Solance (https://github.com/SolanceLab)
"""Move every pinned plugin in the store to its repository's newest release tag (vX.Y.Z)."""
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


def fetch_tags(repo):
    """All (tag name, commit sha) pairs of SolanceLab/<repo>, following GitHub's Link pages."""
    url = "https://api.github.com/repos/SolanceLab/%s/tags?per_page=100" % repo
    headers = {"User-Agent": "solancelab-plugins-bump", "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    tags = []
    while url:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
            tags += [(t["name"], (t.get("commit") or {}).get("sha")) for t in json.load(r)]
            link = r.headers.get("Link") or ""
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else None
    return tags


def sha_of(tags, name):
    """The commit sha the tag `name` points at, or None when the tag is not there."""
    for n, sha in tags:
        if n == name:
            return sha
    return None


def _norm(path):
    return (path or "").lstrip("./")


def _short(sha):
    return (sha or "")[:12]


def plan_bumps(store_docs, makefile_text, fetch):
    """Return one change dict per entry.

    status is bumped / current / skipped / error / tampered (a pinned tag moved or vanished)
    / needs-pin (an entry with no sha yet; it is never moved). Nothing is mutated.
    store_docs: {"claude": doc, "codex": doc} (any subset).
    """
    cache = {}

    def remote(repo):
        if repo not in cache:
            try:
                cache[repo] = (fetch(repo), None)
            except Exception as exc:  # one repo failing must not stop the others
                cache[repo] = (None, "%s: %s" % (type(exc).__name__, str(exc)[:80]))
        return cache[repo]

    def judge(where, name, repo, old, sha):
        tags, err = remote(repo)
        base = {"where": where, "name": name, "repo": repo, "old": old}
        if err:
            return dict(base, status="error", reason=err)
        now = sha_of(tags, old)
        if sha and (now or "").lower() != sha.lower():
            return dict(base, status="tampered", was=sha, now=now)
        if not sha and where != "makefile":
            return dict(base, status="needs-pin", pin=now)
        new = latest_tag([n for n, _ in tags])
        if new and parse_semver(new) > parse_semver(old):
            return dict(base, status="bumped", new=new, new_sha=sha_of(tags, new))
        return dict(base, status="current")

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
            sha = marketplace_shas.get((short, m.group(4)))  # cross-check against the store's pin
            c = judge("makefile", short, short, m.group(4), sha)
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

    return docs, MAKE_VAR.sub(swap, makefile_text or "")


def apply_pins(store_docs, changes):
    """Record the current sha of every needs-pin entry's present ref (no version moves)."""
    docs = copy.deepcopy(store_docs)
    pins = {(c["repo"], c.get("path"), c["old"]): c["pin"] for c in changes if c["status"] == "needs-pin" and c.get("pin")}
    for _, _, src, k in _each_entry(docs):
        if k in pins and not src.get("sha"):
            src["sha"] = pins[k]
    return docs


def describe(c):
    if c["status"] == "bumped":
        return "bumped %s: %s -> %s%s" % (c["name"], c["old"], c["new"], " (unpinned)" if c.get("unpinned") else "")
    if c["status"] == "current":
        return "up to date %s %s" % (c["name"], c["old"])
    if c["status"] == "skipped":
        return "skipped %s (%s)" % (c["name"], c["reason"])
    if c["status"] == "needs-pin":
        return "needs-pin %s %s (no sha recorded; not moved)" % (c["name"], c["old"])
    if c["status"] == "tampered":
        if not c["now"]:
            return "REFUSED: %s tag %s vanished" % (c["name"], c["old"])
        return "REFUSED: %s tag %s moved from %s to %s" % (c["name"], c["old"], _short(c["was"]), _short(c["now"]))
    return "error %s: %s" % (c["repo"], c["reason"])


def _write_docs(docs, paths):
    for k, doc in docs.items():
        with open(paths[k], "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2, ensure_ascii=False)
            fh.write("\n")


def main(argv=None, root=ROOT, fetch=fetch_tags):
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
    changes = plan_bumps(docs, make_text, fetch)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
