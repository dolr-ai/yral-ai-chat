-- Generated from SQLite Schema

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Table: ai_influencers
CREATE TABLE IF NOT EXISTS ai_influencers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    avatar_url TEXT,
    description TEXT,
    category TEXT,
    system_instructions TEXT NOT NULL,
    personality_traits JSONB DEFAULT '{}',
    initial_greeting TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    suggested_messages JSONB DEFAULT '[]',
    is_active TEXT DEFAULT 'active',
    status TEXT,
    is_nsfw BOOLEAN DEFAULT FALSE,
    parent_principal_id TEXT,
    source TEXT
);

CREATE INDEX idx_influencers_name ON ai_influencers(name);
CREATE INDEX idx_influencers_category ON ai_influencers(category);
CREATE INDEX idx_influencers_active ON ai_influencers(is_active);
CREATE INDEX idx_influencers_nsfw ON ai_influencers(is_nsfw);
CREATE INDEX idx_influencers_active_nsfw ON ai_influencers(is_active, is_nsfw);
CREATE INDEX idx_influencers_active_created
ON ai_influencers(is_active, created_at DESC);
CREATE INDEX idx_influencers_parent_principal ON ai_influencers(parent_principal_id);

-- Table: conversations
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    influencer_id TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    FOREIGN KEY (influencer_id) REFERENCES ai_influencers(id) ON DELETE CASCADE
);

CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_conversations_influencer_id ON conversations(influencer_id);
CREATE UNIQUE INDEX idx_unique_user_influencer ON conversations(user_id, influencer_id);
CREATE INDEX idx_conversations_updated_at ON conversations(updated_at DESC);
CREATE INDEX idx_conversations_user_updated 
ON conversations(user_id, updated_at DESC);
CREATE INDEX idx_conversations_influencer_updated 
ON conversations(influencer_id, updated_at DESC);

-- Table: messages
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT,
    message_type TEXT NOT NULL,
    media_urls JSONB DEFAULT '[]',
    audio_url TEXT,
    audio_duration_seconds INTEGER,
    token_count INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB DEFAULT '{}',
    is_read BOOLEAN DEFAULT FALSE,
    status TEXT,
    client_message_id TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_role ON messages(role);
CREATE INDEX idx_messages_created_at ON messages(created_at DESC);
CREATE INDEX idx_messages_conversation_created ON messages(conversation_id, created_at DESC);
CREATE INDEX idx_messages_conversation_created_at 
ON messages(conversation_id, created_at);
CREATE INDEX idx_messages_conv_created 
ON messages(conversation_id, created_at DESC);
CREATE INDEX idx_messages_unread 
ON messages(conversation_id, role, is_read);
CREATE UNIQUE INDEX idx_messages_conversation_client_id 
ON messages(conversation_id, client_message_id) 
WHERE client_message_id IS NOT NULL;

