-- Add inbox indexes (columns are created in 001_init_schema)

-- Create index for faster unread count queries
CREATE INDEX IF NOT EXISTS idx_messages_unread
ON messages(conversation_id, role, is_read);
