-- Add covering index for influencer trending message counts
-- This drops the LEFT JOIN execution time from ~3000ms down to sub-10ms
CREATE INDEX IF NOT EXISTS idx_messages_conv_role ON messages(conversation_id, role);
