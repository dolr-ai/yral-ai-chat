-- Add ownership fields for user-created influencers
ALTER TABLE ai_influencers ADD COLUMN parent_principal_id TEXT;
ALTER TABLE ai_influencers ADD COLUMN source TEXT;
CREATE INDEX idx_influencers_parent_principal ON ai_influencers(parent_principal_id);
