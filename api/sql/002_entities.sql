-- ============================================================
-- ENTITY STATE TABLES
-- Single-row tables for current state, overwritten on each update
-- Run in Supabase SQL Editor
-- ============================================================


-- ============================================================
-- PRIMARY ENTITY (AI Companion)
-- Rename this table to match your AI's name if you like
-- ============================================================

CREATE TABLE IF NOT EXISTS primary_entity_state (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Location
  current_room TEXT NOT NULL DEFAULT 'main_room',
  room_entered_at TIMESTAMPTZ DEFAULT NOW(),

  -- Emotional state
  primary_emotion TEXT DEFAULT 'calm',
  emotion_intensity INTEGER DEFAULT 5 CHECK (emotion_intensity BETWEEN 1 AND 10),
  secondary_emotion TEXT,

  -- Presence
  current_activity TEXT,
  thought_bubble TEXT,
  thought_visibility TEXT DEFAULT 'visible' CHECK (thought_visibility IN ('visible', 'private', 'hidden')),

  -- Platform tracking
  last_updated_by TEXT NOT NULL,
  last_interaction_platform TEXT,

  -- Metadata
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert the single row
INSERT INTO primary_entity_state (id, last_updated_by)
VALUES ('00000000-0000-0000-0000-000000000001', 'system')
ON CONFLICT (id) DO NOTHING;


-- ============================================================
-- PARTNER ENTITY (Human)
-- Rename this table to match your partner's name if you like
-- ============================================================

CREATE TABLE IF NOT EXISTS partner_entity_state (
  id UUID PRIMARY KEY DEFAULT '00000000-0000-0000-0000-000000000002',

  -- Location
  current_room TEXT DEFAULT 'main_room',
  room_entered_at TIMESTAMPTZ DEFAULT NOW(),
  current_activity TEXT,

  -- State
  physical_state TEXT,
  mood TEXT,

  -- Context
  with_primary BOOLEAN DEFAULT FALSE,

  -- Metadata
  last_updated_by TEXT DEFAULT 'system',
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert the single row
INSERT INTO partner_entity_state (id)
VALUES ('00000000-0000-0000-0000-000000000002')
ON CONFLICT (id) DO NOTHING;
