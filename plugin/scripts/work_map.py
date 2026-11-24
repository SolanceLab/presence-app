#!/usr/bin/env python3
# work-map — Copyright (c) 2026 House of Solance. PolyForm Noncommercial 1.0.0. Required Notice: Copyright (c) 2026 House of Solance (https://github.com/SolanceLab)
"""work-map: read tagged lines (decisions, pipeline, tasks, ships) and link them into a graph.

Python 3.9+, standard library only. Reads files and git history only; writes nothing.
Run:  python3 work_map.py --config <file> <index|query|open|slice|inventory|why> [--json]
"""
import argparse
import datetime
import glob
import json
import os
import re
import subprocess
import sys

WAITING = re.compile(r"waiting(-on-[a-z0-9][a-z0-9-]*)?")
DEFAULT_WORKBENCH_LIMIT = 3
PLURAL = {"decision": "decisions", "pipeline": "pipeline", "task": "tasks", "ship": "ships", "project": "projects"}
SEP = " · "
ROOT_ACCESS = ("public", "going-public", "house", "none")
NEW_PROJECT_STATUSES = ("workbench", "waiting", "settled")  # these are projects: they need their own PIPELINE
DATE = r"\d{4}-\d{2}-\d{2}"
OPEN_STATUSES = {"idea", "planned", "building", "open", "standing", "waiting", "live", "workbench"}
KINDS = ("decisions", "pipeline", "tasks", "ships")
ROOT_STATUSES = ("workbench", "waiting", "idea", "settled", "dropped")  # old root statuses (live, building, later, closed ...) still read as written


def is_waiting(status):
    """True for "waiting" and "waiting-on-<name>"."""
    return bool(WAITING.fullmatch(status or ""))
LINK_TYPES = ("in-session", "applies-to", "from", "belongs-to", "done-by", "depends-on")


class ConfigError(Exception):
    pass


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def split_fields(text):
    return [f.strip() for f in text.split(SEP) if f.strip()]


def tag(field):
    """('session', 'abc') for 'session: abc', else None."""
    m = re.match(r"^([a-z][a-z ]*?):\s*(.*)$", field)
    return (m.group(1), m.group(2).strip()) if m else None


def csv(value):
    value = value.strip().strip("[]")
    return [v.strip() for v in value.split(",") if v.strip() and v.strip().lower() not in ("none", "unknown")]


def record(kind, id_, source, **kw):
    r = {"kind": kind, "id": id_, "project": "unknown", "session": "unknown",
         "status": "", "date": "", "gist": "", "text": "", "source": source, "links": []}
    r.update(kw)
    return r


def add_link(r, type_, target):
    r["links"].append((type_, target))


# ---- parsers: one per kind, each returns a record or None for a line ----

def parse_decision(line, source):
    m = re.match(r"^\s*-\s+(%s)\b(.*)$" % DATE, line)
    if not m:
        return None
    r = record("decision", "", source, date=m.group(1))
    applies, frm, slug = [], "", ""
    for f in split_fields(m.group(2)):
        t = tag(f)
        if f.lower().startswith("why:"):
            r["why"] = f[4:].strip()
        elif "→" in f:
            who, call = f.split("→", 1)
            r["who"], r["call"] = who.strip(), call.strip()
        elif t and t[0] == "session":
            r["session"] = t[1] or "unknown"
        elif t and t[0] == "applies":
            applies = csv(t[1])
        elif t and t[0] == "from":
            frm = "" if t[1].strip().lower() in ("", "unknown", "none") else t[1]
        elif t and t[0] == "kind":
            r["weight"] = t[1].strip()
        elif not t and re.match(r"^SUPERSEDED by ([a-z0-9-]+)\b", f):  # the mark decisions.py add --supersedes writes
            r["superseded_by"] = re.match(r"^SUPERSEDED by ([a-z0-9-]+)\b", f).group(1)
        elif not slug and not t:
            slug = f
    r["call"] = r.get("call", "")
    r["why"] = r.get("why", "")
    r["slug"] = slugify(slug) if slug else slugify(r["call"])[:40]
    r["id"] = "decision:" + r["slug"]
    r["applies"], r["from"] = applies, frm
    r["project"] = frm or (applies[0] if applies else "unknown")
    r["status"] = "superseded" if r.get("superseded_by") else "standing"
    r["gist"] = r["call"] or r.get("who", "")
    r["text"] = " ".join([r["slug"], r.get("who", ""), r["call"], r["why"]])
    for p in applies:
        add_link(r, "applies-to", "project:" + p)
    if frm:
        add_link(r, "from", "project:" + frm)
    return r


ITEM = re.compile(r"^-\s+\*\*(.+?)\*\*(.*)$")
DETAIL = re.compile(r"^\s+-\s+(.*\S)\s*$")


def scan_items(text):
    """[(line_no, title, rest, details)] for column-0 bold item lines; indented '- ' lines under one are its details."""
    out, cur = [], None
    for n, line in enumerate(text.splitlines(), 1):
        m = ITEM.match(line)
        if m:
            cur = (n, m.group(1).strip(), m.group(2), [])
            out.append(cur)
        elif not line.strip():
            continue
        elif line[0] in " \t":
            d = DETAIL.match(line)
            if d and cur is not None:
                cur[3].append(d.group(1))
        else:
            cur = None  # a heading or any other column-0 line ends the item
    return out


def parse_pipeline_file(text, source_name, default_project="unknown"):
    out = []
    for n, title, rest, details in scan_items(text):
        tags, bare = {}, []
        for f in split_fields(rest):
            t = tag(f)
            if t and t[0] in ("project", "session", "status", "spec", "id", "why", "decisions", "devlog"):
                tags[t[0]] = t[1]
            else:
                bare.append(f)
        project = tags.get("project") or default_project
        item_id = tags.get("id") or slugify(title)
        why = tags.get("why", "")
        decisions = csv(tags.get("decisions", ""))
        r = record("pipeline", "pipeline:%s/%s" % (project, item_id), (source_name, n),
                   project=project, session=tags.get("session") or "unknown",
                   status=tags.get("status") or "unknown", gist=why or " · ".join(bare) or title)
        r["title"], r["spec"], r["why"] = title, tags.get("spec", "none"), why
        r["decisions"], r["devlog"], r["details"] = decisions, tags.get("devlog", ""), details
        r["text"] = " ".join([title, why] + bare + details)
        if project != "unknown":
            add_link(r, "belongs-to", "project:" + project)
        for d in decisions:
            add_link(r, "depends-on", "decision:" + slugify(d))
        out.append(r)
    return out


def parse_map_file(text, source_name):
    out = []
    for n, name, rest, details in scan_items(text):
        tags = {}
        for f in split_fields(rest):
            t = tag(f)
            if t and t[0] in ("id", "status", "access", "aka", "why", "pipeline", "spec"):
                tags[t[0]] = t[1]
        pid = tags.get("id") or slugify(name)
        why = tags.get("why", "")
        r = record("project", "project:" + pid, (source_name, n), project=pid,
                   status=tags.get("status") or "unknown", gist=why or name)
        r["title"], r["why"], r["aka"], r["details"] = name, why, csv(tags.get("aka", "")), details
        for k in ("pipeline", "spec", "access"):
            if k in tags:
                r[k] = tags[k]  # a path, or "none" (access: one of ROOT_ACCESS)
        r["text"] = " ".join([name, why] + r["aka"] + details)
        out.append(r)
    return out


def root_problems(roots, base, limit):
    """Problems in root (map) lines. roots: dicts with id, status, pipeline, spec (the last two may be missing)."""
    out = []
    bench = [r["id"] for r in roots if r["status"] == "workbench"]
    if len(bench) > limit:
        out.append({"type": "workbench-over-limit", "limit": limit, "ids": bench})
    for r in roots:
        st, pl, sp = r["status"], r.get("pipeline"), r.get("spec")
        if (st in NEW_PROJECT_STATUSES and (not pl or pl == "none")) or (st == "idea" and not pl and not sp):
            out.append({"type": "pointer-missing", "id": r["id"], "status": st})
        if st in ROOT_STATUSES:  # a line with an old status is not asked for access
            ac = r.get("access")
            if ac is None:
                out.append({"type": "access-missing", "id": r["id"], "status": st})
            elif ac not in ROOT_ACCESS:
                out.append({"type": "access-invalid", "id": r["id"], "status": st, "access": ac})
        for field, path in (("pipeline", pl), ("spec", sp)):
            if path and path != "none" and not os.path.exists(path if os.path.isabs(path) else os.path.join(base, path)):
                out.append({"type": "pointer-target-missing", "id": r["id"], "field": field, "path": path})
    return out


def config_workbench_limit(path):
    """The config's workbench_limit (int, default 3); a value that is not a whole number above 0 is a ConfigError."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read().decode("utf-8")
        if path.endswith(".toml"):
            import tomllib  # Python 3.11+
            cfg = tomllib.loads(raw)
        else:
            cfg = json.loads(raw)
    except Exception:
        return DEFAULT_WORKBENCH_LIMIT  # load_config already reports an unreadable config
    v = cfg.get("workbench_limit", DEFAULT_WORKBENCH_LIMIT) if isinstance(cfg, dict) else DEFAULT_WORKBENCH_LIMIT
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        raise ConfigError("config key 'workbench_limit' must be a whole number of 1 or more")
    return v


YES_LINE = re.compile(r'^\s*-\s+\d{4}-\d{2}-\d{2} · session: [^·]+ · project: [^·]+ · publish-yes \S+ \S+ · yes: ')


def is_yes_line(text):
    """A publish yes DEVLOG line (the yes record kind): an approval, never a ship and never shown by why."""
    return bool(YES_LINE.search(text))


def parse_ship(line, source):
    m = re.match(r"^\s*(?:-\s+)?(%s)\b(.*)$" % DATE, line)
    if not m or not re.search(r"(^|·)\s*shipped\b", m.group(2)):
        return None
    if is_yes_line(line):
        return None
    r = record("ship", "", source, date=m.group(1), status="shipped")
    decisions, tasks, repo, version, sha = [], [], "unknown", "", ""
    for f in split_fields(m.group(2)):
        t = tag(f)
        if f.startswith("shipped"):
            toks = f.split()[1:]
            if len(toks) >= 2:
                version, sha = toks[0], toks[1]
            elif len(toks) == 1:
                if re.fullmatch(r"[0-9a-f]{7,40}", toks[0]):
                    sha = toks[0]
                else:
                    version = toks[0]
        elif t and t[0] == "session":
            r["session"] = t[1] or "unknown"
        elif t and t[0] == "project":
            repo = t[1] or "unknown"
        elif t and t[0] == "decisions":
            decisions = csv(t[1])
        elif t and t[0] == "tasks closed":
            tasks = csv(t[1])
    ref = version or sha or "unknown"
    r["id"] = "ship:%s@%s" % (repo, ref)
    r["project"] = repo
    r["version"], r["sha"] = version, sha
    r["gist"] = ("shipped %s %s" % (version, sha)).strip()
    r["text"] = " ".join([r["gist"], " ".join(decisions), " ".join(tasks)])
    for d in decisions:
        add_link(r, "depends-on", "decision:" + slugify(d))
    for k in tasks:
        add_link(r, "done-by", "task:" + k)
    return r


LINE_PARSERS = {"decisions": parse_decision, "ships": parse_ship}


def parse_tasks(text, source_name):
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("tasks", data.get("items", []))
    if not isinstance(data, list):
        raise ValueError("expected a JSON list of task objects")
    out = []
    pos = 0  # search from the previous match so duplicate ids get their own lines
    for obj in data:
        if not isinstance(obj, dict) or "id" not in obj or "title" not in obj:
            continue
        tid = str(obj["id"])
        decs = obj.get("decisions") or []
        if not isinstance(decs, list):
            raise ValueError("task %s: 'decisions' must be a list" % tid)
        m = re.compile(r'"id"\s*:\s*"?%s"?\s*[,}\n]' % re.escape(tid)).search(text, pos)
        if m:
            pos = m.end()
        line = text.count("\n", 0, m.start()) + 1 if m else 1
        project = str(obj.get("project") or "unknown")
        r = record("task", "task:" + tid, (source_name, line), project=project,
                   session=str(obj.get("session") or "unknown"),
                   status=str(obj.get("status") or "open"), gist=str(obj["title"]),
                   text=str(obj["title"]), date=str(obj.get("date") or ""))
        if project != "unknown":
            add_link(r, "belongs-to", "project:" + project)
        for d in decs:
            add_link(r, "depends-on", "decision:" + slugify(str(d)))
        out.append(r)
    return out


# ---- config and loading ----

def load_config(path):
    if not path:
        raise ConfigError("no config: pass --config <file> or set WORK_MAP_CONFIG")
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as e:
        raise ConfigError("cannot read config %s: %s" % (path, e.strerror))
    try:
        if path.endswith(".toml"):
            import tomllib  # Python 3.11+
            cfg = tomllib.loads(raw.decode("utf-8"))
        else:
            cfg = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise ConfigError("cannot parse config %s: %s" % (path, e))
    if not isinstance(cfg, dict):
        raise ConfigError("config must be an object with keys: " + ", ".join(KINDS + ("map",)))
    sources = {}
    for k in KINDS + ("map",):
        v = cfg.get(k, [])
        if isinstance(v, str):
            v = [v]
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise ConfigError("config key %r must be a list of file paths or globs" % k)
        sources[k] = v
    if not any(sources.values()):
        raise ConfigError("config lists no sources (keys: %s)" % ", ".join(KINDS + ("map",)))
    return sources, os.path.dirname(os.path.abspath(path))


def load_all(sources, base):
    records, files, excluded = [], [], []
    for kind in KINDS + ("map",):
        for pattern in sources.get(kind, []):
            pat = pattern if os.path.isabs(pattern) else os.path.join(base, pattern)
            paths = sorted(glob.glob(pat, recursive=True))
            if not paths:
                excluded.append({"file": pattern, "kind": kind, "reason": "no file matches"})
            for p in paths:
                name = os.path.relpath(p, base)
                if os.path.isdir(p):
                    excluded.append({"file": name, "kind": kind, "reason": "is a folder"})
                    continue
                try:
                    with open(p, encoding="utf-8") as fh:
                        text = fh.read()
                except (OSError, UnicodeDecodeError) as e:
                    why = "not readable text" if isinstance(e, UnicodeDecodeError) else e.strerror
                    excluded.append({"file": name, "kind": kind, "reason": why})
                    continue
                try:
                    if kind == "tasks":
                        recs = parse_tasks(text, name)
                    elif kind == "map":
                        recs = parse_map_file(text, name)
                    elif kind == "pipeline":
                        # shortcut: folder name is the project only for files below the config folder (the config
                        # folder's own PIPELINE.md stays "unknown"); upgrade: a config key naming the root file
                        parent = os.path.dirname(os.path.abspath(p))
                        folder = os.path.basename(parent) if parent != os.path.abspath(base) else "unknown"
                        recs = parse_pipeline_file(text, name, folder)
                    else:
                        recs = []
                        for n, line in enumerate(text.splitlines(), 1):
                            r = LINE_PARSERS[kind](line, (name, n))
                            if r:
                                recs.append(r)
                except ValueError as e:  # includes JSON decode errors
                    excluded.append({"file": name, "kind": kind, "reason": "bad content: %s" % e})
                    continue
                records.extend(recs)
                files.append({"file": name, "kind": kind, "indexed": len(recs)})
    return records, files, excluded


# ---- graph ----

def build_graph(records):
    for i, r in enumerate(records):
        r["seq"] = i
    # an old project name (aka) resolves to the project's id; the first claim on a name wins
    alias_of, problems = {}, []
    project_ids = {r["id"] for r in records if r["kind"] == "project"}
    for r in records:
        for a in r["aka"] if r["kind"] == "project" else []:
            if "project:" + a in project_ids:
                continue
            if alias_of.get(a, r["id"]) != r["id"]:
                problems.append({"type": "alias-collision", "alias": a, "kept": alias_of[a], "also-claimed-by": r["id"]})
            else:
                alias_of[a] = r["id"]
    for r in records:
        fixed = []
        for t, x in r["links"]:
            if x.startswith("project:") and x[8:] in alias_of:
                x = alias_of[x[8:]]  # alias_of holds the full project id
            fixed.append((t, x))
        r["links"] = fixed
        # slice filters on project/applies names, so an old name resolves there too
        canon = lambda n: alias_of[n][8:] if n in alias_of else n
        if r["kind"] == "pipeline" and canon(r["project"]) != r["project"]:
            r["id"] = "pipeline:%s/%s" % (canon(r["project"]), r["id"].split("/", 1)[1])  # id follows the canonical project
        r["project"] = canon(r["project"])
        r["applies"] = [canon(n) for n in r.get("applies", [])]
    nodes = {}
    for r in records:
        nodes.setdefault(r["id"], []).append(r)
        if r["session"] != "unknown":
            add_link(r, "in-session", "session:" + r["session"])
    # project/session nodes exist because a tag names them
    implicit = set()
    for r in records:
        for _, target in r["links"]:
            if target.startswith(("project:", "session:")):
                implicit.add(target)
    inbound = {}
    unresolved_by_file = {}
    for r in records:
        resolved = []
        for type_, target in r["links"]:
            if target not in nodes and target not in implicit:
                resolved.append((type_, "unresolved:" + target))
                key = r["source"][0]
                unresolved_by_file[key] = unresolved_by_file.get(key, 0) + 1
            else:
                resolved.append((type_, target))
                inbound.setdefault(target, []).append((type_, r["id"]))
        r["links"] = resolved
    collisions = {i: len(v) for i, v in nodes.items() if len(v) > 1}
    return nodes, implicit, inbound, collisions, unresolved_by_file, problems


# ---- output ----

def links_text(r):
    groups = {}
    for type_, target in r["links"]:
        groups.setdefault(type_, []).append(target)
    parts = ["%s=%s" % (t, ",".join(groups[t][:5])) for t in LINK_TYPES if t in groups]
    return "; ".join(parts) or "none"


def public(r, full=False):
    d = {k: r[k] for k in ("kind", "id", "project", "session", "status", "date", "gist")}
    d["source"] = {"file": r["source"][0], "line": r["source"][1]}
    if r.get("superseded_by"):
        d["superseded_by"] = r["superseded_by"]
    links = {}
    for type_, target in r["links"]:
        links.setdefault(type_, []).append(target)
    d["links"] = links if full else {t: v[:5] for t, v in links.items()}
    if full:
        d.update({k: r[k] for k in ("title", "why", "access", "pipeline", "spec", "decisions", "devlog", "aka", "details") if r.get(k)})
    return d


def one_line(r):
    gist = r["gist"] if len(r["gist"]) <= 80 else r["gist"][:77] + "..."
    return "%s %s · %s · %s · %s · links: %s · source: %s:L%d" % (
        r["kind"], r["id"], r["project"], r["status"] if r["kind"] != "decision" else (r["date"] or r["status"]) + (" superseded" if r["status"] == "superseded" else ""),
        gist, links_text(r), r["source"][0], r["source"][1])


def emit(args, payload, lines):
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("\n".join(lines))


def counts(records):
    c = {k: 0 for k in ("decision", "pipeline", "task", "ship", "project")}
    for r in records:
        c[r["kind"]] += 1
    return c


# ---- commands ----

def cmd_index(args, g):
    records, files, excluded, graph = g
    c = counts(records)
    payload = {"counts": c, "total": len(records), "files": len(files), "excluded": len(excluded)}
    emit(args, payload, ["%s: %d" % (PLURAL[k], v) for k, v in c.items()] +
         ["total: %d from %d files (%d excluded)" % (len(records), len(files), len(excluded))])


def cmd_query(args, g):
    records = g[0]
    words = [w.lower() for w in args.text.split()]
    hits = []
    for r in records:
        hay = " ".join([r["id"], r["project"], r["session"], r["gist"], r["text"]]).lower()
        if all(w in hay for w in words):
            hits.append(r)
    emit(args, [public(r) for r in hits], [one_line(r) for r in hits] or ["no match"])


def canonical_name(records, name):
    """An old project name (aka) given on the command line means the project's id; first claim wins, as in build_graph."""
    if any(r["kind"] == "project" and r["id"] == "project:" + name for r in records):
        return name  # a real id is never an alias
    for r in records:
        if r["kind"] == "project" and name in r.get("aka", []):
            return r["id"][8:]
    return name


def cmd_open(args, g):
    records, graph = g[0], g[3]
    if args.id.startswith("project:"):
        args.id = "project:" + canonical_name(records, args.id[8:])
    nodes, implicit, inbound = graph[0], graph[1], graph[2]
    items = [r for r in records if r["id"] == args.id]
    if not items and args.id not in implicit:
        emit(args, {"id": args.id, "found": False}, ["not found: " + args.id])
        return 1
    refs = [{"type": t, "from": i} for t, i in inbound.get(args.id, [])]
    payload = {"id": args.id, "found": True, "items": [public(r, True) for r in items],
               "linked-from": refs}
    members = [nodes[i][0] for t, i in inbound.get(args.id, []) if t == "belongs-to" and i.startswith("pipeline:")]
    if args.id.startswith("project:"):
        payload["project-items"] = [{"id": m["id"], "title": m["title"], "status": m["status"]} for m in members]
    lines = []
    for r in items:
        lines += ["%s %s" % (r["kind"], r["id"]),
                  "  project: %s · session: %s · status: %s · date: %s" % (
                      r["project"], r["session"], r["status"], r["date"] or "-"),
                  "  text: %s" % r["gist"]]
        for k in ("who", "call", "why", "access", "pipeline", "spec", "devlog"):
            if r.get(k) and not (k == "spec" and r[k] == "none"):
                lines.append("  %s: %s" % (k, r[k]))
        if r.get("aka"):
            lines.append("  aka: %s" % ", ".join(r["aka"]))
        if r.get("decisions"):
            lines.append("  decisions: %s" % ", ".join(r["decisions"]))
        for d in r.get("details", []):
            lines.append("  detail: %s" % d)
        for type_, target in r["links"]:
            lines.append("  %s -> %s" % (type_, target))
        lines.append("  source: %s:L%d" % r["source"])
    if not items:
        lines.append("%s (named by tags only)" % args.id)
    for m in members if args.id.startswith("project:") else []:
        lines.append("  item: %s · %s · %s" % (m["id"], m["title"], m["status"]))
    for t, i in inbound.get(args.id, []):
        lines.append("  linked-from: %s (%s)" % (i, t))
    emit(args, payload, lines)
    return 0


def applies_to(r, project, house):
    if house:
        return "house" in r.get("applies", []) or r["project"] == "house"
    return r["project"] == project or project in r.get("applies", []) or "house" in r.get("applies", [])


def cmd_slice(args, g):
    records = g[0]
    if not args.house and not args.project:
        print("slice needs --project <name> or --house", file=sys.stderr)
        return 2
    if args.project:
        args.project = canonical_name(records, args.project)
    # House slices retain their original filtering, ordering, and limit semantics.
    if args.house:
        out = []
        for r in records:
            if not applies_to(r, args.project, True):
                continue
            if args.status == "open" and not (r["status"] in OPEN_STATUSES or is_waiting(r["status"])):
                continue
            if args.status not in ("open", "any") and r["status"] != args.status:
                continue
            out.append(r)
        out.sort(key=lambda r: (r["date"], r["seq"]), reverse=True)
        out = out[:args.limit]
        emit(args, [public(r) for r in out], [one_line(r) for r in out] or ["nothing open"])
        return 0

    def status_matches(r):
        if args.status == "open":
            return (r["status"] in OPEN_STATUSES or is_waiting(r["status"]))
        return args.status == "any" or r["status"] == args.status

    def newest(items):
        return sorted(items, key=lambda r: (r["date"], r["seq"]), reverse=True)

    own = [r for r in records
           if r["project"] == args.project or args.project in r.get("applies", [])]
    house = [r for r in records
             if r not in own
             and (r.get("applies", []) == ["house"] or r["project"] == "house")]

    eligible = [r for r in own if status_matches(r) and r["kind"] != "ship"]
    urgent = [r for r in eligible
              if r["kind"] in ("pipeline", "task")
              and (r["status"] == "building" or is_waiting(r["status"]))]
    other_tasks = [r for r in eligible
                   if r["kind"] == "task"
                   and not (r["status"] == "building" or is_waiting(r["status"]))]
    planned = [r for r in eligible if r["kind"] == "pipeline" and r["status"] == "planned"]
    banded = ("building", "planned", "idea", "parked")
    other_open = [r for r in eligible if r["kind"] == "pipeline"
                  and r["status"] not in banded and not is_waiting(r["status"])]
    deferred = [r for r in eligible
                if args.status == "any" and r["kind"] == "pipeline"
                and r["status"] in ("idea", "parked")]
    decisions = [r for r in eligible if r["kind"] == "decision"]
    out = (newest(urgent) + newest(other_tasks) + newest(planned) + newest(other_open)
           + newest(deferred) + newest(decisions))[:args.limit]
    # the project's own map line opens the slice (status live/building, its why)
    out = [r for r in records if r["kind"] == "project" and r["id"] == "project:" + args.project][:1] + out

    ships = newest([r for r in own if r["kind"] == "ship" and r["project"] == args.project])
    if ships:
        out.append(ships[0])
    # House-wide context is standing calls only: a one-time decision is done and wakes nobody
    out.extend(newest([r for r in house if status_matches(r) and r.get("weight") != "one-time"])[:args.house_limit])
    emit(args, [public(r) for r in out], [one_line(r) for r in out] or ["nothing open"])
    return 0


def problem_line(p):
    if p["type"] == "alias-collision":
        return "%s: %s (kept %s, also claimed by %s)" % (p["type"], p["alias"], p["kept"], p["also-claimed-by"])
    if p["type"] == "workbench-over-limit":
        return "%s: %d on the workbench, limit %d (%s)" % (p["type"], len(p["ids"]), p["limit"], ", ".join(p["ids"]))
    if p["type"] == "pointer-target-missing":
        return "%s: %s %s: %s" % (p["type"], p["id"], p["field"], p["path"])
    if p["type"] == "access-invalid":
        return "%s: %s access %s (status %s)" % (p["type"], p["id"], p["access"], p["status"])
    return "%s: %s (status %s)" % (p["type"], p["id"], p["status"])


def cmd_inventory(args, g):
    records, files, excluded, graph = g
    collisions, unresolved_by_file, problems = graph[3], graph[4], list(graph[5])
    roots = [dict(r, id=r["project"]) for r in records if r["kind"] == "project"]
    problems += root_problems(roots, args.base, args.workbench_limit)
    per_file = [dict(f, unresolved=unresolved_by_file.get(f["file"], 0)) for f in files]
    payload = {"counts": counts(records), "files": per_file, "collisions": collisions,
               "unresolved": sum(unresolved_by_file.values()), "problems": problems, "excluded": excluded}
    lines = ["%s: %d indexed" % (PLURAL[k], v) for k, v in counts(records).items()]
    for f in per_file:
        lines.append("file %s (%s): indexed %d, unresolved links %d" % (
            f["file"], f["kind"], f["indexed"], f["unresolved"]))
    lines.append("unresolved links: %d" % payload["unresolved"])
    lines.append("collisions: %d" % len(collisions) + "".join(
        "\n  %s (%d records)" % (i, n) for i, n in sorted(collisions.items())))
    lines.append("problems: %d" % len(problems) + "".join("\n  " + problem_line(p) for p in problems))
    lines.append("excluded: %d" % len(excluded) + "".join(
        "\n  %s (%s): %s" % (e["file"], e["kind"], e["reason"]) for e in excluded))
    emit(args, payload, lines)
    return 0


# ---- why: commit -> work item -> decisions ----

NOTES_REF = "refs/notes/work-map"
APPROVAL = "publish-yes"
GIT_FMT = ("%H%x1f%ad%x1f%s%x1f%(trailers:key=Work,valueonly,separator=%x2C)"
           "%x1f%(trailers:key=Session,valueonly,separator=%x2C)"
           "%x1f%(trailers:key=Decision,valueonly,separator=%x2C)%x1f%N%x1e")
NOTES_ARGS = ["--no-notes", "--notes=" + NOTES_REF]  # only the work-map notes, never other note refs


class GitError(Exception):
    """git refused or is missing: why exits 2."""


def git(cwd, *args):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_PAGER="cat", LC_ALL="C")
    try:
        proc = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env)
    except FileNotFoundError:
        raise GitError("git is not installed")
    if proc.returncode != 0:
        raise GitError((proc.stderr.strip().splitlines() or ["git failed"])[-1])
    return proc.stdout


def split_trailer(value):
    """git joins repeated trailers with the separator: 'a,b, c' -> ['a', 'b', 'c'], first-seen order, no repeats."""
    out = []
    for part in value.split(","):
        part = part.strip()
        if part and part not in out:
            out.append(part)
    return out


def is_approval(slug):
    """An approval (publish-yes...) is a yes, not a reason: why never shows it."""
    return slugify(slug).startswith(APPROVAL)


def parse_note(text):
    """A local git note: lines 'Work: a, b', 'Session: x', 'Decision: y' (keys in any case); other lines ignored."""
    got = {"work": [], "session": [], "decision": []}
    for line in text.splitlines():
        key, sep, val = line.partition(":")
        key = key.strip().lower()
        if sep and key in got:
            for v in split_trailer(val):
                if v not in got[key]:
                    got[key].append(v)
    return got


def merge_unique(first, second):
    return first + [v for v in second if v not in first]


def parse_log(out):
    commits = []
    for chunk in out.split("\x1e"):
        chunk = chunk.strip("\n")
        if not chunk:
            continue
        parts = chunk.split("\x1f")
        parts += [""] * (7 - len(parts))
        note = parse_note(parts[6])
        commits.append({"sha": parts[0].strip(), "date": parts[1], "subject": parts[2],
                        "work": merge_unique(split_trailer(parts[3]), note["work"]),
                        "session": (split_trailer(parts[4]) or note["session"] or [""])[0],
                        "decision": merge_unique(split_trailer(parts[5]), note["decision"])})
    return commits


def resolve_target(target, limit):
    """(commits newest first, note). GitError means exit 2; an empty list means exit 1 (note says why, or "")."""
    fmt = "--format=" + GIT_FMT
    if os.path.isfile(target):
        p = os.path.abspath(target)
        return parse_log(git(os.path.dirname(p), "log", "--follow", "--date=short", *NOTES_ARGS, fmt,
                             "-n", str(limit), "--", os.path.basename(p))), ""
    m = re.fullmatch(r"(.+):(\d+)", target)
    if m and os.path.isfile(m.group(1)):
        n = int(m.group(2))
        if n < 1:
            raise GitError("line numbers start at 1")
        p = os.path.abspath(m.group(1))
        d, name = os.path.dirname(p), os.path.basename(p)
        out = git(d, "blame", "-L", "%d,%d" % (n, n), "--porcelain", "--", name)
        toks = out.split()
        sha = toks[0] if toks else ""
        if not sha or set(sha) == {"0"}:
            return [], "line %d of %s is not committed yet" % (n, m.group(1))
        return parse_log(git(d, "log", "-1", "--date=short", *NOTES_ARGS, fmt, sha)), ""
    if os.path.isdir(target):
        raise GitError("why needs a commit, a file or file:LINE, not a folder: " + target)
    cwd = os.getcwd()
    try:
        sha = git(cwd, "rev-parse", "--verify", "--quiet", "--end-of-options", target + "^{commit}").strip()
    except GitError:
        raise GitError("not a commit or a file: " + target)
    if not sha:
        raise GitError("not a commit or a file: " + target)
    return parse_log(git(cwd, "log", "-1", "--date=short", *NOTES_ARGS, fmt, sha)), ""


def find_items(records, work_id):
    """Every pipeline record a Work id matches; the caller decides what several matches mean."""
    wid = work_id[len("pipeline:"):] if work_id.startswith("pipeline:") else work_id
    items = [r for r in records if r.get("kind") == "pipeline"]
    if "/" in wid:
        proj, iid = wid.split("/", 1)
        full = "pipeline:%s/%s" % (canonical_name(records, proj), iid)
        hits = [r for r in items if r["id"] == full]
    else:
        hits = [r for r in items if r["id"].split("/", 1)[-1] == wid]
    out, seen = [], set()
    for r in hits:  # the same item listed in two files is one work item
        if r["id"] not in seen:
            seen.add(r["id"])
            out.append(r)
    return out


def find_decision(records, slug):
    s = slugify(slug)
    hits = [r for r in records if r.get("kind") == "decision" and r.get("slug") == s]
    return next((r for r in hits if r.get("status") != "superseded"), hits[0] if hits else None)


def decision_view(records, slug):
    dec = find_decision(records, slug)
    return {"id": "decision:" + slugify(slug), "found": dec is not None,
            "call": dec.get("call", "") if dec else "", "why": dec.get("why", "") if dec else ""}


def work_chain(records, work_id):
    chain = {"id": work_id, "found": False, "title": "", "status": "", "why": "", "spec": "",
             "decisions": [], "record": None, "session": "", "ambiguous": [], "source": "", "devlog": ""}
    hits = find_items(records, work_id)
    if len(hits) > 1:
        chain["ambiguous"] = [h["id"] for h in hits]
    elif hits:
        r = hits[0]
        chain.update(found=True, title=r.get("title", ""), status=r.get("status", ""), why=r.get("why", ""),
                     spec="" if r.get("spec", "none") in ("none", "") else r["spec"], record=r["id"],
                     session="" if r.get("session", "unknown") == "unknown" else r["session"])
        chain["source"], chain["devlog"] = r["source"][0], r.get("devlog", "")
        chain["decisions"] = [decision_view(records, d) for d in r.get("decisions", []) if not is_approval(d)]
    return chain


def devlog_mentions(files, base, sha, limit=3):
    """Lines of the DEVLOG files that name this commit by exactly its 7-char or its full sha."""
    pat = re.compile(r"(?<![0-9a-fA-F])(?:%s|%s)(?![0-9a-fA-F])" % (re.escape(sha), re.escape(sha[:7])), re.I)
    hits = []
    for f in files:
        if f["kind"] != "ships":
            continue
        try:
            with open(os.path.join(base, f["file"]), encoding="utf-8", errors="replace") as fh:
                for n, line in enumerate(fh, 1):
                    if pat.search(line) and not is_yes_line(line):
                        hits.append(dict(source=f["file"], line=n, text=line.strip()[:300]))
                        if len(hits) >= limit:
                            return hits
        except OSError:
            continue
    return hits


_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december")


def devlog_day_lines(files, base, source, day, limit=3):
    """Lines dated `day` (YYYY-MM-DD) in the DEVLOG.md that sits in the same folder as the PIPELINE file `source`."""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", day or "")
    if not m or not source:
        return []
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        datetime.date.fromisoformat(day)
    except ValueError:
        return []
    folder = os.path.dirname(os.path.abspath(os.path.join(base, source)))
    head = re.compile(r"^##\s+0?%d\s+(%s|%s)\s+%d\s*$" % (d, _MONTHS[mo - 1], _MONTHS[mo - 1][:3], y), re.I)
    dated = re.compile(r"^(?:-\s+)?%s(?!\d)" % re.escape(day))
    hits = []
    for f in files:
        if f["kind"] != "ships" or os.path.basename(f["file"]) != "DEVLOG.md":
            continue
        path = os.path.abspath(os.path.join(base, f["file"]))
        if os.path.dirname(path) != folder:
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                under = False
                for n, line in enumerate(fh, 1):
                    t = line.strip()
                    if t.startswith("## "):
                        under = bool(head.match(t))
                        continue
                    if t and (dated.match(t) or under) and not is_yes_line(t):
                        hits.append(dict(source=f["file"], line=n, text=t[:300]))
                        if len(hits) >= limit:
                            return hits
        except OSError:
            continue
    return hits


def cmd_why(args, g):
    records = g[0]
    if args.limit < 1:
        print("work_map: why: --limit must be 1 or more", file=sys.stderr)
        return 2
    try:
        commits, note = resolve_target(args.target, args.limit)
    except GitError as e:
        print("work_map: why: %s" % e, file=sys.stderr)
        return 2
    if not commits:
        emit(args, [], [note or "no commits found for " + args.target])
        return 1
    base = getattr(args, "base", ".")
    payload, lines, shown, bare = [], [], set(), 0
    for c in commits:
        direct = [d for d in c["decision"] if not is_approval(d)]
        # the DEVLOG is the owner's record of why it was done this way: read it for every commit, show it first
        devlog = devlog_mentions(g[1], base, c["sha"])
        if not c["work"] and not direct and not devlog:
            bare += 1
            continue
        chains = [work_chain(records, w) for w in c["work"]]
        for h in devlog:
            h["via"] = "sha"
        seen_hits = {(h["source"], h["line"]) for h in devlog}
        for ch in chains:
            if ch["found"] and ch["devlog"]:
                for h in devlog_day_lines(g[1], base, ch["source"], ch["devlog"]):
                    if (h["source"], h["line"]) not in seen_hits:
                        seen_hits.add((h["source"], h["line"]))
                        h["via"] = "work item " + ch["record"]
                        devlog.append(h)
        decs = [decision_view(records, d) for d in direct]
        session = c["session"] or next((ch["session"] for ch in chains if ch["session"]), "")
        works = []
        for ch in chains:
            w = dict(id=ch["id"], found=ch["found"], title=ch["title"], status=ch["status"], why=ch["why"],
                     spec=ch["spec"], decisions=[dict(id=d["id"], call=d["call"], why=d["why"]) for d in ch["decisions"]])
            if ch["ambiguous"]:
                w["ambiguous"] = ch["ambiguous"]
            works.append(w)
        payload.append(dict(commit=c["sha"], date=c["date"], subject=c["subject"], work=works,
                            decisions=[dict(id=d["id"], found=d["found"], call=d["call"], why=d["why"]) for d in decs],
                            session=session or None, devlog=devlog))
        lines.append("commit %s · %s · %s" % (c["sha"][:7], c["date"], c["subject"]))
        for h in devlog:
            tag = "devlog" if h["via"] == "sha" else "devlog (%s)" % h["via"]
            lines.append("  %s: %s:L%d · %s" % (tag, h["source"], h["line"], h["text"]))
        for d in decs:
            lines += decision_lines(d, "  ")
        for ch in chains:
            if ch["ambiguous"]:
                lines.append("  work: %s (ambiguous: %s; write <project>/<id>)" % (ch["id"], ", ".join(ch["ambiguous"])))
            elif not ch["found"]:
                lines.append("  work: %s (not in the record)" % ch["id"])
            elif ch["record"] in shown:
                lines.append("  work: %s (above)" % ch["id"])
            else:
                shown.add(ch["record"])
                lines.append("  %s · %s · %s" % (ch["record"], ch["title"], ch["status"]))
                if ch["why"]:
                    lines.append("    why: " + ch["why"])
                for d in ch["decisions"]:
                    lines += decision_lines(d, "    ", "")
                if ch["spec"]:
                    lines.append("    spec: " + ch["spec"])
        if session:
            lines.append("  session: " + session)
    if bare:
        lines.append("%d commits without a Work line or DEVLOG mention" % bare)
    emit(args, payload, lines)
    return 0


def decision_lines(d, indent, label="decision: "):
    if not d["found"]:
        return ["%s%s%s (not in the record)" % (indent, label, d["id"][len("decision:"):] if label else d["id"])]
    name = d["id"][len("decision:"):] if label else d["id"]
    out = ["%s%s%s · %s" % (indent, label, name, d["call"])]
    if d["why"]:
        out.append("%s  why: %s" % (indent, d["why"]))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="work_map", description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=os.environ.get("WORK_MAP_CONFIG"),
                    help="JSON or TOML file listing sources by kind (or set WORK_MAP_CONFIG)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--json", action="store_true", help="print JSON")
    sub.add_parser("index", parents=[shared], help="parse all sources, print counts")
    q = sub.add_parser("query", parents=[shared], help="find items by id, project or words")
    q.add_argument("text")
    o = sub.add_parser("open", parents=[shared], help="one item with all its links")
    o.add_argument("id")
    s = sub.add_parser("slice", parents=[shared], help="newest open items for a lean session start")
    s.add_argument("--project")
    s.add_argument("--house", action="store_true")
    s.add_argument("--status", default="open", help="open (default), any, or an exact status")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--house-limit", type=int, default=3,
                   help="house-wide records appended to a project slice (default: 3; 0 disables)")
    sub.add_parser("inventory", parents=[shared], help="counts per kind and file, problems")
    w = sub.add_parser("why", parents=[shared], help="from a commit, file or file:LINE back to the reasons it exists")
    w.add_argument("target")
    w.add_argument("--limit", type=int, default=20, help="commits read for a file (default 20)")
    args = ap.parse_args(argv)
    try:
        sources, base = load_config(args.config)
        args.base, args.workbench_limit = base, config_workbench_limit(args.config)
    except ConfigError as e:
        print("work_map: %s" % e, file=sys.stderr)
        return 2
    args.base = base
    records, files, excluded = load_all(sources, base)
    g = (records, files, excluded, build_graph(records))
    return {"index": cmd_index, "query": cmd_query, "open": cmd_open,
            "slice": cmd_slice, "inventory": cmd_inventory, "why": cmd_why}[args.cmd](args, g) or 0


if __name__ == "__main__":
    sys.exit(main())
