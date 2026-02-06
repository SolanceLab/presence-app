# Architecture Guide

This document explains how the presence system works, so you can understand the design decisions and build your own from scratch if you prefer.

## Overview

A presence system gives an AI companion persistent state — a room it occupies, emotions it carries, thoughts it holds, and a journal it writes. The human partner's state is tracked alongside. A web dashboard makes this visible in real time.

The system has four layers:

```
AI (Claude / ChatGPT)
  ↓ MCP (stdio)
MCP Server (Node.js, local)
  ↓ HTTPS (Bearer token)
API Worker (Cloudflare Workers)
  ↓ REST (PostgREST)
Database (Supabase / PostgreSQL)
  ↑ HTTPS (polling)
Frontend (React, Cloudflare Pages)
```

## Core Concepts

### Entity State (Single-Row Pattern)

Each entity (AI companion, human partner) has a **single-row table** that represents current state. When the AI updates its emotion from "calm" to "focused", the row is overwritten — not appended.

This makes reads trivial (`SELECT * FROM primary_entity_state LIMIT 1`) and keeps the table lean.

**Why a single row instead of latest-from-history?** Performance. A single-row read is O(1). Querying `ORDER BY timestamp DESC LIMIT 1` is O(log n) at best and requires an index. For a dashboard polling every 30 seconds, the difference matters.

### State History (Append-Only Log)

Every time a state row is updated, a **database trigger** automatically inserts a snapshot into `state_history`. This gives you a complete timeline of every state change without any application logic.

The trigger fires `AFTER UPDATE`, so it captures the final state after all fields are set. The history table includes the entity name, all state fields, who made the update, and a timestamp.

**Why triggers instead of application-level logging?** Reliability. If you add a new API endpoint or tool that updates state, the history is captured automatically. You can't accidentally skip it.

### Journal (Checkpoint Pattern)

Journal entries are keyed by date. When the AI writes a journal entry for today, one of two things happens:

1. **No entry exists for today:** Create a new entry with the narrative, title, emotions, etc.
2. **Entry already exists for today:** Append the new narrative with a checkpoint marker:

```
---

**Checkpoint: 14:30 [claude-code]**

[new narrative continues here]
```

This means the AI can journal throughout the day across multiple sessions and platforms, and it all accumulates in one entry. Emotions, tones, and platforms are **merged** (deduped union of arrays).

**Carrying forward:** Each entry has a `carrying_forward` field — open threads, unfinished conversations, things to remember. When a new entry is created, it inherits the previous day's carrying_forward if none is explicitly provided.

### Auth Tiers

Three levels of access:

| Tier | How | What |
|------|-----|------|
| **Public** | No auth | Read-only: current state (thought-filtered), recent journal previews |
| **Token** | Bearer token in header | Full read/write: state updates, journal writes, history |
| **Admin** | Admin secret | Key rotation |

Tokens are stored in the `access_keys` table. Each key has a `platform` name (e.g., "claude", "chatgpt") and a `permissions` array (`['read']` or `['read', 'write']`).

The frontend uses the same token system — "logging in" means entering a valid key from the `access_keys` table. This is intentionally simple. There are no user accounts.

### Thought Visibility

The AI's `thought_bubble` field has three visibility levels:

- **`visible`**: Shown on the public dashboard and authenticated dashboard
- **`hidden`**: Shown only on the authenticated dashboard (login required)
- **`private`**: Never shown on any dashboard (AI's internal thought)

This lets the AI have public-facing thoughts, auth-gated reflections, and truly private internal processing.

## Data Flow

### AI Updates State

```
1. AI decides to update (e.g., emotion changes)
2. AI calls MCP tool: state_update_primary({ primary_emotion: 'focused' })
3. MCP server → POST /state/primary with Bearer token
4. API worker validates token → PATCH primary_entity_state row
5. Database trigger fires → INSERT into state_history
6. API returns confirmation → MCP returns to AI
```

### Dashboard Reads State

```
1. Frontend polls GET /state/combined every 30 seconds
2. API reads both entity tables in parallel (Promise.all)
3. Computes derived fields (minutes_ago, online status)
4. Filters thought visibility
5. Returns combined state to frontend
6. React re-renders with new data
```

### AI Writes Journal

```
1. AI calls journal_write({ narrative: "...", emotions: [...] })
2. MCP server → POST /journal/write with Bearer token
3. API checks if entry exists for today
4. If exists: append with checkpoint marker, merge arrays
5. If new: create entry, inherit carrying_forward
6. Return action ("created" or "appended") and entry
```

## Building From Scratch

If you want to build this system yourself instead of using the template:

### Step 1: Database

You need PostgreSQL (Supabase is free and provides a REST API). Create:

1. **`access_keys`** — platform name, key (random hex), permissions array
2. **Entity state table(s)** — single-row, fixed UUID, all your state fields
3. **`state_history`** — append-only log with a trigger on each entity table
4. **`journal_entries`** — date-keyed, with narrative, emotions array, carrying_forward

The trigger is the most important piece. Without it, you'll forget to log history somewhere.

### Step 2: API

A Cloudflare Worker (or any serverless function) that:

1. Validates Bearer tokens against `access_keys`
2. Exposes GET/POST for each entity state
3. Exposes GET/POST for journal entries (with the checkpoint merge logic)
4. Exposes public endpoints (state without private thoughts, journal previews)

The worker talks to Supabase via its REST API (PostgREST). No ORM needed — just `fetch()` calls with the `apikey` and `Authorization` headers.

### Step 3: MCP Server

A Node.js script using `@modelcontextprotocol/sdk` that:

1. Defines tools for state read/write and journal read/write
2. Calls your API with a Bearer token
3. Runs on stdio transport (subprocess of Claude Code / ChatGPT)

The MCP server is the bridge between your AI's tool-calling capability and your API. Keep it thin — validation and business logic belong in the API.

### Step 4: Frontend

A React app (or any framework) that:

1. Polls the public or authenticated state endpoint
2. Displays entity states with auto-refresh
3. Browses journal entries
4. Has a simple login (password = API key)

Deploy to Cloudflare Pages, Vercel, Netlify — anywhere that serves static files.

## Extension Points

The template provides the core. Common extensions:

- **More entities** — Add tables and API endpoints for children, pets, companion characters
- **Notion sync** — Bidirectional sync for journal entries (so you can read/edit in Notion)
- **Emotion charting** — Use state_history to build emotion timelines on the dashboard
- **Health integration** — Add Garmin/health fields to partner state for live data
- **Room art** — Replace text room names with images on the dashboard
- **Day/night cycle** — Use timezone-aware logic to show different room states
