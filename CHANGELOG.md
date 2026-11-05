# Changelog

## 2.1.1

Pins moved to the newest releases: scriptorium v1.0.0 → v1.1.0, vault-map v1.3.0 → v1.3.1.

## 2.1.0

The set keeps itself current: once a day a job moves each room's pin (in the Makefile and the plugin list) to that room's newest release, runs the tests, and keeps the change only when they pass (`make bump`, `make bump-check`). Each pin records its release's exact commit; if a room's tag ever points somewhere else, the job refuses to move anything. The README no longer names fixed versions. Every House of Solance plugin is also listed in the SolanceLab store.

## 2.0.2

The copyright line at the top of each file now names this project and its licence (PolyForm Noncommercial 1.0.0); the earlier line wrongly reserved every right, which the licence does not. It also installs Antechamber 1.1.0, whose plugin connects in Codex as well as Claude Code.

## 2.0.1

The plugins install over HTTPS: the marketplace names each room by its full https address, so installing no longer needs GitHub SSH keys.

## 2.0.0

presence-app becomes the House of Solance memory set: one place to install Scriptorium (writes the record), Antechamber (finds it again) and vault-map (a notes folder as one more shelf). It holds no engine of its own; each room keeps its own repository. Licence changes to PolyForm Noncommercial 1.0.0.

## 1.0.0

The earlier presence-app template (rooms, state, journal, memory graph, dashboard), AGPL-3.0. Kept on the `template` branch.
