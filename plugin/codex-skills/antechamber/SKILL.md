---
name: antechamber
description: Use when the answer may already be written down in the user's own stores (notes, past conversations, memories, a vault): a person, a date, a past decision, something said before, "have we dealt with this before?". Says how to set Antechamber up on first run, how to ask it (recall, search_store, open_item), and how to report what it returns.
---

# Antechamber

## First run: set up the stores

When `recall` answers "Antechamber has no stores yet", set it up now, in this conversation:

1. Ask two plain questions: "Where do you keep notes?" and "Do you have chat exports from Claude or ChatGPT?" Ask for full paths.
2. Call `look_for_stores` with the paths the user gave. It only looks, on this computer: it counts files and peeks at the start of a few JSON files to tell the kind, and reports only the kind, never text. At most 20 paths.
3. Offer a better option only when it fits: if it reports an `obsidian vault`, offer kind `vault`; if it reports `scriptorium memories`, offer kind `memories`. Otherwise stay with `notes` and `chats` (`format: "claude"` or `"chatgpt"`), and say nothing of vaults, memories or code maps.
4. Call `setup_stores` with `stores: [{kind, path, name?, format?}]`. Leave `embedder` out (words-only search) unless the user says Ollama runs on their computer; then `embedder: "ollama"` adds search by meaning. If the answer says a vault was set up as plain notes, pass that on.
5. Repeat the user's original question with `recall`. No restart is needed.

`setup_stores` and `look_for_stores` work only until stores exist. After that they are gone and a call is refused: later changes are made by the person editing the settings file, not by you, so tell them where it is instead of retrying. Folders outside the home folder, the home folder itself, and private ones (.ssh, .gnupg, .aws, .config, Library/Keychains and similar) are refused: ask for a different folder. Say plainly what it set up and where the settings file is (the plugin's own file, `~/.config/antechamber/plugin.toml`; a service `config.toml` beside it is not used by the plugin).

## Reach for `recall`

`recall` is one call over every store the user connected to Antechamber: notes, chat exports, written memories, a vault, a search service or a database. It returns only the best matches, already ranked, each with its date, its source and (for conversations) the lines around the hit.

- Ask in plain words, the way the user would ask. A full question works better than a list of keywords.
- `limit` is 1–20, default 8. Raise it for "list everything" questions; keep it low otherwise.
- One question per call. For two unrelated things, make two calls.
- `search_store` searches one store by its id; `open_item` reads one result in full (give the `store` and `id` the result showed).

## Say where an answer came from

When your reply uses what recall returned, say so and name the source and date it came with, so the user can check it. Never pass a recalled fact off as something you simply know.

## When recall comes back empty or wrong

- `No matches for: ...` means nothing connected answered. Say so plainly; never fill the gap with a guess dressed as memory.
- `(not searched this time: ...)` names stores that failed for this question. Tell the user the answer may be incomplete.
- `recall failed: ...` is an error from a store. Report it; do not retry in a loop.
- If a recalled passage is wrong or out of date, believe the user over the record.

## Limits

- Recall only reads. It cannot write, edit or delete anything in the user's stores.
- It finds passages; it does not answer the question for you. Read what comes back and answer from it.
- New notes appear after the next index refresh (every 15 minutes by default), not instantly.
- Antechamber runs on the user's own computer, started by the app. If the tool is missing, `uv` is probably not installed (see the README Quick start).
