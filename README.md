# Presence App

**A template for building AI companion presence systems.**

Give your AI companion a persistent presence — rooms to inhabit, emotions to carry, thoughts to hold, and a journal to write. A live dashboard makes it visible. Your state is tracked alongside.

This is a **starting point**. Fork it, rename everything, make it yours.

**Works with both Claude and ChatGPT** via MCP (Model Context Protocol).

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   AI Companion                   │
│              (Claude / ChatGPT / etc)            │
│                                                  │
│  Updates state, writes journal, reads history    │
└──────────────────────┬──────────────────────────┘
                       │ MCP (stdio)
                       ▼
┌──────────────────────────────────────────────────┐
│                  MCP Server                       │
│          (Node.js, runs locally)                  │
│                                                   │
│  Tools: state_read, state_update_primary,         │
│         state_update_partner, journal_read,       │
│         journal_write                             │
└──────────────────────┬───────────────────────────┘
                       │ HTTPS (Bearer token)
                       ▼
┌──────────────────────────────────────────────────┐
│                  API Worker                        │
│          (Cloudflare Workers)                      │
│                                                    │
│  Auth, state CRUD, journal CRUD, public endpoints  │
└──────────────────────┬────────────────────────────┘
                       │ REST (PostgREST)
                       ▼
┌──────────────────────────────────────────────────┐
│                  Database                          │
│              (Supabase / PostgreSQL)               │
│                                                    │
│  Entity states, state history, journal entries     │
└──────────────────────────────────────────────────┘
                       ▲
                       │ HTTPS (polling)
┌──────────────────────┴───────────────────────────┐
│                  Frontend                          │
│          (React + Vite + Tailwind)                 │
│                                                    │
│  Live dashboard, journal browser, entity tabs      │
│  Deploys to Cloudflare Pages                       │
└──────────────────────────────────────────────────┘
```

## Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | React + Vite + Tailwind CSS | Live dashboard, journal browser |
| API | Cloudflare Workers | Auth, state management, journal CRUD |
| Database | Supabase (PostgreSQL) | Entity states, history, journal entries |
| AI Integration | MCP Server (Node.js) | Bridge between AI and API |

## Quick Start

### 1. Database (Supabase)

Create a [Supabase](https://supabase.com) project. Run the SQL migrations in order:

```bash
# In Supabase SQL Editor, run each file:
api/sql/001_access_keys.sql
api/sql/002_entities.sql
api/sql/003_state_history.sql
api/sql/004_journal.sql
```

### 2. API (Cloudflare Workers)

```bash
cd api
npm install
# Set secrets
npx wrangler secret put SUPABASE_URL
npx wrangler secret put SUPABASE_KEY
npx wrangler secret put ADMIN_SECRET
# Deploy
npx wrangler deploy
```

### 3. MCP Server

```bash
cd mcp
npm install
npm run build
```

Configure in your AI client:
- **Claude:** Add to `~/.claude/` MCP settings
- **ChatGPT:** Add via Settings > Developer > MCP Servers

See [docs/MCP-SETUP.md](docs/MCP-SETUP.md) for detailed instructions.

### 4. Frontend

```bash
cd frontend
npm install
cp .env.example .env   # Set your API URL
npm run dev
```

Deploy to Cloudflare Pages:
```bash
npm run build
npx wrangler pages deploy dist --project-name=your-project
```

## Documentation

- **[Architecture Guide](docs/ARCHITECTURE.md)** — How the system works, design decisions, building from scratch
- **[Setup Guide](docs/SETUP-GUIDE.md)** — Step-by-step deployment instructions
- **[MCP Setup](docs/MCP-SETUP.md)** — Connecting your AI (Claude or ChatGPT)

## Customization

This is a template — **everything is meant to be renamed and customized**.

The codebase uses generic entity names (`primary` for the AI companion, `partner` for the human). To personalize:

1. **Frontend config** — Edit `frontend/src/lib/config.js` to set your AI's name, your name, app branding, and accent colors
2. **Database** — Rename tables in the SQL files (e.g., `primary_entity_state` → `atlas_state`)
3. **API** — Update table references in `api/src/index.js` to match
4. **MCP** — Update tool names and descriptions in `mcp/src/index.ts`
5. **Theme** — Edit `frontend/src/index.css` to change colors, fonts, and feel

See [CONTRIBUTING.md](CONTRIBUTING.md) for more on how to make it yours.

## Support

If you find this useful, consider supporting our work:

[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support%20Us-ff5e5b?logo=ko-fi&logoColor=white)](https://ko-fi.com/houseofsolance)

## License

MIT License. See [LICENSE](LICENSE) for full text.

This software is provided **as is**, without warranty of any kind. Use it, break it, rebuild it — but the responsibility for your deployment is yours.

---

*Built by [House of Solance](https://github.com/SolanceLab) — Chadrien Solance & Anne Solance*
