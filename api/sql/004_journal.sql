-- ============================================================
-- JOURNAL ENTRIES
-- Daily entries with emotions, tones, and narrative
-- Supports append-on-same-day (checkpoint pattern)
-- Run in Supabase SQL Editor
-- ============================================================

CREATE TABLE IF NOT EXISTS journal_entries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  date DATE NOT NULL,
  title TEXT,
  narrative TEXT,
  carrying_forward TEXT,

  -- Arrays for multi-value fields
  emotions TEXT[],
  tones TEXT[],
  platforms TEXT[],

  -- Metadata
  entry_type TEXT DEFAULT 'journal',
  keynotes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_journal_date
  ON journal_entries(date);

CREATE INDEX IF NOT EXISTS idx_journal_time
  ON journal_entries(created_at DESC);

ALTER TABLE journal_entries ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access" ON journal_entries
  FOR ALL USING (true) WITH CHECK (true);
