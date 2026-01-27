-- Migration: Add parent principal ID and source to ai_influencers
-- Version: 1.1.0

-- Add parent_principal_id column
ALTER TABLE ai_influencers ADD COLUMN parent_principal_id TEXT;

-- Add source column
ALTER TABLE ai_influencers ADD COLUMN source TEXT;

-- Index for parent_principal_id as it might be used for filtering
CREATE INDEX IF NOT EXISTS idx_influencers_parent_principal ON ai_influencers(parent_principal_id);
