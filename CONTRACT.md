# presence-app contract

presence-app is a set, not a service: it lists three rooms and fetches them at pinned releases. It runs nothing and stores nothing itself.

## Doors it offers

| Door | What it answers |
|---|---|
| Plugin marketplace `presence-app` (`.claude-plugin/marketplace.json`) | `scriptorium@presence-app` and `antechamber@presence-app`, each pinned to its room's release |
| `make get` | Clones Scriptorium, Antechamber and vault-map at their pinned releases into `rooms/` |

## Data it owns

| Table / bucket / file | What is in it |
|---|---|
| `rooms/` (made by `make get`, not in the repo) | The three rooms' code, at the pinned releases |

Each room owns its own data; see its CONTRACT.md.

## Settings and secrets it needs

None. Each room names its own (Scriptorium: `SCRIPTORIUM_MCP_KEY`; Antechamber: `[mcp] key`).
