-- Performance Optimization Indexes
-- Version: 1.0.0
-- Created: 2026-01-16

-- Composite index for conversation list queries (user_id + updated_at DESC)
-- Speeds up: list_conversations endpoint
CREATE INDEX IF NOT EXISTS idx_conversations_user_updated 
ON conversations(user_id, updated_at DESC);

-- Composite index for message queries with conversation
-- Speeds up: fetching recent messages per conversation
CREATE INDEX IF NOT EXISTS idx_messages_conv_created 
ON messages(conversation_id, created_at DESC);

-- Index for active influencer lookups with ordering
-- Speeds up: list_influencers endpoint
CREATE INDEX IF NOT EXISTS idx_influencers_active_created
ON ai_influencers(is_active, created_at DESC);

-- Index for message role filtering (if needed for analytics)
CREATE INDEX IF NOT EXISTS idx_messages_role
ON messages(role);
