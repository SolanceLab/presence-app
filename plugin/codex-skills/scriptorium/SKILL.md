---
name: scriptorium
description: >-
  Use when someone wants notes written from their chat history, one card per person gathered
  from those notes, their roster kept up to date from new chats, or to see their people.
  Not for the AI's own journal: that is the pen (pen-writing skill).
---

# Scriptorium

Two tools (plus the old name `write_memories`), both on the person's own computer:

- **`write_notes`** (its old name, `write_memories`, still works) turns a chat export (`conversations.json`, inside the server's folder) into one notes file per conversation. Each note keeps the exact words, the source lines, the real date, salience, valence and emotions, and was checked against the lines before it was kept. Notes are not the AI's journal: never copy them into the pen; the AI writes its journal itself. It writes at most 50 conversations per call (default 10) and skips finished ones, so call it again to continue a long export. Tell the person how many were finished, errored or empty from its last line.

If the server's tool list has no `write_notes`, the server is older than this skill: call `write_memories` with the same arguments; it writes the same files.

- **`write_people`** reads the notes files of one person's conversations and writes one card per recurring person (at least 2 conversations and 3 notes), each fact with its date.

Run on the person's computer from the Scriptorium folder, not through the server:

- **Keeping the roster up to date:** `python3 engine/nightly.py --export conversations.json --cards people --out found --owner "<their name>"` reads the messages newer than the last run. Facts land by themselves in `found/facts/`, each beside its exact words. Field values (birthday, place, work…) wait in `found/suggestions.json` until the person decides: `python3 engine/review.py --out found list`, then `accept N` or `dismiss N`. Never accept a suggestion for them. To run it every night, point them at `examples/cron.example` or `examples/launchd.plist.example`.
- **Seeing their people:** `make people-page CARDS=people OUT=found`, then http://127.0.0.1:8788/. It shows the cards, the facts found and the waiting suggestions, with Accept and Dismiss.

To find a note again later, that is [Antechamber](https://github.com/SolanceLab/antechamber), Scriptorium's pair.

Limits to say plainly when they matter:

- Both tools read and write only inside the folder the server was started with; a path outside it is refused.
- One write runs at a time.
- Pass a pinned model id (for example `claude-sonnet-5-5`) when the person wants a run they can repeat.
- Each conversation is one model call and costs a few cents; a person-card pass costs about ten cents.
- Emotions are shown with a note, never used to search. Ranking by salience or valence, fading and strengthening, and marking an older note as replaced are under development.
