-- Add principal ID indexes (columns are created in 001_init_schema)
-- Version: 1.1.0

-- Index for parent_principal_id as it might be used for filtering
CREATE INDEX IF NOT EXISTS idx_influencers_parent_principal ON ai_influencers(parent_principal_id);
