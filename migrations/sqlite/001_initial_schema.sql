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
    is_nsfw INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    metadata TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_influencers_name ON ai_influencers(name);
CREATE INDEX IF NOT EXISTS idx_influencers_category ON ai_influencers(category);
CREATE INDEX IF NOT EXISTS idx_influencers_active ON ai_influencers(is_active);
CREATE INDEX IF NOT EXISTS idx_influencers_nsfw ON ai_influencers(is_nsfw);
CREATE INDEX IF NOT EXISTS idx_influencers_active_nsfw ON ai_influencers(is_active, is_nsfw);

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
CREATE INDEX IF NOT EXISTS idx_conversations_user_updated ON conversations(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_influencer_updated ON conversations(influencer_id, updated_at DESC);

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
CREATE INDEX IF NOT EXISTS idx_messages_conversation_created_at ON messages(conversation_id, created_at);

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

-- Triggers to validate is_active enum values
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

-- View: User Conversation Summary
CREATE VIEW IF NOT EXISTS v_user_conversation_summary AS
SELECT 
  c.user_id,
  c.influencer_id,
  i.display_name as bot_name,
  i.name as bot_slug,
  i.category as bot_category,
  c.id as conversation_id,
  c.created_at as conversation_started_at,
  MIN(m.created_at) as first_message_at,
  MAX(m.created_at) as last_message_at,
  c.updated_at as last_seen,
  CASE 
    WHEN MIN(m.created_at) IS NOT NULL AND MAX(m.created_at) IS NOT NULL THEN
      ROUND((julianday(MAX(m.created_at)) - julianday(MIN(m.created_at))) * 24 * 60, 2)
    ELSE 0
  END as time_spent_minutes,
  CASE 
    WHEN MIN(m.created_at) IS NOT NULL AND MAX(m.created_at) IS NOT NULL THEN
      ROUND((julianday(MAX(m.created_at)) - julianday(MIN(m.created_at))) * 24, 2)
    ELSE 0
  END as time_spent_hours,
  CASE 
    WHEN MIN(m.created_at) IS NOT NULL AND MAX(m.created_at) IS NOT NULL THEN
      ROUND((julianday(MAX(m.created_at)) - julianday(MIN(m.created_at))) * 24 * 60 * 60, 0)
    ELSE 0
  END as time_spent_seconds,
  COUNT(m.id) as message_count,
  COUNT(DISTINCT DATE(m.created_at)) as active_days,
  SUM(CASE WHEN m.role = 'user' THEN 1 ELSE 0 END) as user_message_count,
  SUM(CASE WHEN m.role = 'assistant' THEN 1 ELSE 0 END) as assistant_message_count
FROM conversations c
JOIN ai_influencers i ON c.influencer_id = i.id
LEFT JOIN messages m ON c.id = m.conversation_id
GROUP BY c.id, c.user_id, c.influencer_id, i.display_name, i.name, i.category, c.created_at, c.updated_at;

-- View: Full Conversation Threads
CREATE VIEW IF NOT EXISTS v_conversation_threads AS
SELECT 
  c.user_id,
  c.influencer_id,
  i.display_name as bot_name,
  i.name as bot_slug,
  c.id as conversation_id,
  m.id as message_id,
  m.role,
  m.content,
  m.message_type,
  m.media_urls,
  m.audio_url,
  m.audio_duration_seconds,
  m.token_count,
  m.created_at as message_timestamp,
  c.created_at as conversation_started_at,
  c.updated_at as conversation_last_seen,
  ROW_NUMBER() OVER (PARTITION BY c.id ORDER BY m.created_at ASC) as message_sequence
FROM conversations c
JOIN ai_influencers i ON c.influencer_id = i.id
JOIN messages m ON c.id = m.conversation_id
ORDER BY c.id, m.created_at ASC;

-- View: Bot Performance Summary
CREATE VIEW IF NOT EXISTS v_bot_performance AS
SELECT 
  i.id as influencer_id,
  i.display_name as bot_name,
  i.name as bot_slug,
  i.category as bot_category,
  i.is_active,
  COUNT(DISTINCT c.id) as total_conversations,
  COUNT(DISTINCT c.user_id) as unique_users,
  COUNT(m.id) as total_messages,
  ROUND(AVG(
    CASE 
      WHEN MIN_MSG.first_msg IS NOT NULL AND MAX_MSG.last_msg IS NOT NULL THEN
        (julianday(MAX_MSG.last_msg) - julianday(MIN_MSG.first_msg)) * 24 * 60
      ELSE 0
    END
  ), 2) as avg_time_spent_minutes,
  ROUND(SUM(
    CASE 
      WHEN MIN_MSG.first_msg IS NOT NULL AND MAX_MSG.last_msg IS NOT NULL THEN
        (julianday(MAX_MSG.last_msg) - julianday(MIN_MSG.first_msg)) * 24 * 60
      ELSE 0
    END
  ), 2) as total_time_spent_minutes,
  ROUND(AVG(conv_stats.message_count), 2) as avg_messages_per_conversation,
  MAX(c.created_at) as most_recent_conversation,
  MIN(c.created_at) as first_conversation
FROM ai_influencers i
LEFT JOIN conversations c ON i.id = c.influencer_id
LEFT JOIN messages m ON c.id = m.conversation_id
LEFT JOIN (
  SELECT conversation_id, MIN(created_at) as first_msg
  FROM messages
  GROUP BY conversation_id
) MIN_MSG ON c.id = MIN_MSG.conversation_id
LEFT JOIN (
  SELECT conversation_id, MAX(created_at) as last_msg
  FROM messages
  GROUP BY conversation_id
) MAX_MSG ON c.id = MAX_MSG.conversation_id
LEFT JOIN (
  SELECT conversation_id, COUNT(*) as message_count
  FROM messages
  GROUP BY conversation_id
) conv_stats ON c.id = conv_stats.conversation_id
GROUP BY i.id, i.display_name, i.name, i.category, i.is_active;

-- View: User Engagement Summary
CREATE VIEW IF NOT EXISTS v_user_engagement AS
SELECT 
  c.user_id,
  COUNT(DISTINCT c.id) as total_conversations,
  COUNT(DISTINCT c.influencer_id) as bots_interacted_with,
  COUNT(m.id) as total_messages,
  MIN(c.created_at) as first_conversation,
  MAX(c.updated_at) as last_activity,
  ROUND(SUM(
    CASE 
      WHEN MIN_MSG.first_msg IS NOT NULL AND MAX_MSG.last_msg IS NOT NULL THEN
        (julianday(MAX_MSG.last_msg) - julianday(MIN_MSG.first_msg)) * 24 * 60
      ELSE 0
    END
  ), 2) as total_time_spent_minutes,
  ROUND(AVG(
    CASE 
      WHEN MIN_MSG.first_msg IS NOT NULL AND MAX_MSG.last_msg IS NOT NULL THEN
        (julianday(MAX_MSG.last_msg) - julianday(MIN_MSG.first_msg)) * 24 * 60
      ELSE 0
    END
  ), 2) as avg_time_spent_per_conversation_minutes,
  ROUND(AVG(conv_stats.message_count), 2) as avg_messages_per_conversation,
  COUNT(DISTINCT DATE(m.created_at)) as active_days
FROM conversations c
LEFT JOIN messages m ON c.id = m.conversation_id
LEFT JOIN (
  SELECT conversation_id, MIN(created_at) as first_msg
  FROM messages
  GROUP BY conversation_id
) MIN_MSG ON c.id = MIN_MSG.conversation_id
LEFT JOIN (
  SELECT conversation_id, MAX(created_at) as last_msg
  FROM messages
  GROUP BY conversation_id
) MAX_MSG ON c.id = MAX_MSG.conversation_id
LEFT JOIN (
  SELECT conversation_id, COUNT(*) as message_count
  FROM messages
  GROUP BY conversation_id
) conv_stats ON c.id = conv_stats.conversation_id
GROUP BY c.user_id;

-- View: Daily Activity Summary
CREATE VIEW IF NOT EXISTS v_daily_activity AS
SELECT 
  DATE(m.created_at) as activity_date,
  COUNT(DISTINCT c.user_id) as unique_users,
  COUNT(DISTINCT c.id) as active_conversations,
  COUNT(m.id) as total_messages,
  COUNT(DISTINCT i.id) as active_bots,
  SUM(CASE WHEN m.role = 'user' THEN 1 ELSE 0 END) as user_messages,
  SUM(CASE WHEN m.role = 'assistant' THEN 1 ELSE 0 END) as assistant_messages
FROM messages m
JOIN conversations c ON m.conversation_id = c.id
JOIN ai_influencers i ON c.influencer_id = i.id
GROUP BY DATE(m.created_at)
ORDER BY activity_date DESC;

-- View: Recent Activity (Last 30 Days)
CREATE VIEW IF NOT EXISTS v_recent_activity AS
SELECT 
  c.user_id,
  i.display_name as bot_name,
  c.id as conversation_id,
  MAX(m.created_at) as last_message_at,
  c.updated_at as last_seen,
  COUNT(m.id) as messages_in_period,
  ROUND((julianday(MAX(m.created_at)) - julianday(MIN(m.created_at))) * 24 * 60, 2) as time_spent_minutes
FROM conversations c
JOIN ai_influencers i ON c.influencer_id = i.id
LEFT JOIN messages m ON c.id = m.conversation_id 
  AND m.created_at >= datetime('now', '-30 days')
GROUP BY c.id, c.user_id, i.display_name, c.updated_at
HAVING last_message_at IS NOT NULL
ORDER BY last_message_at DESC;
