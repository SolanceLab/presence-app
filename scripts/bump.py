# presence-app — Copyright (c) 2026 House of Solance. PolyForm Noncommercial 1.0.0. Required Notice: Copyright (c) 2026 House of Solance (https://github.com/SolanceLab)
"""Move every pinned plugin in the store to its repository's newest release tag (vX.Y.Z)."""
import copy
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORES = {"claude": (".claude-plugin", "marketplace.json"), "codex": (".agents", "plugins", "marketplace.json")}
OWNER_URL = re.compile(r"^https://github\.com/SolanceLab/([A-Za-z0-9._-]+)\.git$")
SEMVER = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
MAKE_VAR = re.compile(r"^([ \t]*)([A-Za-z_][A-Za-z0-9_]*)([ \t]*[:?]?=[ \t]*)(v\d+\.\d+\.\d+)([ \t]*)$", re.M)
KNOWN_ROOMS = {"antechamber", "scriptorium", "vault-map", "stack-guard"}  # repos a Makefile may pin


def parse_semver(tag):
    """'v1.2.3' -> (1, 2, 3); anything else (pre-release, no v, branch) -> None."""
    m = SEMVER.match(tag or "")
    return tuple(int(x) for x in m.groups()) if m else None


def latest_tag(tags):
    """Highest strict vX.Y.Z tag, or None."""
    good = [t for t in tags if parse_semver(t)]
    return max(good, key=parse_semver) if good else None


def fetch_tags(repo):
    """All tag names of SolanceLab/<repo>, following GitHub's Link pages."""
    url = "https://api.github.com/repos/SolanceLab/%s/tags?per_page=100" % repo
    headers = {"User-Agent": "solancelab-plugins-bump", "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    tags = []
    while url:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
            tags += [t["name"] for t in json.load(r)]
            link = r.headers.get("Link") or ""
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else None
    return tags


def _norm(path):
    return (path or "").lstrip("./")


def plan_bumps(store_docs, makefile_text, fetch):
    """Return one change dict per entry: status is bumped / current / skipped / error.

    store_docs: {"claude": doc, "codex": doc} (any subset). Nothing is mutated.
    """
    cache = {}

    def newest(repo):
        if repo not in cache:
            try:
                cache[repo] = (latest_tag(fetch(repo)), None)
            except Exception as exc:  # one repo failing must not stop the others
                cache[repo] = (None, "%s: %s" % (type(exc).__name__, str(exc)[:80]))
        return cache[repo]

    def judge(where, name, repo, old):
        tag, err = newest(repo)
        if err:
            return {"status": "error", "where": where, "name": name, "repo": repo, "old": old, "reason": err}
        if tag and parse_semver(tag) > parse_semver(old):
            return {"status": "bumped", "where": where, "name": name, "repo": repo, "old": old, "new": tag}
        return {"status": "current", "where": where, "name": name, "repo": repo, "old": old}

    changes = []
    for key, doc in store_docs.items():
        for p in doc.get("plugins", []):
            src = p.get("source") or {}
            m = OWNER_URL.match(src.get("url") or "")
            if src.get("source") != "git-subdir" or not m:
                changes.append({"status": "skipped", "where": key, "name": p.get("name"), "reason": "not a SolanceLab git-subdir"})
            elif not parse_semver(src.get("ref")):
                changes.append({"status": "skipped", "where": key, "name": p.get("name"), "reason": "no release ref"})
            else:
                c = judge(key, p["name"], m.group(1), src["ref"])
                c["path"] = _norm(src.get("path"))
                changes.append(c)
    for m in MAKE_VAR.finditer(makefile_text or ""):
        short = m.group(2).lower().replace("_", "-")
        if short in KNOWN_ROOMS:
            changes.append(judge("makefile", short, short, m.group(4)))
    return changes


def apply(store_docs, makefile_text, changes):
    """Return (new_docs, new_makefile_text) with the 'bumped' changes written in."""
    docs = copy.deepcopy(store_docs)
    moves = {(c["repo"], c.get("path"), c["old"]): c["new"] for c in changes if c["status"] == "bumped" and c["where"] != "makefile"}
    moved = False
    for key, doc in docs.items():
        for p in doc.get("plugins", []):
            src = p.get("source") or {}
            m = OWNER_URL.match(src.get("url") or "")
            new = m and moves.get((m.group(1), _norm(src.get("path")), src.get("ref")))
            if new:
                src["ref"] = new
                if key == "claude" and "version" in p:
                    p["version"] = new[1:]
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


def describe(c):
    if c["status"] == "bumped":
        return "bumped %s: %s -> %s" % (c["name"], c["old"], c["new"])
    if c["status"] == "current":
        return "up to date %s %s" % (c["name"], c["old"])
    if c["status"] == "skipped":
        return "skipped %s (%s)" % (c["name"], c["reason"])
    return "error %s: %s" % (c["repo"], c["reason"])


def main(argv=None, root=ROOT, fetch=fetch_tags):
    argv = sys.argv[1:] if argv is None else argv
    dry, check = "--dry-run" in argv, "--check" in argv
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
    todo = any(c["status"] == "bumped" for c in changes)
    if any(c["status"] == "error" for c in changes):
        return 2  # a failed lookup must fail the run before anything is written
    if check:
        return 1 if todo else 0
    if todo and not dry:
        new_docs, new_make = apply(docs, make_text, changes)
        for k, doc in new_docs.items():
            with open(paths[k], "w", encoding="utf-8") as fh:
                json.dump(doc, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
        if new_make != make_text:
            with open(make_path, "w", encoding="utf-8") as fh:
                fh.write(new_make)
    return 0


if __name__ == "__main__":
    sys.exit(main())
