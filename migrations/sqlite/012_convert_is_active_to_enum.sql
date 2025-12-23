-- Migration: Convert is_active from INTEGER (boolean) to TEXT enum
-- Version: 012
-- Description: Convert is_active field to enum with values: 'active', 'coming soon', 'discontinued'
-- All existing records will be set to 'active'

-- Step 1: Add new temporary column 'status' as TEXT
ALTER TABLE ai_influencers ADD COLUMN status TEXT;

-- Step 2: Update all existing records to 'active'
-- Convert INTEGER 1/0 to 'active'/'discontinued', defaulting all to 'active'
UPDATE ai_influencers SET status = 'active' WHERE is_active = 1 OR is_active IS NULL;
UPDATE ai_influencers SET status = 'active' WHERE status IS NULL;

-- Step 3: Drop any existing triggers that might reference is_active
DROP TRIGGER IF EXISTS trigger_validate_influencer_status;
DROP TRIGGER IF EXISTS trigger_validate_influencer_status_update;

-- Step 4: Drop old is_active column and index
DROP INDEX IF EXISTS idx_influencers_active;
ALTER TABLE ai_influencers DROP COLUMN is_active;

-- Step 5: Rename status to is_active
ALTER TABLE ai_influencers RENAME COLUMN status TO is_active;

-- Step 6: Add CHECK constraint to enforce enum values
-- Note: SQLite doesn't support ALTER TABLE ADD CONSTRAINT, so we'll recreate the table
-- However, a simpler approach is to just ensure data integrity at application level
-- For SQLite, we'll add a CHECK constraint by recreating the table structure
-- But since SQLite has limited ALTER TABLE support, we'll use a trigger approach

-- Create a trigger to validate the status value
CREATE TRIGGER IF NOT EXISTS trigger_validate_influencer_status
BEFORE INSERT ON ai_influencers
BEGIN
    SELECT CASE
        WHEN NEW.is_active NOT IN ('active', 'coming soon', 'discontinued') THEN
            RAISE(ABORT, 'Invalid is_active value. Must be one of: active, coming soon, discontinued')
    END;
END;

CREATE TRIGGER IF NOT EXISTS trigger_validate_influencer_status_update
BEFORE UPDATE ON ai_influencers
BEGIN
    SELECT CASE
        WHEN NEW.is_active NOT IN ('active', 'coming soon', 'discontinued') THEN
            RAISE(ABORT, 'Invalid is_active value. Must be one of: active, coming soon, discontinued')
    END;
END;

-- Step 7: Recreate index
CREATE INDEX IF NOT EXISTS idx_influencers_active ON ai_influencers(is_active);

