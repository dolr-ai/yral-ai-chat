-- Add inbox/read tracking columns to messages
ALTER TABLE messages ADD COLUMN is_read BOOLEAN DEFAULT 0;
ALTER TABLE messages ADD COLUMN status TEXT DEFAULT 'delivered';
CREATE INDEX idx_messages_unread ON messages(conversation_id, role, is_read);
