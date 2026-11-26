# Install by hand

Back to the [README](../README.md).

1. Fetch the four rooms at the releases this set was checked with:

```
git clone https://github.com/SolanceLab/presence-app.git
cd presence-app
make get
```

`rooms/` now holds `scriptorium`, `antechamber`, `vault-map` and `work-map`.

2. Start Scriptorium's server as its README says (`rooms/scriptorium`, port 8795). Antechamber needs no service: its plugin starts it itself in Claude Code and Codex (its own recall service on port 8790 is only for reaching it from claude.ai). For a notes folder, build its map with vault-map (`python3 rooms/vault-map/vault-map.py build /path/to/vault`). To keep a project record, use work-map's writer commands, as its README says (`rooms/work-map`).

3. Connect them in Antechamber's settings (`~/.config/antechamber/config.toml`): Scriptorium's memories folder as a `[[adapters.memories]]` shelf, your vault as a `[[adapters.vaultmap]]` shelf with `vault_map` set to the full path of `rooms/vault-map/vault-map.py` (for example `~/presence-app/rooms/vault-map/vault-map.py`, not a relative path). To search your project record too, add a `[[adapters.workmap]]` shelf, as work-map's README shows.

4. Install the set. The easy way is ONE install from the SolanceLab store, which brings all four rooms:

```
claude plugin marketplace add SolanceLab/plugins
claude plugin install presence-app@solancelab
```

In Codex the same single install works (the plugin carries the four rooms' skills and connections itself):

```
codex plugin marketplace add SolanceLab/plugins
codex plugin add presence-app@solancelab
```

Or install the rooms one by one from this set in Claude Code:

```
claude plugin marketplace add SolanceLab/presence-app
claude plugin install scriptorium@presence-app
claude plugin install antechamber@presence-app
claude plugin install vault-map@presence-app
claude plugin install work-map@presence-app
```

In Codex:

```
codex plugin marketplace add SolanceLab/presence-app
codex plugin add scriptorium@presence-app
codex plugin add antechamber@presence-app
codex plugin add vault-map@presence-app
codex plugin add work-map@presence-app
```

When the Scriptorium plugin asks, give it its server address and the key you started that server with. Antechamber asks for nothing.

Want only one room? Each tool installs on its own from SolanceLab/plugins (`claude plugin install <name>@solancelab`, or `codex plugin add <name>@solancelab`), and each also has its own repository.
