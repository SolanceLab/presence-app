#!/usr/bin/env python3
# work-map — Copyright (c) 2026 House of Solance. PolyForm Noncommercial 1.0.0. Required Notice: Copyright (c) 2026 House of Solance (https://github.com/SolanceLab)
"""pipeline.py add|update|check — the writer for project PIPELINE.md item lines (the shape work_map.py reads).

Refuses bad input in one line, supports --dry-run, writes, parses the written line back, and restores
the file byte-for-byte on any failure. Python 3.9+, standard library only.
  add    --project ID --item T --id SLUG --status S --why W [--spec P] [--decisions a,b]
         [--worker NAME] [--detail L]... [--file P] [--config C] [--decisions-file P]... [--dry-run]
  update (--file P | --project ID) --id SLUG [--status S] [--devlog YYYY-MM-DD] [--add-detail L] [--config C]
  check  [--config C] FILE...      (item lines, and root lines of a map file)
  root add    --name N --id ID --access A --status S --why W [--aka a,b] [--pipeline PATH | --spec PATH]
              [--file P] [--config C] [--dry-run]
  root update --id ID [--access A] [--status S] [--pipeline PATH] [--spec PATH] [--why W] [--aka a,b] [--add-detail L]... [--file P] [--config C] [--dry-run]
Root lines (the map file, one per project or idea) carry two tags.
  access: public (others have it), going-public (private now, meant for the public), house (ours only), none (not built).
  status: workbench (at most the config's "workbench_limit", default 3), waiting (known work, not on the bench),
          idea (not started), settled (finished, nothing open), dropped.
workbench, waiting and settled need a pipeline pointer ("none" is not enough); an idea needs a spec or pipeline
pointer ("none" when it has none); dropped needs no pointer. A line still carrying an old status (live, building,
later, closed, planned, parked) or no access tag stays readable and is held only to the pointer-path rules.
Status: idea, planned, building, waiting, waiting-on-<name>, parked, done, dropped.
Paths: --config, else $WORK_MAP_CONFIG, else ./work-map.json (its "pipeline", "map" and "decisions"
lists; globs allowed, relative paths read from the config's folder). Without a config, pass --file.
"""
import argparse, contextlib, datetime, glob, hashlib, json, os, re, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the shared lock sits beside this script
import _writelock
import work_map  # the one place the root-line rules live (root_problems)
from _writelock import locked, _private_lock_dir, confined
fcntl = _writelock.fcntl

WAITING = re.compile(r"waiting(-on-[a-z0-9][a-z0-9-]*)?")
FIXED = {"idea": "Later", "planned": "Next", "building": "Now", "parked": "Later", "done": "Done", "dropped": "Done"}
STATUSES = ["idea", "planned", "building", "waiting", "waiting-on-<name>", "parked", "done", "dropped"]


def status_ok(status):
    return status in FIXED or bool(WAITING.fullmatch(status or ""))


def section_of(status):
    return "Now" if WAITING.fullmatch(status or "") else FIXED[status]


def default_config():
    return os.environ.get("WORK_MAP_CONFIG") or "work-map.json"


def given_config(arg):
    """The config the user named (--config, else $WORK_MAP_CONFIG), else None."""
    return arg or os.environ.get("WORK_MAP_CONFIG") or None


def strict_decision_files(config):
    """Decision files a config names; refuses when it is unreadable, names none, or matches none."""
    try:
        with open(config, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, UnicodeError, ValueError) as exc:
        raise Refusal("config %s is unreadable or not valid JSON: %s" % (config, exc))
    vals = cfg.get("decisions") if isinstance(cfg, dict) else None
    vals = [vals] if isinstance(vals, str) else vals
    if not isinstance(vals, list) or not vals or not all(isinstance(v, str) for v in vals):
        raise Refusal("config %s names no decisions file (key \"decisions\")" % config)
    found = config_paths(config, "decisions")
    if not found:
        raise Refusal("config %s: no decisions file matches %s" % (config, ", ".join(vals)))
    return found


def config_paths(config, key):
    """Files the config lists under key, globs expanded, relative paths read from the config's folder."""
    try:
        with open(config, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError):
        return []
    base = os.path.dirname(os.path.abspath(config))
    vals = cfg.get(key, []) if isinstance(cfg, dict) else []
    vals = [vals] if isinstance(vals, str) else vals
    out = []
    for v in vals:
        pat = v if os.path.isabs(v) else os.path.join(base, v)
        out += sorted(glob.glob(pat, recursive=True))
    return out
HEADING = re.compile(r"^## (.*?)\s*$")
SECTIONS = ["Now", "Next", "Later", "Done"]
ITEM = re.compile(r"^- \*\*(?P<item>.+?)\*\* · (?P<rest>.*)$")
KEYS = ["id", "project", "worker", "status", "why", "spec", "decisions", "devlog", "touched"]


class Refusal(Exception):
    pass


def now_stamp():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def parse_item_line(line):
    """Item line -> {'item', <field>...} or None. A part without a known key continues the previous value."""
    m = ITEM.match(line)
    if not m:
        return None
    out, last = {"item": m.group("item")}, None
    for part in m.group("rest").split(" · "):
        km = re.match(r"^(%s): (.*)$" % "|".join(KEYS), part)
        if km and km.group(1) not in out:
            last = km.group(1)
            out[last] = km.group(2)
        elif last:
            out[last] += " · " + part
        else:
            return None
    return out


def format_line(f):
    parts = ["id: " + f["id"]] if f.get("id") else []
    if f.get("project"):
        parts.append("project: " + f["project"])
    if f.get("worker"):
        parts.append("worker: " + f["worker"])
    parts += ["%s: %s" % (k, f[k]) for k in ("status", "why", "spec", "decisions", "devlog", "touched") if k in f and f[k] != ""]
    return "- **%s** · %s" % (f["item"], " · ".join(parts))


def item_id(line):
    m = re.search(r" · id: ([^ ]+?)(?: · |$)", line) if ITEM.match(line) else None
    return m.group(1) if m else None


def find_block(lines, slug):
    """(start, end) of the item with this id: its line plus indented detail lines; None if absent."""
    for i, l in enumerate(lines):
        if item_id(l) == slug:
            j = i + 1
            while j < len(lines) and re.match(r"^\s+\S", lines[j]):  # any indented non-blank line belongs to the item
                j += 1
            return i, j
    return None


def section_at(lines, idx):
    cur = None
    for l in lines[:idx + 1]:
        m = HEADING.match(l)
        if m:
            cur = m.group(1)
    return cur


def insert_block(lines, section, block):
    """Insert at the end of the section; create the heading in order Now, Next, Later, Done if missing."""
    heads = {HEADING.match(l).group(1): i for i, l in enumerate(lines) if HEADING.match(l)}
    if section in heads:
        h = heads[section]
        e = next((i for i in range(h + 1, len(lines)) if HEADING.match(lines[i])), len(lines))
        last = max([i for i in range(h + 1, e) if lines[i].strip()] or [h])
        ins = block if last > h else [""] + block
        lines[last + 1:last + 1] = ins
        after = last + 1 + len(ins)
        if after < len(lines) and HEADING.match(lines[after]):
            lines.insert(after, "")
        return lines
    later = [heads[s] for s in SECTIONS[SECTIONS.index(section) + 1:] if s in heads]
    if later:
        lines[min(later):min(later)] = ["## " + section, ""] + block + [""]
        return lines
    while lines and lines[-1] == "":
        lines.pop()
    return lines + ["", "## " + section, ""] + block + [""]


def decision_slugs_ok(slugs, files):
    text = ""
    for p in files:
        try:
            text += open(p, encoding="utf-8").read() + "\n"
        except OSError:
            pass
    for s in slugs:
        if not re.search(r"^- \d{4}-\d{2}-\d{2} .* · " + re.escape(s) + r" · ", text, re.M):
            raise Refusal("decision slug not found in the decision files: " + s)


def implicit_base(arg):
    """The config's own folder when the config is implicit (neither --config nor $WORK_MAP_CONFIG), else None."""
    if given_config(arg):
        return None
    return os.path.dirname(os.path.abspath("work-map.json")) if os.path.isfile("work-map.json") else os.getcwd()


def confine_or_refuse(paths, base):
    if base is None:
        return
    for p in paths:
        problem = confined(p, base)
        if problem:
            raise Refusal(problem)


def resolve_file(project, config_path):
    if not os.path.isfile(config_path):
        raise Refusal("no PIPELINE for %s; pass --file (config unreadable: %s)" % (project, config_path))
    pid = project
    for mp in config_paths(config_path, "map"):
        try:
            with open(mp, encoding="utf-8") as fh:
                mlines = fh.readlines()
            for l in mlines:
                m = re.search(r" · id: ([^ ]+) · .*? · aka: (.*?) · ", l)
                if m and pid in [a.strip() for a in m.group(2).split(",")]:
                    pid = m.group(1)
        except OSError:
            pass
    for p in config_paths(config_path, "pipeline"):
        if os.path.basename(os.path.dirname(p)) == pid:
            return p, pid
    raise Refusal("no PIPELINE for %s; pass --file" % project)


def no_reserved(**fields):
    for k, v in fields.items():
        vals = v if isinstance(v, list) else [v]
        for x in vals:
            if isinstance(x, str) and ("\n" in x or "\r" in x or " · " in x):
                raise Refusal("%s contains a newline or reserved delimiter" % k)


def read_bytes(path):
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


def to_text(original):
    """Bytes -> text with LF newlines (CRLF files are worked on as LF and written back as CRLF)."""
    return original.decode("utf-8").replace("\r\n", "\n")


def atomic_write(path, data):
    """Write data to a temp file in the same folder (0600, then the original's mode), fsync, os.replace onto path."""
    folder = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".work-map-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.chmod(tmp, os.stat(path).st_mode & 0o7777)
        except FileNotFoundError:
            pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def restore_original(path, original):
    """Put the original bytes back atomically (or remove a file that did not exist); loud, with a backup, if even that fails."""
    try:
        if original is None:
            if os.path.exists(path):
                os.remove(path)
        else:
            try:
                with open(path, "rb") as fh:
                    if fh.read() == original:
                        return True  # the write never reached the target: nothing to put back
            except FileNotFoundError:
                pass
            atomic_write(path, original)
        return True
    except OSError as exc:
        backup = path + ".work-map-backup"
        try:
            with open(backup, "wb") as fh:
                fh.write(original or b"")
            where = "the original is saved beside it as " + backup
        except OSError:
            where = "the original could NOT be saved; take it from your own backup"
        print("RESTORE FAILED (%s): %s is now the new content; %s" % (exc, path, where), file=sys.stderr)
        return False


def commit(path, original, new_text, expect):
    """Write atomically, parse back via expect(lines); restore the original atomically on any failure."""
    path = os.path.realpath(path)
    if original is not None and b"\r\n" in original:
        new_text = new_text.replace("\n", "\r\n")
    try:
        atomic_write(path, new_text.encode("utf-8"))
        with open(path, encoding="utf-8") as f:
            ok = expect(f.read().split("\n"))
        if not ok:
            raise ValueError("written line failed parse-back")
    except BaseException as exc:  # any failure after the write puts the original bytes back
        restored = restore_original(path, original)
        if not isinstance(exc, Exception):
            raise
        print("failed: %s" % exc, file=sys.stderr)
        return 1 if restored else 3
    return 0


def matches(lines, slug, want, details, section):
    b = find_block(lines, slug)
    if not b:
        return False
    got = parse_item_line(lines[b[0]])
    if got is None or any(got.get(k) != v for k, v in want.items()):
        return False
    if lines[b[0] + 1:b[1]] != details:
        return False
    return section_at(lines, b[0]) == section


def add(argv):
    p = argparse.ArgumentParser(prog="pipeline.py add")
    p.add_argument("--project", required=True)
    p.add_argument("--item", required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--status", required=True)
    p.add_argument("--why", required=True)
    p.add_argument("--spec", default="none")
    p.add_argument("--decisions", default="")
    p.add_argument("--worker")
    p.add_argument("--detail", action="append", default=[])
    p.add_argument("--file")
    p.add_argument("--config")
    p.add_argument("--decisions-file", action="append")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    no_reserved(project=a.project, item=a.item, id=a.id, status=a.status, why=a.why, spec=a.spec,
                decisions=a.decisions, detail=a.detail)
    if not a.why.strip():
        raise Refusal("why is required and cannot be empty")
    if not status_ok(a.status):
        raise Refusal("status must be one of: " + " ".join(STATUSES))
    if not re.fullmatch(r"[a-z0-9-]+", a.id):
        raise Refusal("invalid id (use a-z, 0-9, -)")
    if not a.item.strip() or not a.spec.strip():
        raise Refusal("item and spec cannot be empty")
    slugs = [s.strip() for s in a.decisions.split(",") if s.strip()]
    if slugs:
        cfg_given = given_config(a.config) or ("work-map.json" if os.path.isfile("work-map.json") else None)
        dfiles = a.decisions_file or (strict_decision_files(cfg_given) if cfg_given else ["DECISIONS.md"])
        if not a.decisions_file:
            confine_or_refuse(dfiles, implicit_base(a.config))
        decision_slugs_ok(slugs, dfiles)
    if a.file:
        path, pid = a.file, a.project
    else:
        path, pid = resolve_file(a.project, given_config(a.config) or "work-map.json")
    path = os.path.realpath(path)  # resolved once: the same path is checked, locked and written
    if not a.file:
        confine_or_refuse([path], implicit_base(a.config))
    with locked(path):
        original = read_bytes(path)
        if original is None and not a.file:
            raise Refusal("%s does not exist; pass --file to create it" % path)
        text = to_text(original) if original is not None else "# %s — PIPELINE\n" % pid
        lines = text.split("\n")
        if any(item_id(l) == a.id for l in lines):
            raise Refusal("duplicate id: " + a.id)
        f = dict(item=a.item, id=a.id, status=a.status, why=a.why, spec=a.spec,
                 decisions=", ".join(slugs) or "none", touched=now_stamp())
        if os.path.basename(os.path.dirname(os.path.abspath(path))) != pid:
            f["project"] = pid
        if a.worker:
            f["worker"] = a.worker
        section = section_of(a.status)
        block = [format_line(f)] + ["  - " + d for d in a.detail]
        if a.dry_run:
            print("\n".join(block))
            return 0
        new = "\n".join(insert_block(lines, section, block))
        return commit(path, original, new, lambda ls: matches(ls, a.id, f, block[1:], section))


def update(argv):
    p = argparse.ArgumentParser(prog="pipeline.py update")
    p.add_argument("--file")
    p.add_argument("--project")
    p.add_argument("--id", required=True)
    p.add_argument("--status")
    p.add_argument("--devlog")
    p.add_argument("--add-detail", action="append", default=[])
    p.add_argument("--config")
    a = p.parse_args(argv)
    no_reserved(id=a.id, devlog=a.devlog or "", add_detail=a.add_detail)
    if a.status and not status_ok(a.status):
        raise Refusal("status must be one of: " + " ".join(STATUSES))
    if a.status == "done" and not a.devlog:
        raise Refusal("--status done requires --devlog YYYY-MM-DD")
    if a.status == "dropped" and not a.add_detail:
        raise Refusal("--status dropped requires --add-detail (why it died)")
    if a.devlog:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a.devlog):
                raise ValueError()
            datetime.date.fromisoformat(a.devlog)
        except ValueError:
            raise Refusal("devlog must be a valid YYYY-MM-DD")
    if a.file:
        path = a.file
    elif a.project:
        path, _ = resolve_file(a.project, given_config(a.config) or "work-map.json")
        confine_or_refuse([path], implicit_base(a.config))
    else:
        raise Refusal("pass --file or --project")
    with locked(path):
        original = read_bytes(path)
        if original is None:
            raise Refusal("no such file: " + path)
        lines = to_text(original).split("\n")
        b = find_block(lines, a.id)
        if not b:
            raise Refusal("unknown id: " + a.id)
        cur = parse_item_line(lines[b[0]])
        if cur is None:
            raise Refusal("item line for %s is not in item format" % a.id)
        if a.status:
            cur["status"] = a.status
        if a.devlog:
            cur["devlog"] = a.devlog
        cur["touched"] = now_stamp()
        want = {k: cur[k] for k in KEYS if k in cur}
        line = format_line(dict(cur))
        # keep the line's own field set; format_line only reorders fields into the house order
        # detail lines move verbatim (original indentation and text); new details append at two spaces
        details = lines[b[0] + 1:b[1]] + ["  - " + d for d in a.add_detail]
        block = [line] + details
        section = section_of(cur["status"])
        if section_at(lines, b[0]) == section:
            lines[b[0]:b[1]] = block
        else:
            del lines[b[0]:b[1]]
            lines = insert_block(lines, section, block)
        new = "\n".join(lines)
        want["item"] = cur["item"]
        return commit(path, original, new, lambda ls: matches(ls, a.id, want, details, section))


def check(argv):
    p = argparse.ArgumentParser(prog="pipeline.py check")
    p.add_argument("--config")
    p.add_argument("files", nargs="+")
    a = p.parse_args(argv)
    cfg = given_config(a.config) or ("work-map.json" if os.path.isfile("work-map.json") else None)
    try:
        limit = work_map.config_workbench_limit(cfg) if cfg and os.path.isfile(cfg) else work_map.DEFAULT_WORKBENCH_LIMIT
    except work_map.ConfigError as exc:
        raise Refusal(str(exc))
    bad = 0
    bench = []  # every workbench root across all the map files, so the limit is counted once, not per file
    for path in a.files:
        try:
            with open(path, encoding="utf-8") as fh:
                lines = fh.read().split("\n")
        except (OSError, UnicodeError) as exc:
            print("%s: unreadable: %s" % (path, exc))
            bad += 1
            continue
        seen = {}
        base = os.path.dirname(os.path.abspath(cfg)) if cfg and os.path.isfile(cfg) else os.path.dirname(os.path.abspath(path))
        bad += check_roots(path, lines, base, limit, bench)
        for n, l in enumerate(lines, 1):
            if not l.startswith("- **") or is_root(l):
                continue
            f = parse_item_line(l)
            if f is None:
                print("%s:%d: not an item line" % (path, n)); bad += 1; continue
            for k in ("id", "status", "why", "spec", "decisions"):
                if not f.get(k, "").strip():
                    print("%s:%d: missing %s" % (path, n, k)); bad += 1
            if f.get("status") and not status_ok(f["status"]):
                print("%s:%d: bad status %s" % (path, n, f["status"])); bad += 1
            if "touched" in f and not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", f["touched"]):
                print("%s:%d: malformed touched %s" % (path, n, f["touched"])); bad += 1
            if f.get("id"):
                if f["id"] in seen:
                    print("%s:%d: duplicate id %s (first at line %d)" % (path, n, f["id"], seen[f["id"]])); bad += 1
                seen.setdefault(f["id"], n)
    if len(bench) > limit:
        for p in work_map.root_problems([{"id": i, "status": "workbench", "pipeline": "none"} for i in bench], "", limit):
            if p["type"] == "workbench-over-limit":
                print("%s" % work_map.problem_line(p)); bad += 1
    return 1 if bad else 0


# ---- root lines: one line per project or idea in the map file ----

ROOT_ORDER = ["id", "access", "status", "aka", "pipeline", "spec", "why"]
ROOT_ACCESS = list(work_map.ROOT_ACCESS)
ROOT_STATUSES = list(work_map.ROOT_STATUSES)
# statuses written before the two-tag line (15 Nov); readable until converted, never written new
OLD_ROOT_STATUSES = ("live", "building", "later", "closed", "planned", "parked")
ROOT_KEYS = ROOT_ORDER


def parse_root_line(line):
    """Root line -> ({'name', <field>...}, [keys in written order]) or None. Same split as the reader."""
    m = ITEM.match(line)
    if not m:
        return None
    out, order, last = {"name": m.group("item")}, [], None
    for part in m.group("rest").split(" · "):
        km = re.match(r"^(%s): (.*)$" % "|".join(ROOT_KEYS), part)
        if km and km.group(1) not in out:
            last = km.group(1)
            out[last] = km.group(2)
            order.append(last)
        elif last:
            out[last] += " · " + part
        else:
            return None
    return out, order


def format_root(f, order):
    keys = list(order)
    for k in ("pipeline", "spec"):  # a pointer new to the line goes before why, where add puts it
        if k in f and k not in keys:
            keys.insert(keys.index("why") if "why" in keys else len(keys), k)
    keys += [k for k in ROOT_ORDER if k not in keys and k in f]
    return "- **%s** · %s" % (f["name"], " · ".join("%s: %s" % (k, f[k]) for k in keys if f.get(k) is not None))


def config_map_files(config):
    return config_paths(config, "map") if config and os.path.isfile(config) else []


def roots_in(path):
    """[(line_no, fields)] for the root lines of a map file."""
    try:
        with open(path, encoding="utf-8") as fh:
            return roots_in_lines(fh.read().split("\n"))
    except (OSError, UnicodeError):
        return []


def root_target(a):
    """(map file path, config path or None, folder pointers resolve from, workbench limit, all root lines of the config's map files)."""
    cfg = given_config(a.config) or ("work-map.json" if os.path.isfile("work-map.json") else None)
    if a.file:
        path = a.file
    else:
        files = config_map_files(cfg)
        if not files:
            raise Refusal("no map file in the config; pass --file")
        path = files[0]
    path = os.path.realpath(path)
    if not a.file:
        confine_or_refuse([path], implicit_base(a.config))
    try:
        limit = work_map.config_workbench_limit(cfg) if cfg and os.path.isfile(cfg) else work_map.DEFAULT_WORKBENCH_LIMIT
    except work_map.ConfigError as exc:
        raise Refusal(str(exc))
    base = os.path.dirname(os.path.abspath(cfg)) if cfg and os.path.isfile(cfg) else os.path.dirname(path)
    others = [os.path.realpath(m) for m in config_map_files(cfg)]
    return path, base, limit, [m for m in others if m != path]


def root_rules(f, was_bench, base, limit, bench_ids, status_given, access_given=False):
    """Refuse (one line) a root line that breaks the access, status, pointer and workbench rules; f is the line as it would be written.
    A line that keeps an old status (live, building, later ...) or has no access tag is only held to the pointer-path rules."""
    st = f.get("status", "")
    # whole-line check: an access tag on the line must be valid, and only the listed old statuses are grandfathered
    if (access_given or "access" in f) and f.get("access") not in ROOT_ACCESS:
        raise Refusal("access must be one of: " + " ".join(ROOT_ACCESS))
    if (status_given or st not in OLD_ROOT_STATUSES) and st not in ROOT_STATUSES:
        raise Refusal("status must be one of: " + " ".join(ROOT_STATUSES))
    if status_given and "access" not in f:
        raise Refusal("a line moving to status %s needs --access (%s)" % (st, " ".join(ROOT_ACCESS)))
    old = st not in ROOT_STATUSES or "access" not in f
    if st == "workbench" and not was_bench and len(bench_ids) >= limit:
        raise Refusal("the workbench is full (limit %d): %s. Move one off the workbench first" % (limit, ", ".join(bench_ids)))
    pl, sp = f.get("pipeline"), f.get("spec")
    if pl is not None and sp is not None:
        raise Refusal("a root line takes pipeline or spec, not both")
    if old:
        pass
    elif st in work_map.NEW_PROJECT_STATUSES and pl in (None, "none"):
        raise Refusal("status %s needs --pipeline <path to the project's own PIPELINE> (none is not enough)" % st)
    elif st == "idea" and pl is None and sp is None:
        raise Refusal("status idea needs --spec <path> or --pipeline <path> (write none when there is none)")
    for k, v in (("pipeline", pl), ("spec", sp)):
        if v is not None:
            if not v.strip():
                raise Refusal("--%s cannot be empty" % k)
            if v != "none" and not os.path.exists(v if os.path.isabs(v) else os.path.join(base, v)):
                raise Refusal("%s path does not exist: %s (resolved from %s)" % (k, v, base))


def root_matches(lines, rid, want):
    for l in lines:
        got = parse_root_line(l) if l.startswith("- **") else None
        if got and got[0].get("id") == rid:
            return all(got[0].get(k) == v for k, v in want.items())
    return False


def root_cmd(argv):
    if not argv or argv[0] not in ("add", "update"):
        raise Refusal("root needs add or update")
    adding = argv[0] == "add"
    p = argparse.ArgumentParser(prog="pipeline.py root " + argv[0])
    if adding:
        p.add_argument("--name", required=True)
        p.add_argument("--id", required=True)
        p.add_argument("--access", required=True)
        p.add_argument("--status", required=True)
        p.add_argument("--why", required=True)
        p.add_argument("--aka", default="none")
    else:
        p.add_argument("--id", required=True)
        p.add_argument("--access")
        p.add_argument("--status")
        p.add_argument("--why")
        p.add_argument("--aka")
        p.add_argument("--add-detail", action="append", default=[])
    p.add_argument("--pipeline")
    p.add_argument("--spec")
    p.add_argument("--file")
    p.add_argument("--config")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv[1:])
    no_reserved(id=a.id, access=a.access or "", status=a.status or "", why=a.why or "", pipeline=a.pipeline or "", spec=a.spec or "",
                name=getattr(a, "name", ""), aka=getattr(a, "aka", "") or "", add_detail=getattr(a, "add_detail", []))
    if a.pipeline is not None and a.spec is not None:
        raise Refusal("a root line takes pipeline or spec, not both")
    if adding:
        if not re.fullmatch(r"[a-z0-9-]+", a.id):
            raise Refusal("invalid id (use a-z, 0-9, -)")
        if not a.name.strip() or not a.why.strip():
            raise Refusal("name and why cannot be empty")
        if a.access not in ROOT_ACCESS:
            raise Refusal("access must be one of: " + " ".join(ROOT_ACCESS))
        if a.status not in ROOT_STATUSES:
            raise Refusal("status must be one of: " + " ".join(ROOT_STATUSES))
    path, base, limit, others = root_target(a)
    with locked(path):
        original = read_bytes(path)
        if original is None:
            if adding and a.file:
                text = "# Root\n"
            else:
                raise Refusal("no such file: " + path)
        else:
            text = to_text(original)
        lines = text.split("\n")
        mine = {f["id"]: (n, f) for n, f in roots_in_lines(lines)}
        elsewhere = [f for o in others for _, f in roots_in(o)]
        bench = [rid for rid, (_, f) in mine.items() if f.get("status") == "workbench"] + \
                [f["id"] for f in elsewhere if f.get("status") == "workbench"]
        if adding:
            if a.id in mine or any(f["id"] == a.id for f in elsewhere):
                raise Refusal("duplicate id: " + a.id)
            f = {"name": a.name, "id": a.id, "access": a.access, "status": a.status, "aka": ", ".join(x.strip() for x in a.aka.split(",") if x.strip()) or "none", "why": a.why}
            order = list(ROOT_ORDER)
            if a.pipeline is not None:
                f["pipeline"] = a.pipeline
            if a.spec is not None:
                f["spec"] = a.spec
            root_rules(f, False, base, limit, bench, True, True)
            line = format_root(f, [k for k in ROOT_ORDER if k in f])
            last = max([n for n, _ in roots_in_lines(lines)] or [0])
            if last:  # after the last root line and its indented details
                i = last
                while i < len(lines) and re.match(r"^\s+\S", lines[i]):
                    i += 1
                lines[i:i] = [line]
            else:
                while lines and lines[-1] == "":
                    lines.pop()
                lines += ["", line, ""] if len(lines) > 1 else [line, ""]
        else:
            if a.id not in mine:
                hit = [o for o in others if any(f["id"] == a.id for _, f in roots_in(o))]
                raise Refusal("unknown id: " + a.id + (" (it is in %s; pass --file)" % hit[0] if hit else ""))
            n, f = mine[a.id]
            order = parse_root_line(lines[n - 1])[1]
            was_bench = f.get("status") == "workbench"
            if a.access is not None:
                f["access"] = a.access
                if "access" not in order:
                    order.insert(order.index("status") if "status" in order else len(order), "access")
            if a.status:
                f["status"] = a.status
            if a.why:
                f["why"] = a.why
            if a.aka is not None:
                if not a.aka.strip():
                    raise Refusal("--aka cannot be empty (write none)")
                f["aka"] = a.aka
                if "aka" not in order:
                    order.insert(order.index("status") + 1 if "status" in order else len(order), "aka")
            for d in a.add_detail:
                if not d.strip() or "\n" in d:
                    raise Refusal("--add-detail must be one non-empty line")
            if a.pipeline is not None:  # a new pointer replaces the other kind (an idea promoted to a project)
                f["pipeline"] = a.pipeline
                f.pop("spec", None)
                order = [k for k in order if k != "spec"]
            if a.spec is not None:
                f["spec"] = a.spec
                f.pop("pipeline", None)
                order = [k for k in order if k != "pipeline"]
            # every update checks the whole line, so a why-only edit cannot re-save a line that breaks the rules
            root_rules(f, was_bench, base, limit, [b for b in bench if b != a.id], bool(a.status), a.access is not None)
            line = format_root(f, order)
            lines[n - 1] = line
            if a.add_detail:  # new details go after the line's existing indented details
                end = n
                while end < len(lines) and re.match(r"^\s+-\s+\S", lines[end]):  # same detail shape as the reader (work_map DETAIL)
                    end += 1
                lines[end:end] = ["  - " + d for d in a.add_detail]
        if a.dry_run:
            print(line)
            return 0
        want = {k: v for k, v in f.items() if k != "name"}
        return commit(path, original, "\n".join(lines), lambda ls: root_matches(ls, a.id, want))


def is_root(line):
    got = parse_root_line(line)
    return bool(got and "id" in got[0] and "aka" in got[0])


def roots_in_lines(lines):
    out = []
    for n, l in enumerate(lines, 1):
        if l.startswith("- **") and is_root(l):
            out.append((n, parse_root_line(l)[0]))
    return out


def check_roots(path, lines, base, limit, bench):
    """Print one line per root-line problem (same rules as `work_map.py inventory`); returns how many.
    The workbench limit is not judged here: workbench ids go into `bench` and check() counts them across all files."""
    roots = [dict(f) for _, f in roots_in_lines(lines) if f.get("status")]
    bench.extend(r["id"] for r in roots if r["status"] == "workbench" and r["id"] not in bench)
    n = 0
    for p in work_map.root_problems(roots, base, 10 ** 9):
        print("%s: %s" % (path, work_map.problem_line(p)))
        n += 1
    return n


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("add", "update", "check", "root"):
        print(__doc__)
        return 0
    try:
        if argv[0] == "check":
            return check(argv[1:])
        if argv[0] == "root":
            return root_cmd(argv[1:])
        return (add if argv[0] == "add" else update)(argv[1:])
    except Refusal as r:
        print("refused: %s" % r, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
