-- Migration: Add client_message_id for idempotency
-- Version: 1.0.8
-- Created: 2026-02-03

-- Add client_message_id column to messages table
ALTER TABLE messages ADD COLUMN client_message_id TEXT;

-- Create unique index to prevent duplicate user messages in the same conversation
-- We ignore NULLs in unique indexes in SQLite by default, which is good for backward compatibility
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_conversation_client_id 
ON messages(conversation_id, client_message_id) 
WHERE client_message_id IS NOT NULL;
