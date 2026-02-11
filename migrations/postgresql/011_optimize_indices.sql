-- Optimization: Remove duplicate indexes and add GIN indexes for JSONB
-- Version: 1.1.0

-- 1. Remove duplicate index on messages
DROP INDEX IF EXISTS idx_messages_conversation_created; -- Duplicate of idx_messages_conv_created (or similar)

-- Keep idx_messages_conv_created as primary (if it exists)
-- Ensure we have the optimal index: (conversation_id, created_at DESC)
-- Check if it exists, if not create it (safe DDL)
CREATE INDEX IF NOT EXISTS idx_messages_conv_created_at_desc 
ON messages(conversation_id, created_at DESC);

-- 2. Add GIN indexes for JSONB columns to enable fast filtering/search
CREATE INDEX IF NOT EXISTS idx_influencers_metadata 
ON ai_influencers USING GIN (metadata);

CREATE INDEX IF NOT EXISTS idx_influencers_personality 
ON ai_influencers USING GIN (personality_traits);

CREATE INDEX IF NOT EXISTS idx_messages_metadata 
ON messages USING GIN (metadata);

-- 3. Add Partial Index for Active Influencers (Optimization for "list active" queries)
CREATE INDEX IF NOT EXISTS idx_influencers_active_status 
ON ai_influencers(id) 
WHERE is_active = 'active';
