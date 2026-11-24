#!/usr/bin/env python3
# work-map — Copyright (c) 2026 House of Solance. PolyForm Noncommercial 1.0.0. Required Notice: Copyright (c) 2026 House of Solance (https://github.com/SolanceLab)
"""decisions.py add|query — write and search decision lines (the shape work_map.py reads).

  add   --slug S --applies a,b|house --from PROJECT --who NAME --time HH:MM --words "..." --call "..." --why "..."
        [--kind standing|one-time] [--date YYYY-MM-DD] [--session ID8] [--file P] [--config C] [--dry-run]
        [--supersedes OLD-SLUG]   marks the old line "SUPERSEDED by <slug>" (same file, one atomic write)
  query TERMS... [--config C] [--file P]... [--notes P]... [--decision-words REGEX]...
        Lines matching ALL terms (case-insensitive); when none match and there are 2+ terms, the closest
        lines matching at least half, tagged [k/n terms]. Live house-wide standing rules first, then newest date first;
        a replaced decision keeps its place with a [superseded by <slug>] prefix. A cut list names every left-out
        match under "also matching (N more):" and ends "showing N of M; add a term to narrow".
        Exit 0 always: no match means "not decided on record".

Paths: decision files come from --file, else the config's "decisions" list (--config, else $WORK_MAP_CONFIG,
else ./work-map.json; globs allowed, relative paths read from the config's folder), else ./DECISIONS.md.
--notes adds files or folders of .md notes, searched only on lines that read like a decision.
The session id is --session or $WORK_MAP_SESSION (first 8 characters of the session id).
Python 3.9+, standard library only.
"""
import argparse, datetime, glob, json, math, os, re, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the shared lock sits beside this script
from _writelock import locked, confined
import work_map

LINE_DATE = re.compile(r"^\s*(?:[-*]\s+)?(\d{4}-\d{2}-\d{2})\b")
ADD_LINE = re.compile(r'^- (?P<date>\d{4}-\d{2}-\d{2}) · session: (?P<session>.*?) · applies: \[(?P<applies>.*?)\] · from: (?P<project>.*?)(?: · kind: (?P<kind>standing|one-time))? · (?P<slug>[a-z0-9-]+) · (?P<who>.*?) \((?P<time>\d{2}:\d{2}) "(?P<words>.*?)"\) → (?P<call>.*?) · Why: (?P<why>.*)$')
SUPERSEDED_FIELD = re.compile(r"SUPERSEDED by ([a-z0-9-]+)\b")
DECISION = re.compile(r"(DECIDED|decided|chose|approved|her words|his words|their words)", re.I)


class ConfigRefused(Exception):
    pass


def default_config():
    """The config named by $WORK_MAP_CONFIG, else None (a ./work-map.json is used only when it exists)."""
    return os.environ.get("WORK_MAP_CONFIG") or None


def config_decision_files(config):
    """Decision files an explicitly given config names; refuses (never falls back) when it cannot."""
    try:
        with open(config, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ConfigRefused("config %s is unreadable or not valid JSON: %s" % (config, exc))
    vals = cfg.get("decisions") if isinstance(cfg, dict) else None
    vals = [vals] if isinstance(vals, str) else vals
    if not isinstance(vals, list) or not vals or not all(isinstance(v, str) for v in vals):
        raise ConfigRefused("config %s names no decisions file (key \"decisions\")" % config)
    base = os.path.dirname(os.path.abspath(config))
    out = []
    for v in vals:
        out += sorted(glob.glob(v if os.path.isabs(v) else os.path.join(base, v), recursive=True))
    if not out:
        raise ConfigRefused("config %s: no decisions file matches %s" % (config, ", ".join(vals)))
    return out


def decision_files(files, config):
    """--file wins; else the explicit config; else ./work-map.json if it exists; else ./DECISIONS.md (no config given)."""
    if files:
        return files
    if config:
        return config_decision_files(config)
    if os.path.isfile("work-map.json"):
        return config_decision_files("work-map.json")
    return ["DECISIONS.md"]


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


def slug_field_regex(slug):
    """Matches the front of a decision line up to and including the slug field (and its separator)."""
    return re.compile(r"^[-*] \d{4}-\d{2}-\d{2} · (?:session: .*? · applies: .*? · from: .*? · (?:kind: \S+ · )?)?" + re.escape(slug) + r" · ")


def parse_add_line(line):
    match = ADD_LINE.fullmatch(line)
    return match.groupdict() if match else None


def config_decision_words(config):
    """Extra decision regexes from the config's "decision_words" list; an unreadable config adds none."""
    config = config or ("work-map.json" if os.path.isfile("work-map.json") else None)
    if not config:
        return []
    try:
        with open(config, encoding="utf-8") as fh:
            words = json.load(fh).get("decision_words", [])
    except (OSError, UnicodeError, ValueError, AttributeError):
        return []
    return [w for w in words if isinstance(w, str)] if isinstance(words, list) else []


def candidate_lines(path, decision_only, extra=()):
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
    except (OSError, UnicodeError):
        return []
    start = 0
    if not decision_only:  # a register's own header ends at its first "---" line, if that comes before any "- " line
        for i, l in enumerate(lines):
            if l.startswith("- "):
                break
            if l.strip() == "---":
                start = i + 1
                break
    return [(i, l) for i, l in enumerate(lines, 1)
            if i > start and (not decision_only or DECISION.search(l) or any(x.search(l) for x in extra))]


def note_files(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += [os.path.join(p, f) for f in sorted(os.listdir(p)) if f.endswith(".md")]
        else:
            out.append(p)
    return out


def label(path):
    return os.path.basename(path)


def print_rest(rest):
    """Every match the cap left out, compactly: no silent cut."""
    print("also matching (%d more):" % len(rest))
    items = ["%s:%d %s" % (label(e["path"]), e["line"], e["slug"]) for e in rest]
    row = ""
    for n, item in enumerate(items):
        piece = item + ("," if n < len(items) - 1 else "")
        if row and len(row) + 1 + len(piece) > 120:
            print(row)
            row = "  " + piece
        else:
            row = (row + " " + piece) if row else "  " + piece
    if row:
        print(row)


def query_command(argv):
    parser = argparse.ArgumentParser(prog="decisions.py query")
    parser.add_argument("terms", nargs="+")
    parser.add_argument("--config", default=default_config())
    parser.add_argument("--file", action="append")
    parser.add_argument("--notes", action="append", default=[])
    parser.add_argument("--decision-words", action="append", default=[], metavar="REGEX")
    args = parser.parse_args(argv)
    terms = [t.lower() for t in " ".join(args.terms).split() if t.strip()]
    extra = []
    for pattern in args.decision_words + config_decision_words(args.config):
        try:
            extra.append(re.compile(pattern))
        except re.error as exc:
            print("refused: decision words %r is not a valid regex: %s" % (pattern, exc), file=sys.stderr)
            return 2
    try:
        regs = decision_files(args.file, args.config)
        if not args.file and not args.config:  # implicit config or default file: read only inside its own folder, as add does
            base = os.path.dirname(os.path.abspath("work-map.json")) if os.path.isfile("work-map.json") else os.getcwd()
            for r in regs:
                problem = confined(r, base)
                if problem:
                    raise ConfigRefused(problem)
    except ConfigRefused as exc:
        print("refused: %s" % exc, file=sys.stderr)
        return 2
    notes = note_files(args.notes)
    sources = [(r, False) for r in regs] + [(n, True) for n in notes]
    order = {path: n for n, (path, _) in enumerate(sources)}

    def entry(path, i, full):
        date = LINE_DATE.match(full)
        rec = work_map.parse_decision(full, (path, i))
        mark = "[superseded by %s] " % rec["superseded_by"] if rec and rec.get("superseded_by") else ""
        applies = rec.get("applies", []) if rec else []
        pin = bool(rec) and not rec.get("superseded_by") \
            and (rec.get("weight", "").lower() == "standing" or " · kind: standing · " in full) \
            and any(a.strip().lower() == "house" for a in applies)
        slug = rec.get("slug") if rec and rec.get("slug") else full.strip()[:40]
        return {"path": path, "line": i, "date": date.group(1) if date else "", "text": mark + full.strip()[:300],
                "pin": pin, "slug": slug}

    found = []
    for path, only in sources:
        found += [entry(path, i, l) for i, l in candidate_lines(path, only, extra)
                  if all(t in l.lower() for t in terms)]
    if found:
        found.sort(key=lambda e: (order[e["path"]], -e["line"]))  # later line first within a file, config order across files
        dated = sorted([e for e in found if e["date"]], key=lambda e: e["date"], reverse=True)  # stable: same-date ties keep that order
        undated = sorted([e for e in found if not e["date"]], key=lambda e: (order[e["path"]], e["line"]))  # notes lines: current order
        found = dated + undated
        found = [e for e in found if e["pin"]] + [e for e in found if not e["pin"]]  # live house-wide standing rules first, then today's order
        for e in found[:25]:
            print("%s:%d  %s" % (label(e["path"]), e["line"], e["text"]))
        if len(found) > 25:
            print_rest(found[25:])
            print("showing 25 of %d; add a term to narrow" % len(found))
        return 0
    uniq = list(dict.fromkeys(terms))
    if len(uniq) >= 2:
        need = math.ceil(len(uniq) / 2)
        part = []
        for path, only in sources:
            for i, l in candidate_lines(path, only, extra):
                k = sum(1 for t in uniq if t in l.lower())
                if k >= need:
                    part.append(dict(entry(path, i, l), k=k, group=0 if path in regs else 1))
        part.sort(key=lambda e: -e["line"] if e["group"] == 0 else 0)  # later line first among register lines
        part.sort(key=lambda e: e["date"], reverse=True)               # newest date first as the tie-break (undated last)
        part.sort(key=lambda e: (-e["k"], e["group"]))                 # term count, then registers before notes
        if part:
            print("No line matches every term; closest matches:")
            for e in part[:15]:
                print("[%d/%d terms] %s:%d  %s" % (e["k"], len(uniq), label(e["path"]), e["line"], e["text"]))
            if len(part) > 15:
                print_rest(part[15:])
                print("showing 15 of %d; add a term to narrow" % len(part))
            return 0
    print("No decision on record for: %s" % " ".join(terms))
    return 0


def add_command(argv):
    parser = argparse.ArgumentParser(prog="decisions.py add")
    for flag in ("slug", "applies", "from", "who", "time", "words", "call", "why"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--kind", choices=["standing", "one-time"])
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    parser.add_argument("--session")
    parser.add_argument("--file")
    parser.add_argument("--config", default=default_config())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--supersedes", metavar="OLD-SLUG")
    args = parser.parse_args(argv)
    fields = vars(args)
    for key, value in fields.items():
        if isinstance(value, str) and ("\n" in value or "\r" in value or " · " in value):
            parser.error("%s contains a newline or reserved delimiter" % key)
    if not re.fullmatch(r"[a-z0-9-]+", args.slug):
        parser.error("invalid slug")
    if args.supersedes is not None and not re.fullmatch(r"[a-z0-9-]+", args.supersedes):
        parser.error("invalid slug in --supersedes")
    if args.supersedes == args.slug:
        print("refused: --supersedes names the new slug itself (%s)" % args.slug, file=sys.stderr)
        return 2
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
            raise ValueError()
        datetime.date.fromisoformat(args.date)
    except ValueError:
        parser.error("date must be a valid YYYY-MM-DD")
    try:
        if not re.fullmatch(r"\d{2}:\d{2}", args.time):
            raise ValueError()
        datetime.datetime.strptime(args.time, "%H:%M")
    except ValueError:
        parser.error("time must be a valid HH:MM")
    applies = [part.strip() for part in args.applies.split(",")]
    if any(not part or any(c in part for c in "[]") for part in applies) or ("house" in applies and len(applies) != 1):
        parser.error("applies must be a comma list or house alone")
    session = args.session or os.environ.get("WORK_MAP_SESSION")
    if not session:
        parser.error("no session found; provide --session or set WORK_MAP_SESSION")
    if len(session) != 8 or any(c in session for c in "\r\n") or " · " in session:
        parser.error("session must be 8 characters without reserved delimiters")
    try:
        target = os.path.realpath(decision_files([args.file] if args.file else None, args.config)[0])  # resolved once: checked, locked and written as one path
        if not args.file and not args.config:  # implicit config or default file: write only inside its own folder
            base = os.path.dirname(os.path.abspath("work-map.json")) if os.path.isfile("work-map.json") else os.getcwd()
            problem = confined(target, base)
            if problem:
                raise ConfigRefused(problem)
    except ConfigRefused as exc:
        print("refused: %s" % exc, file=sys.stderr)
        return 2
    target = os.path.realpath(target)
    kind = fields.pop("kind", None)
    data = dict(date=args.date, session=session, applies=", ".join(applies), project=fields["from"], slug=args.slug, who=args.who, time=args.time, words=args.words, call=args.call, why=args.why, kind=kind)
    line = ('- {date} · session: {session} · applies: [{applies}] · from: {project}' + (' · kind: {kind}' if kind else '') + ' · {slug} · {who} ({time} "{words}") → {call} · Why: {why}').format(**data)
    if parse_add_line(line) != data:
        parser.error("fields cannot be represented unambiguously")
    with locked(target):
        wrote = False
        try:
            with open(target, "rb") as f:
                original = f.read()
            text = original.decode("utf-8")
            if any(slug_field_regex(args.slug).match(r) for r in text.split("\n")):
                parser.error("duplicate slug: " + args.slug)
            new_data = original + ("\n" if original and not original.endswith(b"\n") else "").encode() + (line + "\n").encode("utf-8")
            old_at = old_line = None
            if args.supersedes:
                old_field = slug_field_regex(args.supersedes)
                rows = text.split("\n")
                hits = [(n, old_field.match(r)) for n, r in enumerate(rows) if old_field.match(r)]
                if not hits:
                    elsewhere = None
                    for other in ([] if args.file else decision_files(None, args.config)):
                        if os.path.realpath(other) == target or not os.path.isfile(other):
                            continue
                        with open(other, encoding="utf-8", errors="replace") as fh:
                            if any(old_field.match(r) for r in fh.read().split("\n")):
                                elsewhere = other
                                break
                    if elsewhere:
                        print("refused: %s is in %s, not in %s; this release marks within one file only" % (args.supersedes, elsewhere, target), file=sys.stderr)
                    else:
                        print("refused: no line with slug %s in %s" % (args.supersedes, target), file=sys.stderr)
                    return 2
                if len(hits) > 1:
                    print("refused: slug %s is ambiguous in %s (lines %s)" % (args.supersedes, target, ", ".join(str(n + 1) for n, _ in hits)), file=sys.stderr)
                    return 2
                old_at, m = hits[0]
                prior = SUPERSEDED_FIELD.match(rows[old_at][m.end():])
                if prior:
                    print("refused: %s is already superseded by %s" % (args.supersedes, prior.group(1)), file=sys.stderr)
                    return 2
                parsed = work_map.parse_decision(rows[old_at], (target, old_at + 1))
                if not parsed or parsed["slug"] != args.supersedes:
                    print("refused: line %d of %s is not a decision line the reader indexes" % (old_at + 1, target), file=sys.stderr)
                    return 2
                old_line = rows[old_at][:m.end()] + "SUPERSEDED by %s · " % args.slug + rows[old_at][m.end():]
                rows[old_at] = old_line
                head = "\n".join(rows).encode("utf-8")
                new_data = head + ("\n" if head and not head.endswith(b"\n") else "").encode() + (line + "\n").encode("utf-8")
            if args.dry_run:
                if old_line:
                    print(old_line)
                print(line)
                return 0
            wrote = True
            atomic_write(target, new_data)
            with open(target, encoding="utf-8") as f:
                after = f.read()
            last = after.splitlines()[-1]
            if parse_add_line(last) != data:
                raise ValueError("written line failed parse-back")
            if old_line:
                back = after.split("\n")[old_at]
                rec = work_map.parse_decision(back, (target, old_at + 1))
                if back != old_line or not rec or rec["status"] != "superseded" or rec.get("superseded_by") != args.slug:
                    raise ValueError("marked line failed parse-back")
        except BaseException as exc:  # any failure after the write (incl. Ctrl-C) puts the original back
            restored = restore_original(target, original) if wrote else True
            if not isinstance(exc, Exception):
                if not restored:
                    print("add interrupted and the original could not be restored", file=sys.stderr)
                raise
            print("add failed: %s" % exc, file=sys.stderr)
            return 1 if restored else 3
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in ("add", "query"):
        print(__doc__)
        return 0
    return (add_command if argv[0] == "add" else query_command)(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
