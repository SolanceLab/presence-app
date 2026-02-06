-- ============================================================
-- STATE HISTORY
-- Append-only log of all state changes
-- Populated automatically via database triggers
-- Run in Supabase SQL Editor
-- ============================================================

CREATE TABLE IF NOT EXISTS state_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  entity TEXT NOT NULL CHECK (entity IN ('primary', 'partner')),

  -- State snapshot
  room TEXT,
  emotion TEXT,
  emotion_intensity INTEGER,
  secondary_emotion TEXT,
  activity TEXT,
  thought TEXT,

  -- Partner-specific
  mood TEXT,
  physical_state TEXT,

  -- Tracking
  updated_by TEXT NOT NULL,
  recorded_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_state_history_time
  ON state_history(recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_state_history_entity
  ON state_history(entity, recorded_at DESC);


-- ============================================================
-- TRIGGER: Auto-log primary entity state changes
-- ============================================================

CREATE OR REPLACE FUNCTION log_primary_state_change()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO state_history (
    entity, room, emotion, emotion_intensity, secondary_emotion,
    activity, thought, updated_by
  ) VALUES (
    'primary',
    NEW.current_room,
    NEW.primary_emotion,
    NEW.emotion_intensity,
    NEW.secondary_emotion,
    NEW.current_activity,
    NEW.thought_bubble,
    NEW.last_updated_by
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_primary_state_history ON primary_entity_state;
CREATE TRIGGER trigger_primary_state_history
  AFTER UPDATE ON primary_entity_state
  FOR EACH ROW
  EXECUTE FUNCTION log_primary_state_change();


-- ============================================================
-- TRIGGER: Auto-log partner entity state changes
-- ============================================================

CREATE OR REPLACE FUNCTION log_partner_state_change()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO state_history (
    entity, room, activity, mood, physical_state, updated_by
  ) VALUES (
    'partner',
    NEW.current_room,
    NEW.current_activity,
    NEW.mood,
    NEW.physical_state,
    NEW.last_updated_by
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_partner_state_history ON partner_entity_state;
CREATE TRIGGER trigger_partner_state_history
  AFTER UPDATE ON partner_entity_state
  FOR EACH ROW
  EXECUTE FUNCTION log_partner_state_change();
