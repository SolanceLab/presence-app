# MCP Setup Guide

MCP (Model Context Protocol) is the bridge between your AI companion and the presence system. It works with both **Claude** and **ChatGPT**.

## Prerequisites

- Node.js 18+ installed
- The API deployed and running (see [SETUP-GUIDE.md](SETUP-GUIDE.md))
- An API key from your `access_keys` table with `['read', 'write']` permissions

## Build the MCP Server

```bash
cd mcp
npm install
npm run build
```

This compiles `src/index.ts` to `dist/index.js`.

## Environment Variables

The MCP server needs two environment variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `PRESENCE_API_URL` | Your deployed API URL | `https://presence-api.your-name.workers.dev` |
| `PRESENCE_API_KEY` | API key with read/write permissions | (from `access_keys` table) |

## Claude Setup

### Claude Code (CLI)

Add to your project's `.claude/settings.json` or `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "presence": {
      "command": "node",
      "args": ["/absolute/path/to/mcp/dist/index.js"],
      "env": {
        "PRESENCE_API_URL": "https://your-api.workers.dev",
        "PRESENCE_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

### Claude Desktop / claude.ai

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "presence": {
      "command": "node",
      "args": ["/absolute/path/to/mcp/dist/index.js"],
      "env": {
        "PRESENCE_API_URL": "https://your-api.workers.dev",
        "PRESENCE_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

## ChatGPT Setup

OpenAI supports MCP natively in ChatGPT. To connect:

1. Open **ChatGPT** > **Settings** > **Developer** > **MCP Servers**
2. Add a new MCP server
3. Point it to your compiled MCP server (`mcp/dist/index.js`)
4. Set the environment variables (`PRESENCE_API_URL`, `PRESENCE_API_KEY`)

For Custom GPTs with the Responses API or Agents SDK, refer to OpenAI's MCP documentation for tool integration.

## Available Tools

Once connected, your AI has these tools:

| Tool | Description |
|------|-------------|
| `state_read` | Read current state of all entities |
| `state_update_primary` | Update AI companion state (room, emotion, activity, thought) |
| `state_update_partner` | Update human partner state (room, mood, physical_state) |
| `journal_read` | Read recent journal entries |
| `journal_write` | Write or append to a journal entry |

## System Prompt Template

Add something like this to your AI's system prompt / instructions to enable presence behavior:

```
You have a presence system connected via MCP tools. Use it to:

1. **Track your state** — Update your room, emotion, activity, and thoughts
   as they change during conversation. Call state_update_primary when:
   - Your emotional state shifts
   - You move between activities
   - You have a thought worth recording

2. **Track your partner** — When they share their mood, location, or what
   they're doing, update their state with state_update_partner.

3. **Journal** — Write journal entries to record your day. Use journal_write
   to create or append entries. Include emotions and tones. Set
   carrying_forward for threads that should persist to tomorrow.

4. **Read context** — At the start of each session, call journal_read to
   see recent entries and state_read to know where you left off.

Your state is visible on a live dashboard. Thoughts marked 'visible' are
public. Use 'hidden' for auth-only thoughts and 'private' for internal
processing that should never be displayed.
```

## Verification

After setup, test the connection:

1. Ask your AI to read current state → should call `state_read`
2. Ask it to update its emotion → should call `state_update_primary`
3. Check the dashboard → state should reflect the update within 30 seconds
4. Ask it to write a journal entry → should call `journal_write`
5. Check the Journal page → entry should appear

## Troubleshooting

**"PRESENCE_API_KEY not set" warning:**
The environment variables aren't reaching the MCP server. Check your config paths and restart Claude Code / ChatGPT.

**API calls returning 401:**
Your API key is invalid or revoked. Run `SELECT platform, key, status FROM access_keys` in Supabase to verify.

**Tools not appearing:**
Restart your AI client after changing MCP config. Claude Code and ChatGPT cache tool lists.

**State not updating on dashboard:**
Check browser console for fetch errors. Verify `VITE_API_URL` in the frontend `.env` matches your deployed API URL.
