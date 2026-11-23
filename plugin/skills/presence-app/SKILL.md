---
name: presence-app
description: Use when the user asks how their AI remembers things with presence-app, or when you are unsure which of Scriptorium, Antechamber, vault-map and work-map to use. Says what each room does and which to reach for first.
---

# presence-app

presence-app is four rooms that work as one memory set. Everything runs on the user's own computer.

| Room | Use it to | Reach for it when |
|---|---|---|
| Antechamber | Find what is already written down: one question searches every store the user connected and returns only the best matches, dated, with their source | The user asks about a person, a date, a past decision, something said before. Try this first |
| Scriptorium | Write the record: turn chat exports into memories you can check (`write_memories`) and gather each recurring person onto one card (`write_people`) | The user has chat exports to turn into memories, or wants a people roster |
| vault-map | Add one more shelf: a folder of markdown notes (an Obsidian vault works) becomes something Antechamber can search, down to the passage | The user keeps notes in a folder and wants them searched |
| work-map | Remember why: what was decided, what is still open and what shipped, from the plain notes the user already keeps; Antechamber searches it as the workmap store | The user asks what was decided, what is open, waiting or recently touched |

Each room has its own skill with the exact steps. Read the room's skill before using its tools. If Antechamber says it has no stores yet, follow its first-run steps; do not guess folders.
work-map's writer commands run from this plugin's scripts folder (${CLAUDE_PLUGIN_ROOT}/scripts; in Codex, the scripts folder beside codex-skills).
