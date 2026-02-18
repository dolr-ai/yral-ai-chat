-- Backfill source for existing influencers
UPDATE ai_influencers SET source = 'admin-created-influencer' WHERE source IS NULL;
