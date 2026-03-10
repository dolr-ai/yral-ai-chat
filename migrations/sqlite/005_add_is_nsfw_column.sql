-- Add is_nsfw indexes (column is created in 001_init_schema)
-- Version: 1.0.1

-- Indexes for NSFW filtering
CREATE INDEX IF NOT EXISTS idx_influencers_nsfw ON ai_influencers(is_nsfw);
CREATE INDEX IF NOT EXISTS idx_influencers_active_nsfw ON ai_influencers(is_active, is_nsfw);
