-- Add client_message_id index (column is created in 001_init_schema)
-- Version: 1.0.8

-- Create unique index to prevent duplicate user messages in the same conversation
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_conversation_client_id
ON messages(conversation_id, client_message_id)
WHERE client_message_id IS NOT NULL;
