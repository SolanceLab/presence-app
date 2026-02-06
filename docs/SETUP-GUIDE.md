# Setup Guide

Step-by-step deployment of the presence system.

## 1. Database (Supabase)

### Create Project

1. Go to [supabase.com](https://supabase.com) and create a free account
2. Create a new project — choose a region close to you
3. Save your project password (you won't need it often, but save it)

### Get Connection Details

From your Supabase dashboard:

- **Project URL:** Settings > API > Project URL (e.g., `https://abcdef.supabase.co`)
- **Service Role Key:** Settings > API > `service_role` key (NOT the `anon` key)

The `service_role` key bypasses Row Level Security and should only be used server-side (in your API worker and MCP server). Never expose it in frontend code.

### Run Migrations

Open the **SQL Editor** (Database > SQL Editor) and run each file in order:

```
api/sql/001_access_keys.sql    — Creates auth keys table + generates keys
api/sql/002_entities.sql       — Creates entity state tables
api/sql/003_state_history.sql  — Creates history table + triggers
api/sql/004_journal.sql        — Creates journal entries table
```

Run them one at a time. Each is idempotent (safe to re-run).

### Retrieve Your API Keys

After running `001_access_keys.sql`, get your generated keys:

```sql
SELECT platform, key, permissions FROM access_keys;
```

Save these keys — you'll need them for the API worker and MCP server.

## 2. API Worker (Cloudflare Workers)

### Prerequisites

- [Node.js](https://nodejs.org) 18+
- A [Cloudflare](https://cloudflare.com) account (free tier works)

### Setup

```bash
cd api
npm install
```

### Configure Secrets

```bash
npx wrangler secret put SUPABASE_URL
# Enter your Supabase project URL (https://xxx.supabase.co)

npx wrangler secret put SUPABASE_KEY
# Enter your Supabase service_role key

npx wrangler secret put ADMIN_SECRET
# Enter a strong random string (for key rotation endpoint)
```

### Local Development

```bash
# Create .dev.vars from the example
cp .dev.vars.example .dev.vars
# Edit .dev.vars with your Supabase URL and key

npx wrangler dev
# API runs at http://localhost:8787
```

### Deploy

```bash
npx wrangler deploy
```

This deploys to `https://presence-api.<your-subdomain>.workers.dev`. Save this URL.

### Verify

```bash
curl https://your-api.workers.dev/health
# Should return: {"status":"ok","timestamp":"..."}

curl -H "Authorization: Bearer YOUR_API_KEY" https://your-api.workers.dev/state/combined
# Should return entity states
```

## 3. Frontend (Cloudflare Pages)

### Setup

```bash
cd frontend
npm install
```

### Configure

```bash
cp .env.example .env
```

Edit `.env`:
```
VITE_API_URL=https://your-api.workers.dev
```

### Local Development

```bash
npm run dev
# Frontend runs at http://localhost:5173
```

### Deploy

```bash
npm run build
npx wrangler pages deploy dist --project-name=your-project-name
```

Or connect your GitHub repo to Cloudflare Pages for automatic deploys on push.

## 4. MCP Server

See [MCP-SETUP.md](MCP-SETUP.md) for detailed instructions on connecting Claude or ChatGPT.

Quick version:

```bash
cd mcp
npm install
npm run build
```

Then configure your AI client with the MCP server path and environment variables.

## 5. Verify End-to-End

1. **Dashboard loads:** Open your frontend URL, see "API connected"
2. **Login works:** Enter an API key from your `access_keys` table
3. **State updates:** Use MCP tools to update state, see it on the dashboard
4. **Journal works:** Write a journal entry via MCP, see it on the Journal page

## Customization

### Entity Names

Edit `frontend/src/lib/config.js`:
```javascript
export const ENTITY_NAMES = {
  primary: 'YourAIName',
  partner: 'YourName',
}
export const APP_NAME = 'YOUR APP NAME'
```

### Colors

Edit `frontend/src/index.css` to change theme colors, or `frontend/src/lib/config.js` for entity accent colors.

### Rooms

The room field is freeform text — no predefined list. Use whatever room names make sense for your system (e.g., "library", "garden", "workshop").
