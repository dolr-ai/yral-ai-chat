-- Add suggested_messages column to ai_influencers
-- Date: December 2025

ALTER TABLE ai_influencers
ADD COLUMN IF NOT EXISTS suggested_messages TEXT DEFAULT '[]';

-- Ensure existing rows have a non-NULL default (idempotent)
UPDATE ai_influencers
SET suggested_messages = COALESCE(suggested_messages, '[]');
