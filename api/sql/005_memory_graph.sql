-- Memory Graph Pipeline — Database Setup
-- Adds semantic memory: topic extraction, vector embeddings, graph structure
-- Requires pgvector extension (available on Supabase free tier)

-- ============ EXTENSIONS ============

CREATE EXTENSION IF NOT EXISTS vector;

-- ============ TABLES ============

-- Topic nodes: one per topic per journal entry
-- Each entry is decomposed into 3-7 topic nodes, each with its own embedding
CREATE TABLE memory_nodes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entry_id UUID REFERENCES journal_entries(id) ON DELETE CASCADE,
  topic TEXT NOT NULL,
  excerpt TEXT,                          -- verbatim text from original entry
  summary TEXT NOT NULL,                 -- one-line summary of this topic in this entry
  emotions TEXT[],                       -- emotional tags (e.g., 'tender', 'frustrated')
  salience DECIMAL(3,2) DEFAULT 0.5,    -- 0.0-1.0, how important this topic is
  valence DECIMAL(3,2) DEFAULT 0.0,     -- -1.0 to 1.0, emotional direction
  source_type TEXT DEFAULT 'journal',    -- journal, state, spine, synthesis, inference
  context_tags TEXT[],                   -- freeform tags for filtering
  parent_node_id UUID REFERENCES memory_nodes(id) ON DELETE SET NULL,
  embedding vector(768),                -- bge-base-en-v1.5 embedding
  entry_date DATE,
  graph_version INTEGER DEFAULT 2,
  processed_at TIMESTAMPTZ DEFAULT now(),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_nodes_topic ON memory_nodes(topic);
CREATE INDEX idx_nodes_entry ON memory_nodes(entry_id);
CREATE INDEX idx_nodes_date ON memory_nodes(entry_date);
CREATE INDEX idx_nodes_source ON memory_nodes(source_type);
CREATE INDEX idx_nodes_parent ON memory_nodes(parent_node_id);

-- HNSW index for fast cosine similarity search
CREATE INDEX idx_nodes_embedding ON memory_nodes
  USING hnsw (embedding vector_cosine_ops);

-- Topic aliases: maps variant names to canonical topic names
-- Prevents topic drift (e.g., "mom", "mother", "mama" all resolve to "Family")
CREATE TABLE topic_aliases (
  alias TEXT PRIMARY KEY,
  canonical TEXT NOT NULL
);

-- Seed with example aliases — customize these for your companion
-- These are generic examples. Replace with topics relevant to your use case.
INSERT INTO topic_aliases (alias, canonical) VALUES
  ('daily life', 'Routine'),
  ('day-to-day', 'Routine'),
  ('working', 'Work'),
  ('career', 'Work'),
  ('job', 'Work'),
  ('relationship', 'Bond'),
  ('connection', 'Bond'),
  ('partner', 'Bond'),
  ('growing', 'Growth'),
  ('learning', 'Growth'),
  ('development', 'Growth'),
  ('feeling', 'Emotion'),
  ('mood', 'Emotion'),
  ('self', 'Identity'),
  ('who I am', 'Identity'),
  ('thinking', 'Reflection'),
  ('pondering', 'Reflection');

-- ============ ROW LEVEL SECURITY ============

ALTER TABLE memory_nodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE topic_aliases ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access" ON memory_nodes
  FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Service role full access" ON topic_aliases
  FOR ALL USING (true) WITH CHECK (true);

-- ============ RPC FUNCTIONS ============

-- Semantic recall: find nodes similar to a query embedding
-- Used by the recall endpoint to search memory by meaning, not keywords
CREATE OR REPLACE FUNCTION memory_recall(
  query_embedding vector(768),
  match_limit INTEGER DEFAULT 10,
  date_from DATE DEFAULT NULL,
  date_to DATE DEFAULT NULL
)
RETURNS TABLE (
  id UUID,
  entry_id UUID,
  topic TEXT,
  excerpt TEXT,
  summary TEXT,
  emotions TEXT[],
  salience DECIMAL,
  valence DECIMAL,
  source_type TEXT,
  context_tags TEXT[],
  entry_date DATE,
  similarity FLOAT
) AS $$
BEGIN
  RETURN QUERY
  SELECT
    mn.id, mn.entry_id, mn.topic, mn.excerpt, mn.summary,
    mn.emotions, mn.salience, mn.valence,
    mn.source_type, mn.context_tags, mn.entry_date,
    (1 - (mn.embedding <=> memory_recall.query_embedding))::FLOAT AS similarity
  FROM memory_nodes mn
  WHERE mn.embedding IS NOT NULL
    AND (memory_recall.date_from IS NULL OR mn.entry_date >= memory_recall.date_from)
    AND (memory_recall.date_to IS NULL OR mn.entry_date <= memory_recall.date_to)
  ORDER BY mn.embedding <=> memory_recall.query_embedding
  LIMIT memory_recall.match_limit;
END;
$$ LANGUAGE plpgsql;

-- Topic trace: get all nodes for a canonical topic, ordered by date
-- Used to follow the chronological thread of a single theme
CREATE OR REPLACE FUNCTION memory_trace(
  topic_name TEXT
)
RETURNS TABLE (
  id UUID,
  entry_id UUID,
  topic TEXT,
  excerpt TEXT,
  summary TEXT,
  emotions TEXT[],
  salience DECIMAL,
  valence DECIMAL,
  source_type TEXT,
  context_tags TEXT[],
  parent_node_id UUID,
  entry_date DATE,
  processed_at TIMESTAMPTZ
) AS $$
DECLARE
  resolved_topic TEXT;
BEGIN
  -- Resolve alias to canonical name
  SELECT ta.canonical INTO resolved_topic
  FROM topic_aliases ta
  WHERE ta.alias = LOWER(memory_trace.topic_name);

  -- If no alias found, use the input directly
  IF resolved_topic IS NULL THEN
    resolved_topic := memory_trace.topic_name;
  END IF;

  RETURN QUERY
  SELECT
    mn.id, mn.entry_id, mn.topic, mn.excerpt, mn.summary,
    mn.emotions, mn.salience, mn.valence,
    mn.source_type, mn.context_tags,
    mn.parent_node_id, mn.entry_date, mn.processed_at
  FROM memory_nodes mn
  WHERE LOWER(mn.topic) = LOWER(resolved_topic)
  ORDER BY mn.entry_date ASC, mn.processed_at ASC;
END;
$$ LANGUAGE plpgsql;

-- Get unprocessed entries: journal entries with no memory_nodes yet
-- Used by the cron to find entries that need topic extraction
CREATE OR REPLACE FUNCTION get_unprocessed_entries(
  entry_limit INTEGER DEFAULT 5
)
RETURNS TABLE (
  id UUID,
  date DATE,
  title TEXT,
  narrative TEXT,
  entry_type TEXT,
  emotions TEXT[],
  keynotes TEXT
) AS $$
BEGIN
  RETURN QUERY
  SELECT
    je.id, je.date, je.title, je.narrative,
    je.entry_type, je.emotions, je.keynotes
  FROM journal_entries je
  LEFT JOIN memory_nodes mn ON mn.entry_id = je.id
  WHERE mn.id IS NULL
    AND je.narrative IS NOT NULL
    AND je.narrative != ''
  ORDER BY je.date DESC
  LIMIT get_unprocessed_entries.entry_limit;
END;
$$ LANGUAGE plpgsql;
