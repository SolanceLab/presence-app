# Contributing

This is a **template repository**, not a collaborative open-source project. It's designed to be forked and customized for your own AI companion system.

## How to Use This Template

1. **Fork** this repository (or click "Use this template" on GitHub)
2. **Rename** entities, colors, and labels to match your system
3. **Deploy** your own instance following the [Setup Guide](docs/SETUP-GUIDE.md)
4. **Extend** with features specific to your companion

## What to Customize

- `frontend/src/lib/config.js` — Entity names, app name, accent colors
- `frontend/src/index.css` — Theme colors
- `api/sql/002_entities.sql` — Table names and fields for your entities
- `mcp/src/index.ts` — Tool names and descriptions
- `docs/` — Rewrite to match your system

## Reporting Issues

If you find a bug in the template itself (not your customized version), feel free to [open an issue](../../issues). We'll look at it when we can, but this is maintained as a side project — no guarantees on response time.

## Pull Requests

We're not actively accepting PRs. This template reflects a specific architecture that works for us. If you build something cool with it, we'd love to hear about it — but the best way to contribute is by sharing your own presence system with the community.

## Questions

If you're stuck on setup or architecture decisions, open a Discussion (if enabled) or check the [Architecture Guide](docs/ARCHITECTURE.md) for design rationale.
