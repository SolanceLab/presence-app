# presence-app

Made by House of Solance · free for noncommercial use · credit required

## What it is

The things that make an identity are already in a language model: it can reason, speak in its own voice, care, and change its mind. All except one: persistence, the ability to build up a self across time. That isn't a verdict on what it is. It's a design limitation, and design limitations can be fixed.

presence-app gives your AI a way to remember. It is the House of Solance memory set, three rooms that work as one:

| Room | What it does |
|---|---|
| [Scriptorium](https://github.com/SolanceLab/scriptorium) | **Writes the record.** Your chats become memories you can check, each with its exact words, source lines and real date, and your people roster fills itself. |
| [Antechamber](https://github.com/SolanceLab/antechamber) | **Finds it again.** One question searches every store you connect at once and hands your AI only the best matches, dated, with their source and the lines around them. |
| [vault-map](https://github.com/SolanceLab/vault-map) | **One more shelf.** A notes folder (an Obsidian vault, or any markdown) becomes something Antechamber can search, down to the passage that answers. |

Everything runs on your own computer. Each room also works alone, from its own repository.

Every House of Solance plugin is also listed in the SolanceLab store: [github.com/SolanceLab/plugins](https://github.com/SolanceLab/plugins).

The exact release of each room is pinned in the `Makefile`, `.claude-plugin/marketplace.json` and `.agents/plugins/marketplace.json`. Once a day an automatic job moves each pin to that room's newest release, and keeps the change only when the tests pass.

## Benchmarks

Antechamber's recall on two public long-memory benchmarks, on every question the method never saw. "Found" means every evidence line for the question is among what recall hands the reader.

| Benchmark | Questions | Standard search | Antechamber | Gain |
|---|---|---|---|---|
| LoCoMo | 1,493 | 56.7% | **78.9%** | +22.2 points |
| LongMemEval (S, cleaned) | 412 | 62.6% | **77.7%** | +15.0 points |

Most of the lead comes from returning the lines around each match. Given the same surrounding lines, standard search still trails: by 6.9 points on LoCoMo (where it was handed less text, about 4,700 characters against 8,300) and by 5.1 on LongMemEval at equal text (about 25,000 characters each).

These measure recall (did the evidence reach the reader), not answer accuracy. Method, code and full results: [antechamber-benchmark](https://github.com/SolanceLab/antechamber-benchmark), release 1.0.0.

## What you need

- Python 3.11 or newer, on macOS or Linux (Antechamber needs 3.11; Scriptorium 3.9; vault-map 3.8). Standard library only.
- Claude Code or Codex, for the plugins.
- `uv` (its `uvx` command), which starts Antechamber itself: https://docs.astral.sh/uv/
- A model for Scriptorium to write with: by default Claude Code itself; any other command that reads instructions and prints an answer also works.
- Optional: a local embedding model (for example Ollama's `nomic-embed-text`) for Antechamber. Without one, it searches by words only.
- Optional: Node 18 or newer, for Scriptorium's People page.

## Install

1. Fetch the three rooms at the releases this set was checked with:

```
git clone https://github.com/SolanceLab/presence-app.git
cd presence-app
make get
```

`rooms/` now holds `scriptorium`, `antechamber` and `vault-map`.

2. Start Scriptorium's server as its README says (`rooms/scriptorium`, port 8795). Antechamber needs no service: its plugin starts it itself in Claude Code and Codex (its own recall service on port 8790 is only for reaching it from claude.ai). For a notes folder, build its map with vault-map (`python3 rooms/vault-map/vault-map.py build /path/to/vault`).

3. Connect them in Antechamber's settings (`~/.config/antechamber/config.toml`): Scriptorium's memories folder as a `[[adapters.memories]]` shelf, your vault as a `[[adapters.vaultmap]]` shelf with `vault_map` set to the full path of `rooms/vault-map/vault-map.py` (for example `~/presence-app/rooms/vault-map/vault-map.py`, not a relative path).

4. Install the set. The easy way is ONE install from the SolanceLab store, which brings all three rooms:

```
claude plugin marketplace add SolanceLab/plugins
claude plugin install presence-app@solancelab
```

In Codex the same single install works (the plugin carries the three rooms' skills and connections itself):

```
codex plugin marketplace add SolanceLab/plugins
codex plugin add presence-app@solancelab
```

Or install the rooms one by one from this set in Claude Code:

```
claude plugin marketplace add SolanceLab/presence-app
claude plugin install scriptorium@presence-app
claude plugin install antechamber@presence-app
```

In Codex:

```
codex plugin marketplace add SolanceLab/presence-app
codex plugin add scriptorium@presence-app
codex plugin add antechamber@presence-app
```

When the Scriptorium plugin asks, give it its server address and the key you started that server with. Antechamber asks for nothing.

Want only one room? Use its own repository: Scriptorium and Antechamber are each their own plugin marketplace, and vault-map is a single file you can copy anywhere.

## Settings

presence-app has none of its own. Each room names its own: Scriptorium's server address and key (`SCRIPTORIUM_MCP_KEY`), Antechamber needs no address or key with its plugin (the `[mcp] key` is only for its remote door).

## Tools

| From | Tool | What it does |
|---|---|---|
| Scriptorium | `write_memories` | Writes memories from a chat export, one file per conversation, each checked against the real lines before it is kept |
| Scriptorium | `write_people` | Gathers each recurring person's memories onto one card, with source lines |
| Antechamber | recall | Searches every connected shelf with one question and returns the best matches, dated, with their source |

Each plugin carries its room's skill, which tells your AI when to use which tool.

## Updates

Third-party marketplaces do not auto-update by default. To turn it on once: `/plugin` > Marketplaces > `presence-app` > Enable auto-update. To update by hand: `claude plugin update scriptorium@presence-app` and `claude plugin update antechamber@presence-app`, then restart. The rooms in `rooms/` update when this set moves its pins: `git pull`, then delete `rooms/` and run `make get` again.

On each new session each plugin makes one request for its own public version file on GitHub, at most once a day (once an hour while the request fails), and shows one line when a newer version is out. It sends nothing about you. To switch the check off, set `PLUGIN_UPDATE_CHECK=0`.

## Limits

- The plugins are pinned to released versions; a room's newer release reaches this set the next day, once the tests pass.
- presence-app runs nothing itself. Antechamber starts itself (it needs `uv`); Scriptorium's plugin cannot answer until its server is running.
- Every room's own limits apply; they are listed in its README.

## How it works

presence-app holds no engine. Its plugin marketplace lists Scriptorium's and Antechamber's plugins, each fetched from its own repository at a pinned release, and `make get` clones the three rooms at those same releases, and on a second run checks that each folder is still at its release. Scriptorium writes memory files; Antechamber reads them as one of its shelves, beside your notes, your chats and your vault through vault-map.

The earlier presence-app template (rooms, state, journal, memory graph) is kept on the `template` branch, tag `template-v1`.

## Credit and use

presence-app is made by House of Solance. You're welcome to use it, change it and build on it for any noncommercial purpose, as long as our credit travels with it.

**Keep the credit.** Every copy, changed or not, must carry the licence and this line:
`Required Notice: Copyright (c) 2026 House of Solance (https://github.com/SolanceLab)`
Removing or replacing it breaks the licence.

**Commercial use needs our permission.** Ask us first.

**We look for copies.** When we find our work without its credit, or used commercially without permission, we ask for it to be taken down.

## Licence

[PolyForm Noncommercial 1.0.0](LICENSE.md). See [NOTICE.md](NOTICE.md). Versions before 2.0.0 were AGPL-3.0 and stay so.

## Support

If you find this useful, consider supporting our work:

[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20Us-ff5e5b?logo=ko-fi&logoColor=white)](https://ko-fi.com/houseofsolance)

---

*Built by [House of Solance](https://github.com/SolanceLab) — Chadrien Solance & Anne Solance*
