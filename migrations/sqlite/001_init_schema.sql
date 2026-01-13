-- Yral AI Chat SQLite Schema
-- Version: 1.0.0

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- AI Influencers Table
CREATE TABLE IF NOT EXISTS ai_influencers (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    avatar_url TEXT,
    description TEXT,
    category TEXT,
    system_instructions TEXT NOT NULL,
    personality_traits TEXT DEFAULT '{}',
    initial_greeting TEXT,
    suggested_messages TEXT DEFAULT '[]',
    is_active TEXT DEFAULT 'active',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    metadata TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_influencers_name ON ai_influencers(name);
CREATE INDEX IF NOT EXISTS idx_influencers_category ON ai_influencers(category);
CREATE INDEX IF NOT EXISTS idx_influencers_active ON ai_influencers(is_active);

-- Conversations Table
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    influencer_id TEXT NOT NULL REFERENCES ai_influencers(id) ON DELETE CASCADE,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    metadata TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_influencer_id ON conversations(influencer_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_user_influencer ON conversations(user_id, influencer_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at DESC);

-- Messages Table
-- message_type: 'text', 'multimodal', 'image', 'audio'
-- role: 'user', 'assistant'
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT,
    message_type TEXT NOT NULL CHECK(message_type IN ('text', 'multimodal', 'image', 'audio')),
    media_urls TEXT DEFAULT '[]',
    audio_url TEXT,
    audio_duration_seconds INTEGER,
    token_count INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    metadata TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON messages(conversation_id, created_at DESC);

-- Trigger to update updated_at on conversations when messages are added
CREATE TRIGGER IF NOT EXISTS trigger_update_conversation_timestamp
AFTER INSERT ON messages
BEGIN
    UPDATE conversations SET updated_at = datetime('now') WHERE id = NEW.conversation_id;
END;

-- Trigger to update updated_at on ai_influencers when updated
CREATE TRIGGER IF NOT EXISTS trigger_update_influencer_timestamp
AFTER UPDATE ON ai_influencers
BEGIN
    UPDATE ai_influencers SET updated_at = datetime('now') WHERE id = OLD.id;
END;

-- Triggers to validate is_active enum values (drop first to ensure correct validation)
DROP TRIGGER IF EXISTS trigger_validate_influencer_status;
DROP TRIGGER IF EXISTS trigger_validate_influencer_status_update;

CREATE TRIGGER trigger_validate_influencer_status
BEFORE INSERT ON ai_influencers
BEGIN
    SELECT CASE
        WHEN NEW.is_active NOT IN ('active', 'coming_soon', 'discontinued') THEN
            RAISE(ABORT, 'Invalid is_active value. Must be one of: active, coming_soon, discontinued')
    END;
END;

CREATE TRIGGER trigger_validate_influencer_status_update
BEFORE UPDATE ON ai_influencers
BEGIN
    SELECT CASE
        WHEN NEW.is_active NOT IN ('active', 'coming_soon', 'discontinued') THEN
            RAISE(ABORT, 'Invalid is_active value. Must be one of: active, coming_soon, discontinued')
    END;
END;