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
