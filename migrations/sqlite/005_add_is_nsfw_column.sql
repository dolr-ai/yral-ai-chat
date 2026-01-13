-- Add is_nsfw column to ai_influencers table
-- Version: 1.0.1

PRAGMA foreign_keys = OFF;

-- Add column if it doesn't exist (SQLite doesn't support IF NOT EXISTS in ALTER TABLE)
-- But we can just try to add it, or check first.
-- For simplicity and robustness in our migration runner:
ALTER TABLE ai_influencers ADD COLUMN is_nsfw INTEGER DEFAULT 0;

-- Indexes for NSFW filtering
CREATE INDEX IF NOT EXISTS idx_influencers_nsfw ON ai_influencers(is_nsfw);
CREATE INDEX IF NOT EXISTS idx_influencers_active_nsfw ON ai_influencers(is_active, is_nsfw);

PRAGMA foreign_keys = ON;
