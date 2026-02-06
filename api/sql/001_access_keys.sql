-- ============================================================
-- ACCESS KEYS
-- API authentication via Bearer tokens
-- Run in Supabase SQL Editor
-- ============================================================

CREATE TABLE IF NOT EXISTS access_keys (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  platform TEXT NOT NULL UNIQUE,
  key TEXT NOT NULL,
  permissions TEXT[] DEFAULT ARRAY['read'],
  status TEXT DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  rotated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE access_keys ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access" ON access_keys
  FOR ALL
  USING (true)
  WITH CHECK (true);

-- Generate keys for your AI platforms
-- Adjust platforms to match your setup (e.g., 'claude', 'chatgpt', 'browser')
INSERT INTO access_keys (platform, key, permissions) VALUES
  ('claude', encode(gen_random_bytes(32), 'hex'), ARRAY['read', 'write']),
  ('chatgpt', encode(gen_random_bytes(32), 'hex'), ARRAY['read', 'write']),
  ('browser', encode(gen_random_bytes(16), 'hex'), ARRAY['read'])
ON CONFLICT (platform) DO NOTHING;

-- After running, retrieve your keys:
-- SELECT platform, key, permissions, status FROM access_keys;
