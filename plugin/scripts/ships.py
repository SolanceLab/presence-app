#!/usr/bin/env python3
# presence-app — Copyright (c) 2026 House of Solance. PolyForm Noncommercial 1.0.0. Required Notice: Copyright (c) 2026 House of Solance (https://github.com/SolanceLab)
# work-map — Copyright (c) 2026 House of Solance. PolyForm Noncommercial 1.0.0. Required Notice: Copyright (c) 2026 House of Solance (https://github.com/SolanceLab)
"""ships.py add — write one ship line (the shape work_map.py reads), once per release.

  add --project P --version V --sha SHA [--decisions a,b|none] [--tasks t1,t2|none]
      [--date YYYY-MM-DD] [--session ID8] [--file F] [--config C] [--dry-run]

Line: <date> · session: <id> · project: <P> · shipped <V> <SHA> · decisions: <slugs> · tasks closed: <ids>
Target file: --file, else the config's "ships" list (--config, else $WORK_MAP_CONFIG, else ./work-map.json):
the one file with a folder named like the project, else the only file listed, else refused.
With no config and no --file: ./DEVLOG.md. A second line for the same project and version is refused.
Where the line goes: directly under the file's one anchor line `<!-- work-map: newest first -->` when it has one
(two or more anchors: refused, file untouched); with no anchor it is appended at the end. A new file starts
`# <project> DEVLOG`, a blank line, the anchor, then the line.
The session id is --session or $WORK_MAP_SESSION, else "unknown". Python 3.9+, standard library only.

ships.py checkpoint / deviation / yes — the other DEVLOG line kinds (the DEVLOG holds checkpoints, approved deviations and publish yeses).

  checkpoint --project P --text T (--commit SHA [--commit SHA2 ...] | --ship VERSION | --who NAME --time HH:MM --words W)
             [--date YYYY-MM-DD] [--session ID8] [--file F] [--config C] [--dry-run]
  deviation  --project P --step S --who NAME --time HH:MM --words W --what D --why Y
             [--date YYYY-MM-DD] [--session ID8] [--file F] [--config C] [--dry-run]
  yes        --project P --tag T --who NAME --time HH:MM --words W [--repo R] [--note N]
             [--date YYYY-MM-DD] [--session ID8] [--file F] [--config C] [--dry-run]

Lines:
  - <date> · session: <id> · project: <P> · <T> · proof: commit <sha7>[, commit <sha7>] | ship <V> | <NAME> (<HH:MM> "<W>")
  - <date> · session: <id> · project: <P> · deviation: <S> · <NAME> (<HH:MM> "<W>") → <D> · Why: <Y>
  - <date> · session: <id> · project: <P> · publish-yes <R> <T> · yes: <NAME> (<HH:MM> "<W>")[ · <N>]
A checkpoint needs exactly one kind of proof (a SHA of 7 to 40 hex characters is written as its first 7). Every field must be
non-empty, with no newline and no " · " inside (words also take no double quote). Same target file rules as add, but the file must
already hold exactly one anchor: no anchor or two anchors is refused, file untouched. Only --file naming a path that does not
exist yet creates a file (heading, blank line, anchor, line). The line goes directly under the anchor, is read back, and the
original bytes are restored if anything fails. --dry-run prints the line and writes nothing.
A yes needs --who, --time and --words; --project picks the file and fills project:, --repo (default: the project) names the repo;
repo and tag are one word each; a second yes for the same repo and tag in the target file is refused, file untouched.
"""
import argparse, datetime, glob, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _writelock import locked, confined
from decisions import atomic_write, restore_original, default_config, ConfigRefused
import work_map

ANCHOR = "<!-- work-map: newest first -->"
YES_RE = re.compile(r'^\s*-\s+\d{4}-\d{2}-\d{2} · session: [^·]+ · project: [^·]+ · publish-yes (\S+) (\S+) · yes: ')


def config_ship_files(config):
    try:
        with open(config, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, UnicodeError, ValueError) as exc:
        raise ConfigRefused("config %s is unreadable or not valid JSON: %s" % (config, exc))
    vals = cfg.get("ships") if isinstance(cfg, dict) else None
    vals = [vals] if isinstance(vals, str) else vals
    if not isinstance(vals, list) or not vals or not all(isinstance(v, str) for v in vals):
        raise ConfigRefused("config %s names no ships file (key \"ships\")" % config)
    base = os.path.dirname(os.path.abspath(config))
    out = []
    for v in vals:
        full = v if os.path.isabs(v) else os.path.join(base, v)
        if glob.has_magic(v):
            out += sorted(glob.glob(full, recursive=True))
        else:
            out.append(os.path.normpath(full))  # a literal path may not exist yet: add creates it
    out = list(dict.fromkeys(out))
    if not out:
        raise ConfigRefused("config %s: no ships file matches %s" % (config, ", ".join(vals)))
    return out


def pick_file(files, project, config):
    own = [f for f in files if project in os.path.normpath(f).split(os.sep)[:-1]]
    if len(own) == 1:
        return own[0]
    if len(files) == 1 and not own:
        return files[0]
    raise ConfigRefused("config %s lists several ships files and none (or several) sit in a folder named %s: %s; pass --file"
                        % (config, project, ", ".join(own or files)))


def split_list(value):
    return [p.strip() for p in value.split(",") if p.strip() and p.strip().lower() != "none"]


def bad_field(value):
    return any(c in value for c in "\r\n[]") or " · " in value


def add_command(argv):
    parser = argparse.ArgumentParser(prog="ships.py add")
    for flag in ("project", "version", "sha"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--decisions", default="none")
    parser.add_argument("--tasks", default="none")
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    parser.add_argument("--session")
    parser.add_argument("--file")
    parser.add_argument("--config", default=default_config())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}", args.sha):
        parser.error("sha must be 7 to 40 hex characters")
    if not args.version.strip() or re.search(r"\s", args.version) or bad_field(args.version):
        parser.error("version must be one word without reserved characters")
    if not args.project.strip() or bad_field(args.project) or args.project != args.project.strip():
        parser.error("project is empty or contains a newline, bracket or reserved delimiter")
    decisions, tasks = split_list(args.decisions), split_list(args.tasks)
    for item in decisions + tasks:
        if bad_field(item):
            parser.error("slug or id %r contains a newline, bracket or reserved delimiter" % item)
    try:
        datetime.date.fromisoformat(args.date)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
            raise ValueError()
    except ValueError:
        parser.error("date must be a valid YYYY-MM-DD")
    session = args.session or os.environ.get("WORK_MAP_SESSION") or "unknown"
    if bad_field(session) or not session.strip():
        parser.error("session contains a newline, bracket or reserved delimiter")
    try:
        implicit = not args.file and not args.config
        if args.file:
            target = args.file
        elif args.config:
            target = pick_file(config_ship_files(args.config), args.project, args.config)
        elif os.path.isfile("work-map.json"):
            target = pick_file(config_ship_files("work-map.json"), args.project, "work-map.json")
        else:
            target = "DEVLOG.md"
        target = os.path.realpath(target)
        if implicit:
            base = os.path.dirname(os.path.abspath("work-map.json")) if os.path.isfile("work-map.json") else os.getcwd()
            problem = confined(target, base)
            if problem:
                raise ConfigRefused(problem)
    except ConfigRefused as exc:
        print("refused: %s" % exc, file=sys.stderr)
        return 2
    line = "%s · session: %s · project: %s · shipped %s %s · decisions: %s · tasks closed: %s" % (
        args.date, session, args.project, args.version, args.sha,
        ", ".join(decisions) or "none", ", ".join(tasks) or "none")
    with locked(target):
        wrote = False
        original = None
        anchor_at = None
        try:
            if os.path.exists(target):
                with open(target, "rb") as fh:
                    original = fh.read()
                anchors = [n for n, old in enumerate(original.decode("utf-8").splitlines(), 1) if old.strip() == ANCHOR]
                if len(anchors) > 1:
                    print("refused: %s has %d anchor lines (%s); keep exactly one %s" % (
                        target, len(anchors), ", ".join("line %d" % n for n in anchors), ANCHOR), file=sys.stderr)
                    return 2
                anchor_at = anchors[0] if anchors else None
                for n, old in enumerate(original.decode("utf-8").splitlines(), 1):
                    r = work_map.parse_ship(old, (target, n))
                    if r and r["project"] == args.project and r["version"] == args.version:
                        print("refused: %s %s is already logged at %s:%d: %s" % (args.project, args.version, target, n, old.strip()), file=sys.stderr)
                        return 2
            if args.dry_run:
                print(line)
                print(target)
                return 0
            os.makedirs(os.path.dirname(target), exist_ok=True)
            wrote = True
            if original is None:
                new_data = ("# %s DEVLOG\n\n%s\n" % (args.project, ANCHOR) + line + "\n").encode("utf-8")
                anchor_at = 3
            elif anchor_at:
                parts = original.decode("utf-8").splitlines(keepends=True)
                above, below = "".join(parts[:anchor_at]), "".join(parts[anchor_at:])
                nl = "" if above.endswith(("\n", "\r")) else "\n"
                new_data = (above + nl + line + "\n" + below).encode("utf-8")
            else:
                sep = b"\n" if original and not original.endswith(b"\n") else b""
                new_data = original + sep + (line + "\n").encode("utf-8")
            atomic_write(target, new_data)
            with open(target, encoding="utf-8") as fh:
                lines_now = fh.read().splitlines()
            last = lines_now[anchor_at] if anchor_at else lines_now[-1]  # the line under the anchor, else the last line
            r = work_map.parse_ship(last, (target, 0))
            want = [("depends-on", "decision:" + work_map.slugify(d)) for d in decisions] + [("done-by", "task:" + t) for t in tasks]
            if not (r and r["kind"] == "ship" and r["project"] == args.project and r["version"] == args.version
                    and r["sha"] == args.sha and r["links"] == want):
                raise ValueError("written line failed parse-back")
        except BaseException as exc:  # any failure after the write (incl. Ctrl-C) puts the original back
            restored = restore_original(target, original) if wrote else True
            if not isinstance(exc, Exception):
                raise
            print("add failed: %s" % exc, file=sys.stderr)
            return 1 if restored else 3
    print(line)
    print(target)
    return 0


class OneLine(argparse.ArgumentParser):
    def error(self, message):  # one line, no usage block, exit 2
        print("refused: %s" % message, file=sys.stderr)
        sys.exit(2)


def _clean(parser, name, value):
    if value is None or not value.strip():
        parser.error("%s is empty" % name)
    if "\r" in value or "\n" in value or " · " in value:
        parser.error("%s contains a newline or the reserved separator ' · '" % name)
    return value.strip()


def _who_proof(parser, who, time, words):
    who = _clean(parser, "who", who)
    if any(c in who for c in '"()→'):
        parser.error("who must be a plain name (no quotes, brackets or arrows)")
    words = _clean(parser, "words", words)
    if '"' in words:
        parser.error("words must not contain a double quote")
    m = re.fullmatch(r"(\d{2}):(\d{2})", time or "")
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        parser.error("time must be HH:MM (00:00 to 23:59)")
    return '%s (%s "%s")' % (who, time, words)


def devlog_write(kind, argv):
    parser = OneLine(prog="ships.py " + kind)
    parser.add_argument("--project", required=True)
    if kind == "checkpoint":
        parser.add_argument("--text")
        parser.add_argument("--commit", action="append", default=[])
        parser.add_argument("--ship")
    elif kind == "deviation":
        for flag in ("step", "what", "why"):
            parser.add_argument("--" + flag)
    else:
        for flag in ("repo", "tag", "note"):
            parser.add_argument("--" + flag)
    for flag in ("who", "time", "words"):
        parser.add_argument("--" + flag)
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    parser.add_argument("--session")
    parser.add_argument("--file")
    parser.add_argument("--config", default=default_config())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    project = _clean(parser, "project", args.project)
    try:
        datetime.date.fromisoformat(args.date)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
            raise ValueError()
    except ValueError:
        parser.error("date must be a valid YYYY-MM-DD")
    session = _clean(parser, "session", args.session or os.environ.get("WORK_MAP_SESSION") or "unknown")
    head = "- %s · session: %s · project: %s · " % (args.date, session, project)
    person = bool(args.who or args.time or args.words)
    if kind == "checkpoint":
        text = _clean(parser, "text", args.text)
        kinds = [bool(args.commit), args.ship is not None, person]
        if sum(kinds) != 1:
            parser.error("give exactly one proof: --commit, --ship, or --who with --time and --words")
        if args.commit:
            shas = []
            for c in args.commit:
                if not re.fullmatch(r"[0-9a-fA-F]{7,40}", c):
                    parser.error("commit must be 7 to 40 hex characters")
                shas.append("commit " + c[:7].lower())
            proof = ", ".join(shas)
        elif args.ship is not None:
            ver = _clean(parser, "ship", args.ship)
            if re.search(r"\s", ver):
                parser.error("ship must be one word")
            proof = "ship " + ver
        else:
            if not (args.who and args.time and args.words):
                parser.error("a spoken proof needs --who, --time and --words")
            proof = _who_proof(parser, args.who, args.time, args.words)
        line = "%s%s · proof: %s" % (head, text, proof)
    elif kind == "deviation":
        step = _clean(parser, "step", args.step)
        what = _clean(parser, "what", args.what)
        why = _clean(parser, "why", args.why)
        if not (args.who and args.time and args.words):
            parser.error("a deviation needs --who, --time and --words")
        line = "%sdeviation: %s · %s → %s · Why: %s" % (head, step, _who_proof(parser, args.who, args.time, args.words), what, why)
    else:
        if not (args.who and args.time and args.words):
            parser.error("a publish yes needs --who, --time and --words")
        tag = _clean(parser, "tag", args.tag)
        if re.search(r"\s", tag):
            parser.error("tag must be one word")
        repo = project if args.repo is None else _clean(parser, "repo", args.repo)
        if re.search(r"\s", repo):
            parser.error("repo must be one word (pass --repo when the project name has spaces)")
        line = "%spublish-yes %s %s · yes: %s" % (head, repo, tag, _who_proof(parser, args.who, args.time, args.words))
        if args.note is not None:
            line += " · " + _clean(parser, "note", args.note)
    try:
        implicit = not args.file and not args.config
        if args.file:
            target = args.file
        elif args.config:
            target = pick_file(config_ship_files(args.config), project, args.config)
        elif os.path.isfile("work-map.json"):
            target = pick_file(config_ship_files("work-map.json"), project, "work-map.json")
        else:
            target = "DEVLOG.md"
        target = os.path.realpath(target)
        if implicit:
            base = os.path.dirname(os.path.abspath("work-map.json")) if os.path.isfile("work-map.json") else os.getcwd()
            problem = confined(target, base)
            if problem:
                raise ConfigRefused(problem)
    except ConfigRefused as exc:
        print("refused: %s" % exc, file=sys.stderr)
        return 2
    creating = bool(args.file) and not os.path.exists(target)
    with locked(target):
        wrote = False
        original = None
        try:
            if os.path.exists(target):
                with open(target, "rb") as fh:
                    original = fh.read()
                anchors = [n for n, old in enumerate(original.decode("utf-8").splitlines(), 1) if old.strip() == ANCHOR]
                if len(anchors) != 1:
                    print("refused: %s has %s; it needs exactly one %s" % (
                        target, "no anchor line" if not anchors else "%d anchor lines" % len(anchors), ANCHOR), file=sys.stderr)
                    return 2
                anchor_at = anchors[0]
                if kind == "yes":
                    for n, old in enumerate(original.decode("utf-8").splitlines(), 1):
                        m = YES_RE.search(old)
                        if m and m.group(1) == repo and m.group(2) == tag:
                            print("refused: %s %s already has a publish yes at %s:%d" % (repo, tag, target, n), file=sys.stderr)
                            return 2
            elif creating:
                anchor_at = 3
            else:
                print("refused: %s does not exist (pass --file with a new path to create one)" % target, file=sys.stderr)
                return 2
            if args.dry_run:
                print(line)
                print(target)
                return 0
            os.makedirs(os.path.dirname(target), exist_ok=True)
            wrote = True
            if original is None:
                new_data = ("# %s DEVLOG\n\n%s\n" % (project, ANCHOR) + line + "\n").encode("utf-8")
            else:
                parts = original.decode("utf-8").splitlines(keepends=True)
                above, below = "".join(parts[:anchor_at]), "".join(parts[anchor_at:])
                nl = "" if above.endswith(("\n", "\r")) else "\n"
                new_data = (above + nl + line + "\n" + below).encode("utf-8")
            atomic_write(target, new_data)
            with open(target, encoding="utf-8") as fh:
                lines_now = fh.read().splitlines()
            if lines_now[anchor_at] != line:
                raise ValueError("written line failed read-back")
        except BaseException as exc:  # any failure after the write (incl. Ctrl-C) puts the original back
            restored = restore_original(target, original) if wrote else True
            if not isinstance(exc, Exception):
                raise
            print("%s failed: %s" % (kind, exc), file=sys.stderr)
            return 1 if restored else 3
    print(line)
    print(target)
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("checkpoint", "deviation", "yes"):
        return devlog_write(argv[0], argv[1:])
    if not argv or argv[0] != "add":
        print(__doc__)
        return 0
    return add_command(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
