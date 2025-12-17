-- Add suggested_messages column to ai_influencers
-- Date: December 2025
-- Note: The suggested_messages column is created by the Python
--       migration runner (scripts/run_migrations.py) to maintain
--       compatibility with older SQLite versions that do not
--       support "ALTER TABLE ... ADD COLUMN IF NOT EXISTS".

-- Ensure existing rows have a non-NULL default (idempotent)
UPDATE ai_influencers
SET suggested_messages = COALESCE(suggested_messages, '[]');
