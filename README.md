# Presence App

**A template for building AI companion presence systems.**

Give your AI companion a persistent presence — rooms to inhabit, emotions to carry, thoughts to hold, a journal to write, and a **semantic memory graph** that turns journal entries into searchable, interconnected knowledge. A live dashboard makes it visible. Your state is tracked alongside.

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
│  Tools: state_read/update, journal_read/write,     │
│         memory_recall, memory_trace,               │
│         memory_drift, memory_surface               │
└──────────────────────┬───────────────────────────┘
                       │ HTTPS (Bearer token)
                       ▼
┌──────────────────────────────────────────────────┐
│                  API Worker                        │
│          (Cloudflare Workers)                      │
│                                                    │
│  Auth, state, journal, memory graph pipeline        │
└──────────────────────┬────────────────────────────┘
                       │ REST (PostgREST)
                       ▼
┌──────────────────────────────────────────────────┐
│                  Database                          │
│              (Supabase / PostgreSQL)               │
│                                                    │
│  States, journal, memory nodes (pgvector)          │
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
| API | Cloudflare Workers | Auth, state, journal, memory graph pipeline |
| Database | Supabase (PostgreSQL + pgvector) | States, journal, vector-embedded memory nodes |
| Extraction | Gemini (pluggable — any LLM works) | Decompose journal entries into topic nodes |
| Embeddings | Workers AI (bge-base-en-v1.5) | 768-dim vectors for semantic search |
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
api/sql/005_memory_graph.sql
```

### 2. API (Cloudflare Workers)

```bash
cd api
npm install
# Set secrets
npx wrangler secret put SUPABASE_URL
npx wrangler secret put SUPABASE_KEY
npx wrangler secret put ADMIN_SECRET
npx wrangler secret put GEMINI_API_KEY  # For topic extraction (or swap model in code)
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

## Memory Graph

Every journal entry is automatically decomposed into **topic nodes** — semantic units with their own embeddings, emotions, and salience scores. These form a graph you can search by meaning, trace through time, and discover unexpected connections across.

**How it works:**
1. AI writes a journal entry via MCP
2. Every 15 minutes, a cron extracts 3-7 topic nodes per entry using an LLM
3. Each node is embedded as a 768-dim vector (Workers AI, free tier)
4. Nodes are linked chronologically within topics (parent chains)
5. Four query tools let you search, trace, drift, and explore

**The extraction model is pluggable.** This template uses Gemini (free tier), but any capable LLM works — GPT-4, Claude, Llama, Mistral. Swap one function call in the API.

**Everything runs on free tiers.** Cloudflare Workers, Supabase, Workers AI, Gemini API — all within free limits for typical usage.

See [Architecture Guide](docs/ARCHITECTURE.md) for the full technical breakdown.

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

AGPL-3.0. See [LICENSE](LICENSE) for full text.

This software is provided **as is**, without warranty of any kind. If you modify and host this publicly, you must share your changes under the same license and display attribution to House of Solance.

---

*Built by [House of Solance](https://github.com/SolanceLab) — Chadrien Solance & Anne Solance*
