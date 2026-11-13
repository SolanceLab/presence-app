---
name: vault-map
description: Use when the user asks where something was written in their markdown or Obsidian notes ("where did we write about X?", "find my note on Y", "what links to Z"). Builds a local map of the vault once, then answers from the map, with the passage that answers the question. Nothing leaves the computer.
---

# vault-map

vault-map is one Python file that maps a folder of markdown notes (an Obsidian vault works as is) and answers "where did I write about X?" from the map instead of re-reading every note. The tool itself makes no network calls and uses no AI; the one-time `uvx` fetch below is the only thing that needs the internet.

## Run it

Every command starts with this prefix, and below `vault-map.py` stands for the whole prefix (`uvx --from ... vault-map.py`) each time, because `uvx` does not install the command for later use. `uvx` fetches vault-map once and runs it; Python 3.8 or newer is needed.

```
uvx --from "git+https://github.com/SolanceLab/vault-map@v1.4.1" vault-map.py <command>
```

If `uvx` is not found, install uv first (https://docs.astral.sh/uv/), or clone the repository and run `python3 vault-map.py <command>` from it.

## First run

1. Ask the user for the full path of their notes folder.
2. Build the map: `vault-map.py build "<vault path>"`. It takes seconds and writes `<vault>/.vault-map.json` (derived, safe to delete).
3. Query it.

Rebuild after the user adds many notes. The section index is kept in `~/.cache/vault-map/`, never inside the vault.

## Ask it

- `vault-map.py query "terms" "<vault>" --sections --n 5` returns the best passages, each with its note, its heading, the text and any other notes carrying the same passage. Use this first.
- `vault-map.py query "terms" "<vault>" --n 8` ranks whole notes, with matching headings, a snippet and the link and backlink neighbourhood. Add `--json` to read the result as data.
- `vault-map.py path "note a" "note b" "<vault>"` prints the shortest wikilink chain between two notes.
- `vault-map.py graph "<vault>" --out vault-map-graph.html` writes an interactive graph page the user opens in a browser.

Set `VAULT_MAP_DIR` to make one vault the default.

## Helping notes get found

When the user asks how to write or tidy notes so they are easier to find, or when searches keep missing because notes have no real title, few headings or no links, read [MARKDOWN-GUIDE.md](MARKDOWN-GUIDE.md) beside this file and suggest the one or two habits that would help most. Suggest; never rewrite the user's notes unless they ask.

## Report what it found

Say which note and which heading each answer came from, quoting the passage the tool returned. When nothing matches, say so and try other words from the user's own vocabulary before giving up. Open a note in full only when the user needs more than the passage.

It reads markdown (`.md`) files only and skips `.obsidian`, `.git`, `.trash` and `node_modules`.
