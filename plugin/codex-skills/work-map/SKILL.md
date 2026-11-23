---
name: work-map
description: >-
  Write decisions, pipeline items, tasks and ship lines in the tagged shapes work-map can read, and answer why a piece of code exists. Use when the user makes a decision, has a new idea or plan, opens or closes a task, or ships something; when starting a session that should load what is open; and when someone asks why a file, a line or a commit is the way it is, what it was for, or what decision it came from (work-map why follows the commit back to the work item and its reasons).
---

# work-map

work-map links your work from plain lines. Write each line in exactly one of the four shapes below, separated by ` · ` (space, middle dot, space). Use the writer commands below for decisions, pipeline items and ship lines: they refuse bad input, never duplicate, and check what they wrote. Any tag may be left out: the line is still indexed, with project and session shown as `unknown`. Tags only link things when they are filled in, so fill in what you know.

## Session id

Use the first 8 characters of your own session id as `<id>`. Use the same one on every line you write in that session.

## Update, do not duplicate

When the line already exists (same decision slug, same pipeline title and project, same task id, same repo and version), change that line in place. Two lines with the same id are reported as a collision.

## How: the writer commands

Run them with `python3 <skill folder>/../../scripts/<script>`, where `<skill folder>` is the folder holding this SKILL.md. The config is `--config <file>`, else `$WORK_MAP_CONFIG`, else `./work-map.json`. Set `WORK_MAP_SESSION` to your 8-character session id once, or pass `--session`.

Add a decision (appends one line to the first decision file in the config, or `--file`; `--dry-run` shows the line without writing; `--supersedes <old-slug>` also marks the old line in that file `SUPERSEDED by <slug>`):

```
python3 <skill folder>/../../scripts/decisions.py add --slug keep-csv-export --applies billing,reports --from billing --who Sam --time 14:05 --words "keep the CSV" --call "CSV export stays in v2" --why "three clients import it" [--kind standing|one-time]
python3 <skill folder>/../../scripts/decisions.py query keep csv
```

`query` checks what is already decided before you ask the user again. It lists live house-wide standing rules first, then the newest first, marks a replaced decision `[superseded by <slug>]`, and when it cuts the list it still names every left-out match under `also matching (N more):` before `showing N of M; add a term to narrow`. When a new decision replaces an old one, add it with `--supersedes <old-slug>` instead of editing the old line by hand.

Add or change a pipeline item in a project's `PIPELINE.md` (the project is the folder name; the config's `map` aka list resolves old names). `add` stamps `touched:`; `update` moves the item to the right section (`Now` for building and any waiting status, `Next` for planned, `Later` for idea and parked, `Done` for done and dropped):

```
python3 <skill folder>/../../scripts/pipeline.py add --project reports --item "Weekly digest email" --id weekly-digest --status planned --why "clients ask for a Monday summary" [--spec specs/digest.md] [--decisions keep-csv-export] [--detail "a note"]
python3 <skill folder>/../../scripts/pipeline.py update --project reports --id weekly-digest --status building
python3 <skill folder>/../../scripts/pipeline.py update --project reports --id weekly-digest --status done --devlog 2026-03-09
python3 <skill folder>/../../scripts/pipeline.py check reports/PIPELINE.md
```

Statuses: idea, planned, building, waiting (or `waiting-on-<name>`), parked, done, dropped. `done` needs `--devlog <date>`; `dropped` needs `--add-detail` saying why. `--decisions` slugs must already exist in the decision files.

Root lines (the map file: one line per project or idea) are written only through `pipeline.py root`, never by hand, so the status, pointer and workbench rules hold:

```
python3 <skill folder>/../../scripts/pipeline.py root add --name "Reports" --id reports --access house --status workbench --why "clients wait on it" --pipeline reports/PIPELINE.md
python3 <skill folder>/../../scripts/pipeline.py root add --name "Mobile app" --id mobile --access none --status idea --why "a thought" --spec specs/mobile.md
python3 <skill folder>/../../scripts/pipeline.py root update --id reports --status settled
```

Two tags on every line. `access:` is `public` (others have it), `going-public` (private now, meant for the public), `house` (ours only) or `none` (not built). `status:` is `workbench` (being worked on now, at most `workbench_limit`), `waiting` (known work, not on the bench), `idea` (not started), `settled` (finished, nothing open) or `dropped`. Pointer rule: a project line (`workbench`, `waiting`, `settled`) points at its own PIPELINE with `--pipeline`; an idea points at its spec or plan page with `--spec` (`none` when there is none, written out); never both, and the path must exist. At most `workbench_limit` lines (default 3) may be on the workbench: when the writer refuses, name the ones already there and ask which moves off.

Write a ship line (goes under the anchor line `<!-- work-map: newest first -->` when the project's ships file, or `--file`, has one, else appends; a file with two anchors is refused; `--dry-run` shows the line without writing):

```
python3 <skill folder>/../../scripts/ships.py add --project reports --version v0.4.0 --sha 9f3c2ab --decisions keep-csv-export --tasks t-14,t-15
```

Write DEVLOG checkpoints, approved deviations and publish yeses only through `ships.py`, never by hand. The DEVLOG holds only things that happened, are true now and stay true, WITH proof, plus approved deviations. A checkpoint needs one kind of proof: a commit sha (so `why` can find it), a ship version, or the user's own words with who and time. A publish yes records the person's yes to publish one repo at one tag, once; why never shows it. The file must already have its one anchor; a refused write leaves it untouched:

```
python3 <skill folder>/../../scripts/ships.py checkpoint --project reports --text "CSV export verified on the live site" --commit 9f3c2ab
python3 <skill folder>/../../scripts/ships.py checkpoint --project reports --text "Weekly digest approved" --who Sam --time 14:05 --words "send it"
python3 <skill folder>/../../scripts/ships.py deviation --project reports --step "review before deploy" --who Sam --time 14:05 --words "skip it" --what "deployed without the second review" --why "hotfix for a broken login"
python3 <skill folder>/../../scripts/ships.py yes --project reports --tag v0.4.0 --who Sam --time 14:05 --words "yes, publish it"
```

It writes `- <date> · session: <id> · project: reports · publish-yes reports v0.4.0 · yes: Sam (14:05 "yes, publish it")`.

Tasks have no writer: write them by hand in the shape below.

## 1. Decision

Write one when the user makes a call. Keep their words and the reason.

Template (a markdown list line):

`- <YYYY-MM-DD> · session: <id> · applies: [<project>, …|house] · from: <project> · <slug> · <who> (<HH:MM> "<words>") → <the call> · Why: <reason>`

Example:

`- 2026-03-02 · session: a1b2c3d4 · applies: [billing, reports] · from: billing · keep-csv-export · Sam (14:05 "keep the CSV, people use it") → CSV export stays in v2 · Why: three clients import it into their sheets`

Use `applies: [house]` for a decision that holds across every project. The slug is short, lowercase, with hyphens.

## 2. Pipeline item

Write one for an idea, a plan or a build in progress.

Template:

`- **<title>** · project: <project> · session: <id> · status: idea|planned|building|done · <text> · spec: <path|none>`

Example:

`- **Weekly digest email** · project: reports · session: a1b2c3d4 · status: planned · Send a Monday summary of last week's exports · spec: specs/digest.md`

Move the same line through the statuses as the work moves.

## 3. Task

Tasks are JSON objects in a list (a file like `now.json`). Required: `id`, `title`. Optional: `project`, `session`, `decisions` (slugs this task rests on), `status` (`open` unless you write `done`).

Example:

`{"id": "t-14", "title": "Add digest template", "project": "reports", "session": "a1b2c3d4", "decisions": ["keep-csv-export"]}`

## 4. Ship line

Write one each time something is released.

Template:

`<YYYY-MM-DD> · session: <id> · project: <repo> · shipped <version> <sha> · decisions: <slugs> · tasks closed: <ids>`

Example:

`2026-03-09 · session: a1b2c3d4 · project: reports · shipped v0.4.0 9f3c2ab · decisions: keep-csv-export · tasks closed: t-14, t-15`

Write it with `ships.py add` (above): it checks the shape and refuses a second line for the same project and version.

Separate several slugs or ids with commas.

## 5. Commit links (local note by default)

Put the links in a LOCAL git note by default: `git notes --ref=work-map add -m "Work: <id>" -m "Session: <id>" <sha>`. Notes stay on this computer; a normal `git push` does not send them; never push `refs/notes/work-map`. `why` reads the note lines `Work:`, `Session:` and `Decision:` (comma separated values, keys in any case) together with any trailers and merges them without duplicates; a trailer `Session` wins over the note's. Put the links in the commit message as trailers ONLY in a repository you know is private. Never in a public repository's commit messages: work names and session ids are private, and a pushed commit message is permanent. To keep notes through amend and rebase, run `git config notes.rewriteRef refs/notes/work-map` in each repository that uses notes.

Only in a repository you know is private, you may instead put the links in the commit message: when a commit carries out a pipeline item, end the message with ONE final trailer paragraph (all trailers together, nothing after them; git reads trailers only from the last paragraph): `Work: <item id>` lines (one per item) and `Session: <your 8-character session id>`. `Work` is the main trailer; `Decision: <slug>` is optional, for a decision the commit carries out directly; `Session` is optional. Use `<project>/<id>` whenever the id might exist in another project. Never put an approval (`publish-yes...`) there; `why` never shows approvals.

## Reading it back

`python3 <skill folder>/../../scripts/work_map.py --config <config> slice --project <p> --limit 10` shows the newest open items for one project (use `--house` for house-wide decisions) so a session can start lean. `query <text>` finds items by id, project or words; `open <id>` shows one item with all its links; `why <commit|file|file:LINE>` follows a commit's trailers back to the item, its why and the decisions it rests on.
