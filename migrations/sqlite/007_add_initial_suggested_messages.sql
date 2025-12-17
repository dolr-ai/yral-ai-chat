-- Add suggested_messages column to ai_influencers
-- Date: December 2025

ALTER TABLE ai_influencers
ADD COLUMN suggested_messages TEXT DEFAULT '[]';

-- Ensure existing rows have a non-NULL default
UPDATE ai_influencers
SET suggested_messages = '[]'
WHERE suggested_messages IS NULL;
