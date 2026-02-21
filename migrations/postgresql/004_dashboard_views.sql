-- Dashboard Views for Metabase BI (PostgreSQL version)
-- Version: 1.0.0

-- View: User Conversation Summary
CREATE OR REPLACE VIEW v_user_conversation_summary AS
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
  -- Time spent (minutes)
  CASE 
    WHEN MIN(m.created_at) IS NOT NULL AND MAX(m.created_at) IS NOT NULL THEN
      ROUND(EXTRACT(EPOCH FROM (MAX(m.created_at) - MIN(m.created_at))) / 60, 2)
    ELSE 0
  END as time_spent_minutes,
  -- Time spent (hours)
  CASE 
    WHEN MIN(m.created_at) IS NOT NULL AND MAX(m.created_at) IS NOT NULL THEN
      ROUND(EXTRACT(EPOCH FROM (MAX(m.created_at) - MIN(m.created_at))) / 3600, 2)
    ELSE 0
  END as time_spent_hours,
  COUNT(m.id) as message_count,
  COUNT(DISTINCT DATE(m.created_at)) as active_days,
  SUM(CASE WHEN m.role = 'user' THEN 1 ELSE 0 END) as user_message_count,
  SUM(CASE WHEN m.role = 'assistant' THEN 1 ELSE 0 END) as assistant_message_count
FROM conversations c
JOIN ai_influencers i ON c.influencer_id = i.id
LEFT JOIN messages m ON c.id = m.conversation_id
GROUP BY c.id, c.user_id, c.influencer_id, i.display_name, i.name, i.category, c.created_at, c.updated_at;

-- View: Daily Activity
CREATE OR REPLACE VIEW v_daily_activity AS
SELECT 
  DATE(m.created_at) as activity_date,
  COUNT(DISTINCT c.user_id) as unique_users,
  COUNT(DISTINCT c.id) as active_conversations,
  COUNT(m.id) as total_messages,
  COUNT(DISTINCT c.influencer_id) as active_bots,
  SUM(CASE WHEN m.role = 'user' THEN 1 ELSE 0 END) as user_messages,
  SUM(CASE WHEN m.role = 'assistant' THEN 1 ELSE 0 END) as assistant_messages
FROM messages m
JOIN conversations c ON m.conversation_id = c.id
GROUP BY DATE(m.created_at)
ORDER BY activity_date DESC;

-- Indexes for filtering
CREATE INDEX IF NOT EXISTS idx_messages_conversation_created_at 
ON messages(conversation_id, created_at);

CREATE INDEX IF NOT EXISTS idx_conversations_user_updated 
ON conversations(user_id, updated_at DESC);
