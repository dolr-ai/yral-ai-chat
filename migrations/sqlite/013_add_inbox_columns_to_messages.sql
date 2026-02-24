-- Add is_read and status columns to messages table
ALTER TABLE messages ADD COLUMN is_read BOOLEAN DEFAULT 0;
ALTER TABLE messages ADD COLUMN status TEXT DEFAULT 'delivered';

-- Create index for faster unread count queries
CREATE INDEX IF NOT EXISTS idx_messages_unread 
ON messages(conversation_id, role, is_read);
