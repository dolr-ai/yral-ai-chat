-- Migration: Add initial_greeting column to ai_influencers
-- Version: 2.0.0

-- Add initial_greeting column to ai_influencers table
ALTER TABLE ai_influencers
ADD COLUMN initial_greeting TEXT DEFAULT NULL;

-- Add comment for documentation
COMMENT ON COLUMN ai_influencers.initial_greeting IS 'Initial greeting message sent when a new conversation is created with this influencer';


