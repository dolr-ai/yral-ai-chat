-- Migration: Add NSFW flag to AI Influencers
-- Version: 005
-- Description: Adds is_nsfw column to support routing NSFW content to OpenRouter

-- Add is_nsfw column to ai_influencers table with default value false
-- Note: Using INTEGER (0/1) for SQLite boolean compatibility
ALTER TABLE ai_influencers ADD COLUMN is_nsfw INTEGER DEFAULT 0;

-- Create index on is_nsfw for efficient filtering
CREATE INDEX IF NOT EXISTS idx_influencers_nsfw ON ai_influencers(is_nsfw);

-- Create index on combination of is_active and is_nsfw for common queries
CREATE INDEX IF NOT EXISTS idx_influencers_active_nsfw ON ai_influencers(is_active, is_nsfw);

-- Mark Savita Bhabhi as NSFW and ensure she's active
UPDATE ai_influencers
SET is_nsfw = 1, is_active = 'active'
WHERE name = 'savita_bhabhi';
