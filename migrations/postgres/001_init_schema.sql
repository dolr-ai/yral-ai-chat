-- Yral AI Chat PostgreSQL Schema
-- Version: 1.0.0
-- Ported from SQLite

-- Enable UUID extension (optional, but good to have)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Function to update timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- AI Influencers Table
CREATE TABLE IF NOT EXISTS ai_influencers (
    id TEXT PRIMARY KEY, -- Can be UUID or IC Principal ID
    name TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    avatar_url TEXT,
    description TEXT,
    category TEXT,
    system_instructions TEXT NOT NULL,
    personality_traits JSONB DEFAULT '{}',
    initial_greeting TEXT,
    suggested_messages JSONB DEFAULT '[]',
    is_active TEXT DEFAULT 'active' CHECK (is_active IN ('active', 'coming_soon', 'discontinued')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_influencers_name ON ai_influencers(name);
CREATE INDEX IF NOT EXISTS idx_influencers_category ON ai_influencers(category);
CREATE INDEX IF NOT EXISTS idx_influencers_active ON ai_influencers(is_active);

-- Conversations Table
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    influencer_id TEXT NOT NULL REFERENCES ai_influencers(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_influencer_id ON conversations(influencer_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_user_influencer ON conversations(user_id, influencer_id);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at DESC);

-- Messages Table
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT,
    message_type TEXT NOT NULL CHECK (message_type IN ('text', 'multimodal', 'image', 'audio')),
    media_urls JSONB DEFAULT '[]',
    audio_url TEXT,
    audio_duration_seconds INTEGER,
    token_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_created ON messages(conversation_id, created_at DESC);

-- Triggers for updated_at
CREATE TRIGGER update_influencer_timestamp
    BEFORE UPDATE ON ai_influencers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_conversation_timestamp
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to update conversation timestamp when message is added
CREATE OR REPLACE FUNCTION update_conversation_timestamp_on_message()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE conversations SET updated_at = NOW() WHERE id = NEW.conversation_id;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER trigger_update_conversation_on_message
    AFTER INSERT ON messages
    FOR EACH ROW
    EXECUTE FUNCTION update_conversation_timestamp_on_message();
