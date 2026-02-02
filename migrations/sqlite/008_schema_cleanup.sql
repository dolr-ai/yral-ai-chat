-- Schema Cleanup Migration
-- Version: 1.0.0
-- Created: 2026-01-30
-- 
-- This migration safely removes redundant triggers and notes on duplicate indexes.
-- All DROP statements use IF EXISTS to ensure idempotence.

-- 1. Remove the trigger that auto-updates ai_influencers.updated_at
--    Rationale: This adds write overhead. Influencer updates are rare and 
--    can be handled explicitly in the application layer if needed.
DROP TRIGGER IF EXISTS trigger_update_influencer_timestamp;

-- 2. Remove redundant trigger that updates conversation timestamp on every message insert
--    Rationale: This is now handled by the service layer to reduce write lock duration and index overhead.
DROP TRIGGER IF EXISTS trigger_update_conversation_timestamp;

-- NOTE: The following duplicate indexes exist across migrations but are harmless:
--   - idx_messages_role (created in 001 and 007)
--   - idx_conversations_user_updated (created in 004 and 007)
-- 
-- We are NOT dropping these because:
--   1. SQLite's CREATE INDEX IF NOT EXISTS already handles duplicates gracefully.
--   2. Dropping and recreating indexes on large tables can cause temporary write locks.
--   3. The slight redundancy in migration files is preferable to runtime disruption.
