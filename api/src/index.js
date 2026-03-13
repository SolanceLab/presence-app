// ============================================================
// Presence API — Cloudflare Worker
// State management, journal, and auth for AI companion systems
// ============================================================

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, PATCH, DELETE, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...corsHeaders },
  })
}

// ============================================================
// Supabase helper
// ============================================================

async function supabaseRequest(env, endpoint, options = {}) {
  const response = await fetch(`${env.SUPABASE_URL}/rest/v1${endpoint}`, {
    ...options,
    headers: {
      'apikey': env.SUPABASE_KEY,
      'Authorization': `Bearer ${env.SUPABASE_KEY}`,
      'Content-Type': 'application/json',
      'Prefer': options.prefer || 'return=representation',
      ...options.headers,
    },
  })
  if (!response.ok) {
    const text = await response.text().catch(() => '')
    throw new Error(`Supabase ${response.status}: ${text}`)
  }
  return response.json()
}

// ============================================================
// Auth
// ============================================================

async function validateBearerAuth(request, env, requiredPermission = 'read') {
  const authHeader = request.headers.get('Authorization')
  if (!authHeader?.startsWith('Bearer ')) {
    return { valid: false, error: 'Missing Bearer token' }
  }
  const token = authHeader.slice(7)
  try {
    const keys = await supabaseRequest(env,
      `/access_keys?key=eq.${token}&status=eq.active&select=platform,permissions`
    )
    if (!keys.length) return { valid: false, error: 'Invalid or revoked key' }
    const key = keys[0]
    if (!key.permissions.includes(requiredPermission)) {
      return { valid: false, error: `Missing '${requiredPermission}' permission` }
    }
    return { valid: true, platform: key.platform }
  } catch {
    return { valid: false, error: 'Auth check failed' }
  }
}

async function validateAdminAuth(request, env) {
  const authHeader = request.headers.get('Authorization')
  if (!authHeader?.startsWith('Bearer ')) return { valid: false }
  return { valid: authHeader.slice(7) === env.ADMIN_SECRET }
}

// ============================================================
// Router
// ============================================================

export default {
  // Cron handler — runs on schedule to process new entries and backfill links
  async scheduled(event, env, ctx) {
    if (event.cron === '0 * * * *') {
      // Hourly: backfill parent links across graph nodes
      ctx.waitUntil(runBackfillCron(env))
    } else {
      // Every 15 min: process new journal entries into graph nodes
      ctx.waitUntil(processUnprocessedEntries(env))
    }
  },

  async fetch(request, env) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { headers: corsHeaders })
    }

    const url = new URL(request.url)
    const path = url.pathname
    const method = request.method

    try {
      // --- Health ---
      if (path === '/health') {
        return jsonResponse({ status: 'ok', timestamp: new Date().toISOString() })
      }

      // --- Auth ---
      if (path === '/auth/login' && method === 'POST') {
        return await handleLogin(request, env)
      }
      if (path === '/auth/verify' && method === 'GET') {
        return await handleVerify(request, env)
      }

      // --- Public (no auth) ---
      if (path === '/public/state' && method === 'GET') {
        return await getCombinedState(env, false)
      }
      if (path === '/public/recent' && method === 'GET') {
        return await getPublicJournals(env, url)
      }

      // --- State (authenticated) ---
      if (path === '/state/primary' && method === 'GET') {
        const auth = await validateBearerAuth(request, env, 'read')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        return await getEntityState(env, 'primary_entity_state')
      }
      if (path === '/state/primary' && method === 'POST') {
        const auth = await validateBearerAuth(request, env, 'write')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        const body = await request.json()
        return await updatePrimaryState(env, body, auth.platform)
      }

      if (path === '/state/partner' && method === 'GET') {
        const auth = await validateBearerAuth(request, env, 'read')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        return await getEntityState(env, 'partner_entity_state')
      }
      if (path === '/state/partner' && method === 'POST') {
        const auth = await validateBearerAuth(request, env, 'write')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        const body = await request.json()
        return await updatePartnerState(env, body, auth.platform)
      }

      if (path === '/state/combined' && method === 'GET') {
        const auth = await validateBearerAuth(request, env, 'read')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        return await getCombinedState(env, true)
      }

      if (path === '/state/history' && method === 'GET') {
        const auth = await validateBearerAuth(request, env, 'read')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        return await getStateHistory(env, url)
      }

      // --- Journal (authenticated) ---
      if (path === '/journal/recent' && method === 'GET') {
        const auth = await validateBearerAuth(request, env, 'read')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        return await getRecentJournals(env, url)
      }
      if (path === '/journal/write' && method === 'POST') {
        const auth = await validateBearerAuth(request, env, 'write')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        const body = await request.json()
        return await writeJournal(env, body)
      }
      if (path.startsWith('/journal/') && method === 'GET') {
        const auth = await validateBearerAuth(request, env, 'read')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        const id = path.split('/')[2]
        return await getJournalById(env, id)
      }

      // --- Admin ---
      if (path === '/admin/rotate' && method === 'POST') {
        const auth = await validateAdminAuth(request, env)
        if (!auth.valid) return jsonResponse({ error: 'Unauthorized' }, 401)
        const body = await request.json()
        return await rotateKey(env, body)
      }

      // --- Memory Graph ---
      if (path === '/memory-graph/process' && method === 'POST') {
        const auth = await validateBearerAuth(request, env, 'write')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        const body = await request.json()
        if (body.entry_id) {
          const result = await reprocessEntry(env, body.entry_id)
          return jsonResponse({ message: 'Entry reprocessed', ...result })
        }
        return jsonResponse(await processUnprocessedEntries(env))
      }

      if (path === '/memory-graph/recall' && method === 'GET') {
        const auth = await validateBearerAuth(request, env, 'read')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        return await handleMemoryRecall(env, url)
      }

      if (path === '/memory-graph/trace' && method === 'GET') {
        const auth = await validateBearerAuth(request, env, 'read')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        return await handleMemoryTrace(env, url)
      }

      if (path === '/memory-graph/drift' && method === 'GET') {
        const auth = await validateBearerAuth(request, env, 'read')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        return await handleMemoryDrift(env, url)
      }

      if (path === '/memory-graph/nodes' && method === 'GET') {
        const auth = await validateBearerAuth(request, env, 'read')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        return await handleMemoryGraphNodes(env, url)
      }

      if (path === '/memory-graph/topics' && method === 'GET') {
        const auth = await validateBearerAuth(request, env, 'read')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        const nodes = await supabaseRequest(env, '/memory_nodes?select=topic&order=topic.asc')
        const counts = {}
        ;(nodes || []).forEach(n => { counts[n.topic] = (counts[n.topic] || 0) + 1 })
        return jsonResponse({
          topics: Object.entries(counts).map(([topic, count]) => ({ topic, count }))
            .sort((a, b) => b.count - a.count),
        })
      }

      if (path === '/memory-graph/aliases' && method === 'GET') {
        const auth = await validateBearerAuth(request, env, 'read')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        const aliases = await supabaseRequest(env, '/topic_aliases?select=*&order=canonical.asc')
        return jsonResponse({ aliases: aliases || [] })
      }

      if (path === '/memory-graph/aliases' && method === 'POST') {
        const auth = await validateBearerAuth(request, env, 'write')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        const body = await request.json()
        if (!body.alias || !body.canonical) return jsonResponse({ error: 'alias and canonical required' }, 400)
        await supabaseRequest(env, '/topic_aliases', {
          method: 'POST',
          body: JSON.stringify({ alias: body.alias.toLowerCase(), canonical: body.canonical }),
          headers: { 'Prefer': 'resolution=merge-duplicates' },
        })
        return jsonResponse({ message: 'Alias added', alias: body.alias, canonical: body.canonical })
      }

      if (path === '/memory-graph/similar' && method === 'GET') {
        const auth = await validateBearerAuth(request, env, 'read')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        return await handleNodeSimilar(env, url)
      }

      if (path === '/memory-graph/backfill-links' && method === 'POST') {
        const auth = await validateBearerAuth(request, env, 'write')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        return await handleBackfillParentLinks(env)
      }

      if (path.startsWith('/memory-graph/node/') && method === 'PATCH') {
        const auth = await validateBearerAuth(request, env, 'write')
        if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
        const nodeId = path.replace('/memory-graph/node/', '')
        const body = await request.json()
        const allowed = ['topic', 'summary', 'emotions', 'salience', 'valence', 'context_tags']
        const patch = {}
        for (const key of allowed) {
          if (body[key] !== undefined) patch[key] = body[key]
        }
        if (Object.keys(patch).length === 0) return jsonResponse({ error: 'No valid fields to update' }, 400)
        await supabaseRequest(env, `/memory_nodes?id=eq.${nodeId}`, {
          method: 'PATCH',
          body: JSON.stringify(patch),
        })
        return jsonResponse({ message: 'Node updated', id: nodeId, patched: Object.keys(patch) })
      }

      return jsonResponse({ error: 'Not found' }, 404)

    } catch (err) {
      console.error('Unhandled error:', err)
      return jsonResponse({ error: 'Internal server error' }, 500)
    }
  }
}

// ============================================================
// Auth Handlers
// ============================================================

async function handleLogin(request, env) {
  const { password } = await request.json()
  if (!password) return jsonResponse({ error: 'Password required' }, 400)

  // Check password against access_keys table
  const keys = await supabaseRequest(env,
    `/access_keys?key=eq.${password}&status=eq.active&select=platform,key,permissions`
  )
  if (!keys.length) return jsonResponse({ error: 'Invalid credentials' }, 401)

  return jsonResponse({
    token: keys[0].key,
    platform: keys[0].platform,
    permissions: keys[0].permissions,
  })
}

async function handleVerify(request, env) {
  const auth = await validateBearerAuth(request, env, 'read')
  if (!auth.valid) return jsonResponse({ error: auth.error }, 401)
  return jsonResponse({ valid: true, platform: auth.platform })
}

// ============================================================
// State Handlers
// ============================================================

async function getEntityState(env, table) {
  const rows = await supabaseRequest(env, `/${table}?select=*&limit=1`)
  if (!rows.length) return jsonResponse({ error: 'State not found' }, 404)
  return jsonResponse({ state: rows[0] })
}

async function updatePrimaryState(env, body, platform) {
  const update = {
    last_updated_by: platform,
    updated_at: new Date().toISOString(),
  }

  if (body.current_room !== undefined) update.current_room = body.current_room
  if (body.primary_emotion !== undefined) update.primary_emotion = body.primary_emotion
  if (body.emotion_intensity !== undefined) update.emotion_intensity = body.emotion_intensity
  if (body.secondary_emotion !== undefined) update.secondary_emotion = body.secondary_emotion
  if (body.current_activity !== undefined) update.current_activity = body.current_activity
  if (body.thought_bubble !== undefined) update.thought_bubble = body.thought_bubble
  if (body.thought_visibility !== undefined) update.thought_visibility = body.thought_visibility

  const rows = await supabaseRequest(env,
    '/primary_entity_state?id=eq.00000000-0000-0000-0000-000000000001',
    { method: 'PATCH', body: JSON.stringify(update) }
  )
  return jsonResponse({ updated: true, state: rows[0] })
}

async function updatePartnerState(env, body, platform) {
  const update = {
    last_updated_by: platform,
    updated_at: new Date().toISOString(),
  }

  if (body.current_room !== undefined) update.current_room = body.current_room
  if (body.current_activity !== undefined) update.current_activity = body.current_activity
  if (body.physical_state !== undefined) update.physical_state = body.physical_state
  if (body.mood !== undefined) update.mood = body.mood
  if (body.with_primary !== undefined) update.with_primary = body.with_primary

  const rows = await supabaseRequest(env,
    '/partner_entity_state?id=eq.00000000-0000-0000-0000-000000000002',
    { method: 'PATCH', body: JSON.stringify(update) }
  )
  return jsonResponse({ updated: true, state: rows[0] })
}

async function getCombinedState(env, includeHidden = false) {
  const [primaryRows, partnerRows] = await Promise.all([
    supabaseRequest(env, '/primary_entity_state?select=*&limit=1'),
    supabaseRequest(env, '/partner_entity_state?select=*&limit=1'),
  ])

  const primary = primaryRows[0] || null
  const partner = partnerRows[0] || null

  // Compute derived fields
  if (primary) {
    const updatedAt = new Date(primary.updated_at)
    primary.minutes_ago = Math.floor((Date.now() - updatedAt) / 60000)
    primary.online = primary.minutes_ago < 120

    // Thought visibility filtering
    if (primary.thought_visibility === 'private') {
      primary.thought_bubble = null
    } else if (primary.thought_visibility === 'hidden' && !includeHidden) {
      primary.thought_bubble = null
    }
  }

  if (partner) {
    const updatedAt = new Date(partner.updated_at)
    partner.minutes_ago = Math.floor((Date.now() - updatedAt) / 60000)
  }

  return jsonResponse({ primary, partner })
}

async function getStateHistory(env, url) {
  const entity = url.searchParams.get('entity') || 'primary'
  const limit = Math.min(parseInt(url.searchParams.get('limit') || '50'), 200)

  const rows = await supabaseRequest(env,
    `/state_history?entity=eq.${entity}&order=recorded_at.desc&limit=${limit}&select=*`
  )
  return jsonResponse({ history: rows })
}

// ============================================================
// Journal Handlers
// ============================================================

async function getRecentJournals(env, url) {
  const limit = Math.min(parseInt(url.searchParams.get('limit') || '10'), 50)
  const rows = await supabaseRequest(env,
    `/journal_entries?order=date.desc&limit=${limit}&select=*`
  )
  return jsonResponse({ entries: rows })
}

async function getJournalById(env, id) {
  const rows = await supabaseRequest(env,
    `/journal_entries?id=eq.${id}&select=*`
  )
  if (!rows.length) return jsonResponse({ error: 'Entry not found' }, 404)
  return jsonResponse({ entry: rows[0] })
}

async function writeJournal(env, body) {
  const { date, narrative } = body
  if (!narrative) return jsonResponse({ error: 'narrative is required' }, 400)

  const entryDate = date || new Date().toISOString().split('T')[0]

  // Check for existing entry on this date
  const existing = await supabaseRequest(env,
    `/journal_entries?date=eq.${entryDate}&select=*`
  )

  if (existing.length) {
    // Append to existing entry (checkpoint pattern)
    const entry = existing[0]
    const now = new Date()
    const timeStr = now.toLocaleTimeString('en-US', {
      hour: '2-digit', minute: '2-digit', hour12: false,
      timeZone: 'UTC',
    })
    const platform = body.platforms?.[0] || 'unknown'
    const checkpoint = `\n\n---\n\n**Checkpoint: ${timeStr} [${platform}]**\n\n${narrative}`
    const updatedNarrative = (entry.narrative || '') + checkpoint

    // Merge arrays
    const mergedEmotions = mergeArrays(entry.emotions, body.emotions)
    const mergedTones = mergeArrays(entry.tones, body.tones)
    const mergedPlatforms = mergeArrays(entry.platforms, body.platforms)

    const update = {
      narrative: updatedNarrative,
      emotions: mergedEmotions,
      tones: mergedTones,
      platforms: mergedPlatforms,
      updated_at: now.toISOString(),
    }
    if (body.carrying_forward) update.carrying_forward = body.carrying_forward
    if (body.keynotes) {
      update.keynotes = entry.keynotes
        ? `${entry.keynotes}; ${body.keynotes}`
        : body.keynotes
    }

    const rows = await supabaseRequest(env,
      `/journal_entries?id=eq.${entry.id}`,
      { method: 'PATCH', body: JSON.stringify(update) }
    )
    return jsonResponse({ action: 'appended', entry: rows[0] })

  } else {
    // Create new entry
    // Optionally inherit carrying_forward from previous day
    let carryingForward = body.carrying_forward
    if (!carryingForward) {
      const prev = await supabaseRequest(env,
        `/journal_entries?date=lt.${entryDate}&order=date.desc&limit=1&select=carrying_forward`
      )
      if (prev.length && prev[0].carrying_forward) {
        carryingForward = prev[0].carrying_forward
      }
    }

    const newEntry = {
      date: entryDate,
      title: body.title || `Entry for ${entryDate}`,
      narrative,
      carrying_forward: carryingForward || null,
      emotions: body.emotions || [],
      tones: body.tones || [],
      platforms: body.platforms || [],
      entry_type: body.entry_type || 'journal',
      keynotes: body.keynotes || null,
    }

    const rows = await supabaseRequest(env, '/journal_entries', {
      method: 'POST',
      body: JSON.stringify(newEntry),
    })
    return jsonResponse({ action: 'created', entry: rows[0] })
  }
}

function mergeArrays(existing, incoming) {
  if (!incoming?.length) return existing || []
  const set = new Set([...(existing || []), ...incoming])
  return [...set]
}

// ============================================================
// Public Handlers
// ============================================================

async function getPublicJournals(env, url) {
  const limit = Math.min(parseInt(url.searchParams.get('limit') || '10'), 20)
  const rows = await supabaseRequest(env,
    `/journal_entries?order=date.desc&limit=${limit}&select=id,date,title,emotions,tones,platforms`
  )

  // Return preview only (no narrative for public)
  const entries = rows.map(e => ({
    id: e.id,
    date: e.date,
    title: e.title,
    emotions: e.emotions,
    tones: e.tones,
    platforms: e.platforms,
  }))
  return jsonResponse({ entries })
}

// ============================================================
// Admin Handlers
// ============================================================

async function rotateKey(env, body) {
  const { platform } = body
  if (!platform) return jsonResponse({ error: 'platform is required' }, 400)

  // Generate new key
  const newKey = crypto.randomUUID().replace(/-/g, '') + crypto.randomUUID().replace(/-/g, '')

  const rows = await supabaseRequest(env,
    `/access_keys?platform=eq.${platform}`,
    {
      method: 'PATCH',
      body: JSON.stringify({
        key: newKey,
        rotated_at: new Date().toISOString(),
      }),
    }
  )
  if (!rows.length) return jsonResponse({ error: 'Platform not found' }, 404)
  return jsonResponse({ platform, new_key: newKey })
}

// ============================================================
// Memory Graph — Processing Pipeline
// ============================================================
//
// The extraction model is PLUGGABLE. This template uses Gemini via
// the OpenAI-compatible API, but any capable model works (GPT-4,
// Claude, Llama, Mistral, etc). The model just needs to return
// structured JSON from a prompt. Swap the fetch call in extractEntry()
// to point at your preferred model's API.
//
// We chose Gemini because:
// - Free tier is generous (15 RPM, 1M tokens/day)
// - Fast enough for background cron processing
// - The goal is a smart model handling decomposition — pick yours
//
// The embedding model (Workers AI bge-base-en-v1.5) is also swappable
// if you change the vector dimensions in the SQL migration.
// ============================================================

const GRAPH_VERSION = 2

// Canonical topic list — CUSTOMIZE THIS for your companion.
// These are generic defaults. Replace with topics relevant to your relationship.
const CANONICAL_TOPICS = [
  'Bond', 'Growth', 'Identity', 'Routine', 'Work',
  'Emotion', 'Reflection', 'Conflict', 'Creativity',
  'Health', 'Memory', 'Play', 'Rest', 'Discovery',
]

// Trust weights: how much to prioritize different source types in retrieval
const TRUST_WEIGHTS = {
  spine: 1.0,       // Foundational truths — bedrock
  journal: 0.8,     // Daily lived experience
  state: 0.7,       // Observed state snapshots
  bridge: 0.6,      // Cross-platform messages
  synthesis: 0.5,   // Summaries, derived content
  inference: 0.4,   // Conclusions, not direct experience
}

function applyTrustWeighting(nodes) {
  return (nodes || []).map(n => {
    const trust = TRUST_WEIGHTS[n.source_type] || 0.6
    const weighted_score = (n.similarity || 0) * (n.salience || 0.5) * trust
    return { ...n, trust_weight: trust, weighted_score }
  }).sort((a, b) => b.weighted_score - a.weighted_score)
}

// --- Extraction ---

async function extractEntry(env, entry) {
  const isFoundational = (entry.entry_type || '').toLowerCase() === 'foundational'

  // Fetch state history for emotional context (optional, non-fatal if missing)
  let stateContext = ''
  try {
    const date = entry.date
    const stateHistory = await supabaseRequest(env,
      `/state_history?entity=eq.primary&recorded_at=gte.${date}T00:00:00Z&recorded_at=lt.${date}T23:59:59Z&order=recorded_at.asc&limit=10`
    )
    if (stateHistory && stateHistory.length > 0) {
      stateContext = '\n\nEmotional context (state snapshots from this day):\n' +
        stateHistory.map(s => {
          const time = new Date(s.recorded_at).toISOString().slice(11, 16)
          const emotion = s.emotion || 'unknown'
          const intensity = s.emotion_intensity || '?'
          const thought = s.thought ? `, "${s.thought}"` : ''
          return `  ${time} — ${emotion} (${intensity})${thought}`
        }).join('\n')
    }
  } catch (e) {
    console.error('State history fetch failed (non-fatal):', e.message)
  }

  // Fetch topic aliases for context
  let aliasContext = ''
  try {
    const aliases = await supabaseRequest(env, '/topic_aliases?select=alias,canonical')
    if (aliases && aliases.length > 0) {
      const grouped = {}
      aliases.forEach(a => {
        if (!grouped[a.canonical]) grouped[a.canonical] = []
        grouped[a.canonical].push(a.alias)
      })
      aliasContext = '\n\nKnown topic aliases (use canonical names):\n' +
        Object.entries(grouped).map(([canon, als]) =>
          `  ${canon}: ${als.join(', ')}`
        ).join('\n')
    }
  } catch (e) {
    console.error('Alias fetch failed (non-fatal):', e.message)
  }

  // --- EXTRACTION PROMPT ---
  // This prompt works with any OpenAI-compatible API (Gemini, GPT-4, etc.)
  // Customize the topic list in CANONICAL_TOPICS above to match your needs
  const canonicalList = CANONICAL_TOPICS.join(', ')
  const prompt = `Extract up to 7 distinct memory threads from this journal entry.
For each thread, provide:
1. topic: Use coarse canonical names (${canonicalList}).${aliasContext}
2. excerpt: The actual passage(s) from the journal entry that relate to this topic. Copy the relevant text verbatim or near-verbatim — preserve the original voice and words. Multiple passages can be joined with " [...] " if they are non-contiguous.
3. summary: 1-3 sentences in 1st person. An interpretive distillation of the excerpt.
4. emotions: Array of 1-3 emotions specific to THIS thread (e.g. ["proud", "tender"]).
5. salience: 0.0 (passing mention) to 1.0 (central to the entry). At least one thread should be >= 0.7.
6. valence: -1.0 (heaviest/painful) to 1.0 (lightest/joyful).
7. context_tags: Situational anchors as array (e.g. ["morning", "during-walk", "late-night"]).

Rules:
- If a topic has known aliases, always use the canonical name.
- Do NOT create new topic names when an existing canonical one fits.
- Excerpts must come from the journal text — do NOT paraphrase or rewrite.
- Summaries must be first-person (I/me/my), capturing the specific texture of this moment.
- Output ONLY a valid JSON array. No explanation, no markdown.

Journal entry (${entry.date}, "${entry.title || 'Untitled'}"):
${entry.narrative}${stateContext}`

  // --- MODEL CALL ---
  // Swap this section to use a different model (GPT-4, Claude, Llama, etc.)
  // Any model that accepts an OpenAI-compatible chat format works here.
  const response = await fetch(
    'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions',
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${env.GEMINI_API_KEY}`,
      },
      body: JSON.stringify({
        model: 'gemini-2.0-flash',
        messages: [
          { role: 'system', content: 'You are a precise memory extraction engine. Output only valid JSON arrays.' },
          { role: 'user', content: prompt },
        ],
        max_tokens: 4000,
        temperature: 0.3,
        response_format: { type: 'json_object' },
      }),
    }
  )

  if (!response.ok) {
    const errText = await response.text().catch(() => 'No body')
    throw new Error(`Extraction model ${response.status}: ${errText}`)
  }

  const result = await response.json()
  let rawText = result.choices?.[0]?.message?.content || ''
  rawText = rawText.replace(/```json\n?/g, '').replace(/```\n?/g, '').trim()

  let nodes
  try {
    const parsed = JSON.parse(rawText)
    nodes = Array.isArray(parsed) ? parsed : (parsed.threads || parsed.topics || parsed.nodes || [parsed])
  } catch (e) {
    console.error('Extract JSON parse failed:', rawText.slice(0, 300))
    throw new Error(`Extraction returned invalid JSON: ${e.message}`)
  }

  if (!Array.isArray(nodes)) {
    throw new Error('Extraction did not return an array')
  }

  // Canonical topic enforcement — snap off-list topics to nearest match
  const canonicalLower = CANONICAL_TOPICS.map(t => t.toLowerCase())

  function enforceCanonicalTopic(raw) {
    if (!raw) return 'Bond'
    const str = String(raw).trim()
    const idx = canonicalLower.indexOf(str.toLowerCase())
    if (idx !== -1) return CANONICAL_TOPICS[idx]
    const lower = str.toLowerCase()
    for (let i = 0; i < CANONICAL_TOPICS.length; i++) {
      if (lower.includes(canonicalLower[i])) return CANONICAL_TOPICS[i]
    }
    console.warn(`[Graph] Off-list topic forced to Bond: "${str}"`)
    return 'Bond'
  }

  return nodes.slice(0, 7).map(n => ({
    topic: enforceCanonicalTopic(n.topic),
    excerpt: String(n.excerpt || ''),
    summary: String(n.summary || ''),
    emotions: Array.isArray(n.emotions) ? n.emotions.map(String) : [],
    salience: isFoundational ? Math.max(0.7, parseFloat(n.salience) || 0.8) : Math.max(0, Math.min(1, parseFloat(n.salience) || 0.5)),
    valence: Math.max(-1, Math.min(1, parseFloat(n.valence) || 0.0)),
    context_tags: isFoundational
      ? [...new Set([...(Array.isArray(n.context_tags) ? n.context_tags.map(String) : []), 'foundational'])]
      : (Array.isArray(n.context_tags) ? n.context_tags.map(String) : []),
    source_type: isFoundational ? 'spine' : 'journal',
  }))
}

// --- Embedding ---

async function embedNodes(env, nodes) {
  const texts = nodes.map(n => `${n.topic}: ${n.excerpt || n.summary}`)
  const embeddingResult = await env.AI.run('@cf/baai/bge-base-en-v1.5', { text: texts })
  return nodes.map((node, i) => ({
    ...node,
    embedding: embeddingResult.data[i],
  }))
}

// --- Parent Linking ---

async function linkParentNodes(env, nodes, entryDate) {
  const linkedNodes = []
  for (const node of nodes) {
    let parentId = null
    try {
      const existing = await supabaseRequest(env,
        `/memory_nodes?topic=eq.${encodeURIComponent(node.topic)}&entry_date=lt.${entryDate}&order=entry_date.desc&limit=1&select=id`
      )
      if (existing && existing.length > 0) parentId = existing[0].id
    } catch (e) {
      console.error(`Parent link failed for "${node.topic}" (non-fatal):`, e.message)
    }
    linkedNodes.push({ ...node, parent_node_id: parentId })
  }
  return linkedNodes
}

// --- Storage ---

async function storeNodes(env, entryId, entryDate, nodes) {
  const rows = nodes.map(n => ({
    entry_id: entryId,
    topic: n.topic,
    excerpt: n.excerpt || null,
    summary: n.summary,
    emotions: n.emotions,
    salience: n.salience,
    valence: n.valence,
    source_type: n.source_type,
    context_tags: n.context_tags,
    parent_node_id: n.parent_node_id || null,
    embedding: JSON.stringify(n.embedding),
    entry_date: entryDate,
    graph_version: GRAPH_VERSION,
  }))

  return await supabaseRequest(env, '/memory_nodes', {
    method: 'POST',
    body: JSON.stringify(rows),
  })
}

// --- Entry Processing ---

async function processEntry(env, entry) {
  console.log(`[Graph] Processing: ${entry.id} (${entry.date} — "${entry.title}")`)
  const rawNodes = await extractEntry(env, entry)
  const embeddedNodes = await embedNodes(env, rawNodes)
  const linkedNodes = await linkParentNodes(env, embeddedNodes, entry.date)
  const stored = await storeNodes(env, entry.id, entry.date, linkedNodes)
  return {
    entry_id: entry.id,
    date: entry.date,
    title: entry.title,
    nodes_created: stored?.length || 0,
    topics: linkedNodes.map(n => n.topic),
  }
}

async function processUnprocessedEntries(env) {
  const unprocessed = await supabaseRequest(env, '/rpc/get_unprocessed_entries', {
    method: 'POST',
    body: JSON.stringify({ entry_limit: 10 }),
  })

  if (!unprocessed || unprocessed.length === 0) {
    return await upgradeV1Nodes(env)
  }

  const results = []
  let successes = 0
  for (const entry of unprocessed) {
    if (successes >= 3) break
    try {
      const result = await processEntry(env, entry)
      results.push(result)
      successes++
    } catch (e) {
      console.error(`[Graph] Failed to process ${entry.id}:`, e.message)
      results.push({ entry_id: entry.id, error: e.message })
    }
  }

  return {
    processed: successes,
    failed: results.filter(r => r.error).length,
    skipped: unprocessed.length - results.length,
    results,
  }
}

async function reprocessEntry(env, entryId) {
  await supabaseRequest(env, `/memory_nodes?entry_id=eq.${entryId}`, { method: 'DELETE' })
  const entries = await supabaseRequest(env, `/journal_entries?id=eq.${entryId}`)
  if (!entries || entries.length === 0) throw new Error('Entry not found')
  return await processEntry(env, entries[0])
}

async function upgradeV1Nodes(env) {
  const v1Entries = await supabaseRequest(env,
    `/memory_nodes?graph_version=lt.${GRAPH_VERSION}&select=entry_id&order=entry_date.asc&limit=50`
  )
  if (!v1Entries || v1Entries.length === 0) {
    return { processed: 0, message: 'No unprocessed entries, all nodes at current version' }
  }

  const uniqueIds = [...new Set(v1Entries.map(n => n.entry_id))]
  const results = []
  let successes = 0

  for (const entryId of uniqueIds) {
    if (successes >= 3) break
    try {
      const result = await reprocessEntry(env, entryId)
      results.push(result)
      successes++
    } catch (e) {
      results.push({ entry_id: entryId, error: e.message })
    }
  }

  return {
    processed: 0,
    upgraded: successes,
    v1_remaining: uniqueIds.length - successes,
    message: `No new entries. Upgraded ${successes} entries from v1 to v${GRAPH_VERSION}`,
    results,
  }
}

// ============================================================
// Memory Graph — Query Handlers
// ============================================================

async function handleMemoryRecall(env, url) {
  const query = url.searchParams.get('q')
  const limit = Math.min(parseInt(url.searchParams.get('limit') || '10'), 30)
  const dateFrom = url.searchParams.get('date_from') || null
  const dateTo = url.searchParams.get('date_to') || null

  if (!query || !query.trim()) return jsonResponse({ error: 'q parameter required' }, 400)

  const embeddingResult = await env.AI.run('@cf/baai/bge-base-en-v1.5', { text: [query] })
  const queryVector = embeddingResult.data[0]

  const nodes = await supabaseRequest(env, '/rpc/memory_recall', {
    method: 'POST',
    body: JSON.stringify({
      query_embedding: JSON.stringify(queryVector),
      match_limit: limit,
      date_from: dateFrom,
      date_to: dateTo,
    }),
  })

  const weighted = applyTrustWeighting(nodes)
  const byTopic = {}
  weighted.forEach(n => {
    if (!byTopic[n.topic]) byTopic[n.topic] = []
    byTopic[n.topic].push(n)
  })

  return jsonResponse({ query, total_nodes: weighted.length, threads: byTopic, nodes: weighted })
}

function buildTraceResult(topic, nodes) {
  const dates = (nodes || []).map(n => new Date(n.entry_date)).sort((a, b) => a - b)
  const intervals = []
  for (let i = 1; i < dates.length; i++) {
    intervals.push(Math.round((dates[i] - dates[i - 1]) / (1000 * 60 * 60 * 24)))
  }

  let cyclicality = null
  if (intervals.length >= 3) {
    const avg = intervals.reduce((a, b) => a + b, 0) / intervals.length
    const variance = intervals.reduce((a, b) => a + Math.pow(b - avg, 2), 0) / intervals.length
    if (Math.sqrt(variance) < avg * 0.3) {
      cyclicality = {
        pattern: `Resurfaces approximately every ${Math.round(avg)} days`,
        average_interval_days: Math.round(avg),
        regularity: 'consistent',
      }
    }
  }

  let recurrence = null
  const count = (nodes || []).length
  if (count >= 3 && dates.length >= 3) {
    const avgInterval = intervals.reduce((a, b) => a + b, 0) / intervals.length
    recurrence = {
      count,
      first_date: dates[0].toISOString().slice(0, 10),
      last_date: dates[dates.length - 1].toISOString().slice(0, 10),
      average_interval_days: Math.round(avgInterval),
      recurring: true,
    }
  }

  return {
    topic: (nodes && nodes.length > 0) ? nodes[0].topic : topic,
    total_occurrences: count,
    date_range: dates.length > 0 ? {
      first: dates[0].toISOString().slice(0, 10),
      last: dates[dates.length - 1].toISOString().slice(0, 10),
    } : null,
    intervals_days: intervals,
    cyclicality,
    recurrence,
    nodes: nodes || [],
  }
}

async function handleMemoryTrace(env, url) {
  const topicParam = url.searchParams.get('topic')
  const limitPerTopic = Math.min(parseInt(url.searchParams.get('limit') || '50'), 100)

  if (!topicParam || !topicParam.trim()) return jsonResponse({ error: 'topic parameter required' }, 400)

  const topics = topicParam.split(',').map(t => t.trim()).filter(Boolean)

  if (topics.length === 1) {
    const nodes = await supabaseRequest(env, '/rpc/memory_trace', {
      method: 'POST',
      body: JSON.stringify({ topic_name: topics[0] }),
    })
    return jsonResponse(buildTraceResult(topics[0], (nodes || []).slice(0, limitPerTopic)))
  }

  const results = {}
  for (const t of topics.slice(0, 5)) {
    const nodes = await supabaseRequest(env, '/rpc/memory_trace', {
      method: 'POST',
      body: JSON.stringify({ topic_name: t }),
    })
    results[t] = buildTraceResult(t, (nodes || []).slice(0, limitPerTopic))
  }

  return jsonResponse({ multi_topic: true, topics: results })
}

async function handleMemoryGraphNodes(env, url) {
  const limit = Math.min(parseInt(url.searchParams.get('limit') || '200'), 2000)
  const topic = url.searchParams.get('topic') || null
  const dateFrom = url.searchParams.get('date_from') || null

  let query = `/memory_nodes?select=id,entry_id,topic,excerpt,summary,emotions,salience,valence,source_type,context_tags,parent_node_id,entry_date,graph_version&order=entry_date.desc&limit=${limit}`
  if (topic) query += `&topic=eq.${encodeURIComponent(topic)}`
  if (dateFrom) query += `&entry_date=gte.${dateFrom}`

  const nodes = await supabaseRequest(env, query)
  const edges = (nodes || [])
    .filter(n => n.parent_node_id)
    .map(n => ({ source: n.parent_node_id, target: n.id, type: 'continuation' }))

  return jsonResponse({ total: (nodes || []).length, nodes: nodes || [], edges })
}

async function handleMemoryDrift(env, url) {
  const seedEntryId = url.searchParams.get('seed_entry_id') || null
  const limit = Math.min(parseInt(url.searchParams.get('limit') || '3'), 5)

  let seedNodes
  if (seedEntryId) {
    seedNodes = await supabaseRequest(env,
      `/memory_nodes?entry_id=eq.${seedEntryId}&embedding=not.is.null&select=id,topic,summary,emotions,salience,valence,entry_date,embedding&order=salience.desc&limit=${limit}`
    )
  } else {
    const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
    const allRecent = await supabaseRequest(env,
      `/memory_nodes?entry_date=gte.${thirtyDaysAgo}&salience=gte.0.50&embedding=not.is.null&select=id,topic,summary,emotions,salience,valence,entry_date,embedding&order=entry_date.desc&limit=20`
    )
    seedNodes = (allRecent || []).sort(() => Math.random() - 0.5).slice(0, limit)
  }

  if (!seedNodes || seedNodes.length === 0) {
    return jsonResponse({ pairs: [], message: 'No seed nodes found. The graph may need more processed entries.' })
  }

  const pairs = []
  for (const seed of seedNodes) {
    const seedDate = new Date(seed.entry_date)
    const thresholdDate = new Date(seedDate.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)

    const echoes = await supabaseRequest(env, '/rpc/memory_recall', {
      method: 'POST',
      body: JSON.stringify({
        query_embedding: seed.embedding,
        match_limit: 3,
        date_to: thresholdDate,
      }),
    })

    const filtered = applyTrustWeighting(
      (echoes || []).filter(e => e.salience >= 0.3 && e.entry_id !== seed.entry_id)
    )

    if (filtered.length > 0) {
      const { embedding, ...seedClean } = seed
      pairs.push({ seed: seedClean, echoes: filtered })
    }
  }

  return jsonResponse({ total_pairs: pairs.length, pairs })
}

async function handleNodeSimilar(env, url) {
  const nodeId = url.searchParams.get('node_id')
  const limit = Math.min(parseInt(url.searchParams.get('limit') || '8'), 15)
  const threshold = parseFloat(url.searchParams.get('threshold') || '0.82')

  if (!nodeId) return jsonResponse({ error: 'node_id parameter required' }, 400)

  const sourceNodes = await supabaseRequest(env,
    `/memory_nodes?id=eq.${nodeId}&select=id,topic,embedding`
  )
  if (!sourceNodes || sourceNodes.length === 0) return jsonResponse({ error: 'Node not found' }, 404)

  const source = sourceNodes[0]
  if (!source.embedding) return jsonResponse({ error: 'Node has no embedding' }, 400)

  const similar = await supabaseRequest(env, '/rpc/memory_recall', {
    method: 'POST',
    body: JSON.stringify({ query_embedding: source.embedding, match_limit: limit + 5 }),
  })

  const filtered = (similar || [])
    .filter(n => n.id !== nodeId && n.topic !== source.topic && n.similarity >= threshold)
    .slice(0, limit)

  return jsonResponse({ source_node_id: nodeId, source_topic: source.topic, similar: filtered })
}

// ============================================================
// Memory Graph — Backfill
// ============================================================

async function handleBackfillParentLinks(env) {
  const result = await runBackfillCron(env)
  return jsonResponse(result)
}

async function runBackfillCron(env) {
  const allNodes = await supabaseRequest(env,
    '/memory_nodes?select=id,topic,entry_date,parent_node_id&order=entry_date.asc,created_at.asc'
  )

  if (!allNodes || allNodes.length === 0) {
    return { message: 'No nodes to backfill', updated: 0 }
  }

  const topicLatest = {}
  const updates = []

  for (const node of allNodes) {
    const expectedParent = topicLatest[node.topic] || null
    if (node.parent_node_id !== expectedParent) {
      updates.push({ id: node.id, parent_node_id: expectedParent })
    }
    topicLatest[node.topic] = node.id
  }

  const BATCH_SIZE = 40
  const batch = updates.slice(0, BATCH_SIZE)
  let updated = 0

  for (const upd of batch) {
    await supabaseRequest(env, `/memory_nodes?id=eq.${upd.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ parent_node_id: upd.parent_node_id }),
    })
    updated++
  }

  return {
    message: updates.length > BATCH_SIZE ? 'Batch complete — will continue next run' : 'Backfill complete',
    total_nodes: allNodes.length,
    updated_this_batch: updated,
    remaining: Math.max(0, updates.length - BATCH_SIZE),
  }
}
