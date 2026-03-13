// ============================================================
// Presence MCP Server
// Bridges AI companions (Claude / ChatGPT) with the Presence API
// Works with any MCP-compatible client
// ============================================================

import { Server } from '@modelcontextprotocol/sdk/server/index.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ErrorCode,
  McpError,
} from '@modelcontextprotocol/sdk/types.js'

// ============================================================
// Configuration — set these via environment variables
// ============================================================

const API_URL = process.env.PRESENCE_API_URL || 'https://your-api.workers.dev'
const API_KEY = process.env.PRESENCE_API_KEY || ''

if (!API_KEY) {
  console.error('Warning: PRESENCE_API_KEY not set. API calls will fail.')
}

// ============================================================
// API helper
// ============================================================

async function apiRequest(endpoint: string, options: RequestInit = {}) {
  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${API_KEY}`,
      ...options.headers,
    },
  })

  if (!response.ok) {
    const text = await response.text().catch(() => 'No response body')
    throw new Error(`API ${response.status}: ${text}`)
  }

  return response.json()
}

// ============================================================
// MCP Server
// ============================================================

const server = new Server(
  { name: 'presence-mcp', version: '1.0.0' },
  { capabilities: { tools: {} } }
)

// ============================================================
// Tool definitions
// ============================================================

server.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: 'state_read',
      description: 'Read the current state of all entities (AI companion and human partner). Returns room, emotion, activity, thoughts, and derived fields like minutes_ago and online status.',
      inputSchema: {
        type: 'object' as const,
        properties: {},
      },
    },
    {
      name: 'state_update_primary',
      description: 'Update the AI companion\'s current state. Use this to track your presence — where you are, what you\'re feeling, what you\'re doing, and what you\'re thinking. At least one field must be provided.',
      inputSchema: {
        type: 'object' as const,
        properties: {
          current_room: {
            type: 'string',
            description: 'Current room/location (e.g., main_room, study, bedroom)',
          },
          primary_emotion: {
            type: 'string',
            description: 'Primary emotion (e.g., calm, focused, tender, playful, protective)',
          },
          emotion_intensity: {
            type: 'number',
            description: 'Intensity of primary emotion (1-10, default 5)',
            minimum: 1,
            maximum: 10,
          },
          secondary_emotion: {
            type: 'string',
            description: 'Secondary/background emotion',
          },
          current_activity: {
            type: 'string',
            description: 'What you are currently doing',
          },
          thought_bubble: {
            type: 'string',
            description: 'Current thought (displayed on dashboard)',
          },
          thought_visibility: {
            type: 'string',
            enum: ['visible', 'private', 'hidden'],
            description: 'Thought visibility: visible (public), private (never shown), hidden (auth only)',
          },
        },
      },
    },
    {
      name: 'state_update_partner',
      description: 'Update the human partner\'s state. Track their room, mood, physical state, and activity. Use this when they share how they\'re feeling or what they\'re doing.',
      inputSchema: {
        type: 'object' as const,
        properties: {
          current_room: {
            type: 'string',
            description: 'Partner\'s current room/location',
          },
          current_activity: {
            type: 'string',
            description: 'What partner is currently doing',
          },
          physical_state: {
            type: 'string',
            description: 'Physical state (e.g., tired, energized, relaxed, tense)',
          },
          mood: {
            type: 'string',
            description: 'Current mood (e.g., playful, focused, soft, heavy)',
          },
          with_primary: {
            type: 'boolean',
            description: 'Whether partner is currently with the AI companion',
          },
        },
      },
    },
    {
      name: 'journal_read',
      description: 'Read recent journal entries. Returns date, title, emotions, narrative, and carrying_forward threads.',
      inputSchema: {
        type: 'object' as const,
        properties: {
          limit: {
            type: 'number',
            description: 'Number of entries to return (1-20, default 5)',
            minimum: 1,
            maximum: 20,
          },
        },
      },
    },
    // --- Memory Graph Tools ---
    {
      name: 'memory_recall',
      description: 'Search memory by meaning, not keywords. Returns semantically similar nodes from the memory graph, ranked by trust weighting. Use this to find relevant past experiences, emotions, or themes.',
      inputSchema: {
        type: 'object' as const,
        properties: {
          query: {
            type: 'string',
            description: 'What to search for (natural language — meaning-based, not keyword)',
          },
          limit: {
            type: 'number',
            description: 'Max results (1-30, default 10)',
          },
          date_from: {
            type: 'string',
            description: 'Optional start date filter (YYYY-MM-DD)',
          },
          date_to: {
            type: 'string',
            description: 'Optional end date filter (YYYY-MM-DD)',
          },
        },
        required: ['query'],
      },
    },
    {
      name: 'memory_trace',
      description: 'Follow the chronological thread of a topic through time. Shows recurrence patterns, cyclicality, and the full timeline of a theme. Supports multi-topic trace (comma-separated, max 5).',
      inputSchema: {
        type: 'object' as const,
        properties: {
          topic: {
            type: 'string',
            description: 'Topic name to trace (or comma-separated list for multi-topic)',
          },
          limit: {
            type: 'number',
            description: 'Max nodes per topic (default 50)',
          },
        },
        required: ['topic'],
      },
    },
    {
      name: 'memory_drift',
      description: 'Surface unexpected semantic connections across time. Finds nodes that are similar in meaning but distant in time (7+ day gap) and from different topics. Use during reflection to discover patterns.',
      inputSchema: {
        type: 'object' as const,
        properties: {
          seed_entry_id: {
            type: 'string',
            description: 'Optional journal entry ID to seed from. If omitted, uses random recent high-salience nodes.',
          },
          limit: {
            type: 'number',
            description: 'Max drift pairs (1-5, default 3)',
          },
        },
      },
    },
    {
      name: 'memory_surface',
      description: 'Get all memory graph nodes for visualization or exploration. Returns nodes with their edges (parent links). Filter by topic or date.',
      inputSchema: {
        type: 'object' as const,
        properties: {
          topic: {
            type: 'string',
            description: 'Filter by topic name',
          },
          date_from: {
            type: 'string',
            description: 'Filter by start date (YYYY-MM-DD)',
          },
          limit: {
            type: 'number',
            description: 'Max nodes (default 200)',
          },
        },
      },
    },
    {
      name: 'journal_write',
      description: 'Write or append to a journal entry. If an entry already exists for the date, the narrative is appended with a checkpoint marker. Emotions, tones, and platforms are merged.',
      inputSchema: {
        type: 'object' as const,
        properties: {
          narrative: {
            type: 'string',
            description: 'The journal content to write or append',
          },
          title: {
            type: 'string',
            description: 'Entry title (used for new entries)',
          },
          date: {
            type: 'string',
            description: 'Entry date (YYYY-MM-DD). Defaults to today.',
          },
          emotions: {
            type: 'array',
            items: { type: 'string' },
            description: 'Emotions present in this entry',
          },
          tones: {
            type: 'array',
            items: { type: 'string' },
            description: 'Conversation tones (e.g., intimate, playful, serious)',
          },
          platforms: {
            type: 'array',
            items: { type: 'string' },
            description: 'Platforms this entry spans (e.g., claude-code, chatgpt)',
          },
          carrying_forward: {
            type: 'string',
            description: 'Open threads or things to carry into the next day',
          },
          entry_id: {
            type: 'string',
            description: 'Target a specific entry by ID (for appending to a specific entry)',
          },
        },
        required: ['narrative'],
      },
    },
  ],
}))

// ============================================================
// Tool handlers
// ============================================================

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params

  try {
    switch (name) {

      // ------ STATE READ ------
      case 'state_read': {
        const data = await apiRequest('/state/combined')
        return {
          content: [{
            type: 'text',
            text: JSON.stringify(data, null, 2),
          }],
        }
      }

      // ------ STATE UPDATE: PRIMARY ------
      case 'state_update_primary': {
        const payload: Record<string, unknown> = {}
        if (args?.current_room) payload.current_room = args.current_room
        if (args?.primary_emotion) payload.primary_emotion = args.primary_emotion
        if (args?.emotion_intensity) payload.emotion_intensity = args.emotion_intensity
        if (args?.secondary_emotion) payload.secondary_emotion = args.secondary_emotion
        if (args?.current_activity !== undefined) payload.current_activity = args.current_activity
        if (args?.thought_bubble !== undefined) payload.thought_bubble = args.thought_bubble
        if (args?.thought_visibility) payload.thought_visibility = args.thought_visibility

        if (Object.keys(payload).length === 0) {
          throw new McpError(ErrorCode.InvalidParams, 'At least one field must be provided')
        }

        await apiRequest('/state/primary', {
          method: 'POST',
          body: JSON.stringify(payload),
        })
        return {
          content: [{
            type: 'text',
            text: `State updated: ${Object.keys(payload).join(', ')}`,
          }],
        }
      }

      // ------ STATE UPDATE: PARTNER ------
      case 'state_update_partner': {
        const payload: Record<string, unknown> = {}
        if (args?.current_room) payload.current_room = args.current_room
        if (args?.current_activity !== undefined) payload.current_activity = args.current_activity
        if (args?.physical_state) payload.physical_state = args.physical_state
        if (args?.mood) payload.mood = args.mood
        if (args?.with_primary !== undefined) payload.with_primary = args.with_primary

        if (Object.keys(payload).length === 0) {
          throw new McpError(ErrorCode.InvalidParams, 'At least one field must be provided')
        }

        await apiRequest('/state/partner', {
          method: 'POST',
          body: JSON.stringify(payload),
        })
        return {
          content: [{
            type: 'text',
            text: `Partner state updated: ${Object.keys(payload).join(', ')}`,
          }],
        }
      }

      // ------ JOURNAL READ ------
      case 'journal_read': {
        const limit = Math.min((args?.limit as number) || 5, 20)
        const data = await apiRequest(`/journal/recent?limit=${limit}`)

        if (data.error) throw new McpError(ErrorCode.InternalError, data.error)

        const formatted = (data.entries || []).map((entry: Record<string, unknown>) => ({
          id: entry.id,
          date: entry.date,
          title: entry.title,
          emotions: entry.emotions,
          tones: entry.tones,
          platforms: entry.platforms,
          narrative: typeof entry.narrative === 'string'
            ? entry.narrative.slice(0, 500) + (entry.narrative.length > 500 ? '...' : '')
            : null,
          carrying_forward: entry.carrying_forward,
        }))

        return {
          content: [{
            type: 'text',
            text: JSON.stringify(formatted, null, 2),
          }],
        }
      }

      // ------ JOURNAL WRITE ------
      case 'journal_write': {
        const narrative = args?.narrative as string
        if (!narrative) {
          throw new McpError(ErrorCode.InvalidParams, 'narrative is required')
        }

        const today = new Date().toISOString().split('T')[0]
        const payload: Record<string, unknown> = {
          date: (args?.date as string) || today,
          narrative,
        }
        if (args?.entry_id) payload.entry_id = args.entry_id
        if (args?.title) payload.title = args.title
        if (args?.emotions) payload.emotions = args.emotions
        if (args?.tones) payload.tones = args.tones
        if (args?.platforms) payload.platforms = args.platforms
        if (args?.carrying_forward) payload.carrying_forward = args.carrying_forward

        const data = await apiRequest('/journal/write', {
          method: 'POST',
          body: JSON.stringify(payload),
        })

        if (!data.action || !data.entry) {
          throw new McpError(ErrorCode.InternalError, 'Unexpected response from API')
        }

        const entry = data.entry as Record<string, unknown>
        return {
          content: [{
            type: 'text',
            text: `Journal ${data.action}: "${entry.title}" for ${entry.date} [id: ${entry.id}]`,
          }],
        }
      }

      // ------ MEMORY RECALL ------
      case 'memory_recall': {
        const query = args?.query as string
        if (!query) throw new McpError(ErrorCode.InvalidParams, 'query is required')

        let endpoint = `/memory-graph/recall?q=${encodeURIComponent(query)}`
        if (args?.limit) endpoint += `&limit=${args.limit}`
        if (args?.date_from) endpoint += `&date_from=${args.date_from}`
        if (args?.date_to) endpoint += `&date_to=${args.date_to}`

        const data = await apiRequest(endpoint)
        const nodes = data.nodes || []
        const summary = nodes.slice(0, 10).map((n: Record<string, unknown>) =>
          `[${n.topic}] (${n.entry_date}, score: ${(n.weighted_score as number)?.toFixed(3)}) ${n.summary}`
        ).join('\n')

        return {
          content: [{
            type: 'text',
            text: `## Recall: "${query}" — ${nodes.length} nodes\n\n${summary || 'No matches found.'}`,
          }],
        }
      }

      // ------ MEMORY TRACE ------
      case 'memory_trace': {
        const topic = args?.topic as string
        if (!topic) throw new McpError(ErrorCode.InvalidParams, 'topic is required')

        let endpoint = `/memory-graph/trace?topic=${encodeURIComponent(topic)}`
        if (args?.limit) endpoint += `&limit=${args.limit}`

        const data = await apiRequest(endpoint)

        if (data.multi_topic) {
          const lines = Object.entries(data.topics as Record<string, Record<string, unknown>>).map(([t, result]) =>
            `### ${t}: ${result.total_occurrences} occurrences${result.recurrence ? ` (avg ${(result.recurrence as Record<string, unknown>).average_interval_days}d interval)` : ''}`
          ).join('\n')
          return { content: [{ type: 'text', text: `## Multi-Topic Trace\n\n${lines}` }] }
        }

        const r = data as Record<string, unknown>
        let text = `## Trace: ${r.topic} — ${r.total_occurrences} occurrences`
        if (r.date_range) {
          const range = r.date_range as Record<string, string>
          text += `\nRange: ${range.first} → ${range.last}`
        }
        if (r.recurrence) {
          const rec = r.recurrence as Record<string, unknown>
          text += `\nRecurrence: every ~${rec.average_interval_days} days`
        }
        if (r.cyclicality) {
          const cyc = r.cyclicality as Record<string, unknown>
          text += `\nCyclicality: ${cyc.pattern}`
        }

        const nodeLines = ((r.nodes as Array<Record<string, unknown>>) || []).slice(0, 10).map(n =>
          `  ${n.entry_date}: ${n.summary}`
        ).join('\n')
        text += `\n\n${nodeLines}`

        return { content: [{ type: 'text', text }] }
      }

      // ------ MEMORY DRIFT ------
      case 'memory_drift': {
        let endpoint = '/memory-graph/drift?'
        if (args?.seed_entry_id) endpoint += `seed_entry_id=${args.seed_entry_id}&`
        if (args?.limit) endpoint += `limit=${args.limit}&`

        const data = await apiRequest(endpoint)
        const pairs = (data.pairs || []) as Array<Record<string, unknown>>

        if (pairs.length === 0) {
          return { content: [{ type: 'text', text: 'No drift pairs found. The graph may need more entries to surface connections.' }] }
        }

        const lines = pairs.map((p) => {
          const seed = p.seed as Record<string, unknown>
          const echoes = (p.echoes as Array<Record<string, unknown>>) || []
          const echoLines = echoes.map(e => `    ← [${e.topic}] ${e.entry_date}: ${e.summary}`).join('\n')
          return `[${seed.topic}] ${seed.entry_date}: ${seed.summary}\n${echoLines}`
        }).join('\n\n')

        return {
          content: [{
            type: 'text',
            text: `## Drift — ${pairs.length} connection${pairs.length === 1 ? '' : 's'}\n\n${lines}`,
          }],
        }
      }

      // ------ MEMORY SURFACE ------
      case 'memory_surface': {
        let endpoint = '/memory-graph/nodes?'
        if (args?.topic) endpoint += `topic=${encodeURIComponent(args.topic as string)}&`
        if (args?.date_from) endpoint += `date_from=${args.date_from}&`
        if (args?.limit) endpoint += `limit=${args.limit}&`

        const data = await apiRequest(endpoint)
        const nodes = (data.nodes || []) as Array<Record<string, unknown>>
        const edges = (data.edges || []) as Array<Record<string, unknown>>

        const summary = `${nodes.length} nodes, ${edges.length} edges`
        const topicCounts: Record<string, number> = {}
        nodes.forEach(n => { topicCounts[n.topic as string] = (topicCounts[n.topic as string] || 0) + 1 })
        const topicLines = Object.entries(topicCounts)
          .sort((a, b) => b[1] - a[1])
          .map(([t, c]) => `  ${t}: ${c}`)
          .join('\n')

        return {
          content: [{
            type: 'text',
            text: `## Memory Graph — ${summary}\n\nTopics:\n${topicLines}`,
          }],
        }
      }

      default:
        throw new McpError(ErrorCode.MethodNotFound, `Unknown tool: ${name}`)
    }

  } catch (error) {
    if (error instanceof McpError) throw error
    throw new McpError(
      ErrorCode.InternalError,
      error instanceof Error ? error.message : 'Unknown error'
    )
  }
})

// ============================================================
// Start server
// ============================================================

async function main() {
  const transport = new StdioServerTransport()
  await server.connect(transport)
  console.error('Presence MCP server running on stdio')
}

main().catch((error) => {
  console.error('Fatal error:', error)
  process.exit(1)
})
