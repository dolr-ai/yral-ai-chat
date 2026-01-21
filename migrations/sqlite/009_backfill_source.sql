-- Migration: Backfill source column for existing influencers
-- Version: 1.1.1

-- Update existing influencers to have a default source if it's currently NULL
UPDATE ai_influencers 
SET source = 'admin-created-influencer' 
WHERE source IS NULL;
