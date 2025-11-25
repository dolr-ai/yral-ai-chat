-- Yral AI Chat Database Schema
-- Version: 1.0.0

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create ENUM types
CREATE TYPE message_type_enum AS ENUM ('text', 'multimodal', 'image', 'audio');
CREATE TYPE message_role_enum AS ENUM ('user', 'assistant');

-- AI Influencers Table
CREATE TABLE ai_influencers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    avatar_url TEXT,
    description TEXT,
    category VARCHAR(100),
    system_instructions TEXT NOT NULL,
    personality_traits JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Create index on name for faster lookups
CREATE INDEX idx_influencers_name ON ai_influencers(name);
CREATE INDEX idx_influencers_category ON ai_influencers(category);
CREATE INDEX idx_influencers_active ON ai_influencers(is_active) WHERE is_active = true;

-- Conversations Table
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,
    influencer_id UUID NOT NULL REFERENCES ai_influencers(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Create indexes for conversations
CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_conversations_influencer_id ON conversations(influencer_id);
CREATE INDEX idx_conversations_user_influencer ON conversations(user_id, influencer_id);
CREATE INDEX idx_conversations_updated_at ON conversations(updated_at DESC);

-- Ensure one conversation per user-influencer pair
CREATE UNIQUE INDEX idx_unique_user_influencer ON conversations(user_id, influencer_id);

-- Messages Table
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role message_role_enum NOT NULL,
    content TEXT,
    message_type message_type_enum NOT NULL,
    media_urls JSONB DEFAULT '[]',
    audio_url TEXT,
    audio_duration_seconds INTEGER,
    token_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Create indexes for messages
CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_role ON messages(role);
CREATE INDEX idx_messages_created_at ON messages(created_at DESC);
CREATE INDEX idx_messages_conversation_created ON messages(conversation_id, created_at DESC);

-- Trigger to update updated_at on conversations
CREATE OR REPLACE FUNCTION update_conversation_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE conversations 
    SET updated_at = NOW() 
    WHERE id = NEW.conversation_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_conversation_timestamp
AFTER INSERT ON messages
FOR EACH ROW
EXECUTE FUNCTION update_conversation_timestamp();

-- Trigger to update updated_at on ai_influencers
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_influencer_timestamp
BEFORE UPDATE ON ai_influencers
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

-- Add comments for documentation
COMMENT ON TABLE ai_influencers IS 'AI influencer personas with unique personalities';
COMMENT ON TABLE conversations IS 'User conversations with AI influencers';
COMMENT ON TABLE messages IS 'Individual messages in conversations (user and assistant)';

COMMENT ON COLUMN messages.content IS 'Message text content. For audio messages, stores transcription prefixed with [Transcribed: ]';
COMMENT ON COLUMN messages.media_urls IS 'JSON array of media URLs for multimodal/image messages';
COMMENT ON COLUMN messages.audio_url IS 'URL to audio file for voice messages';
COMMENT ON COLUMN messages.token_count IS 'Number of tokens in assistant responses (for analytics)';


