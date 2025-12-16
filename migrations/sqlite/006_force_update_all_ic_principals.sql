-- Force update all influencer IDs to IC Principal format
-- This migration updates by NAME instead of ID since production has different UUIDs
-- Date: December 2024
-- Note: Must handle foreign key constraints from conversations table

-- Temporarily disable foreign key checks
PRAGMA foreign_keys = OFF;

-- Update Ahaan Sharma (already exists in prod with different UUID)
UPDATE conversations
SET influencer_id = 'qg2pi-g3xl4-uprdd-macwr-64q7r-plotv-xm3bg-iayu3-rnpux-7ikkz-hqe'
WHERE influencer_id IN (SELECT id FROM ai_influencers WHERE name = 'ahaanfitness');

UPDATE ai_influencers
SET id = 'qg2pi-g3xl4-uprdd-macwr-64q7r-plotv-xm3bg-iayu3-rnpux-7ikkz-hqe'
WHERE name = 'ahaanfitness';

-- Update Ananya Khanna
UPDATE conversations
SET influencer_id = 'ananya-khanna-dating-coach-ic-principal-id-placeholder-001'
WHERE influencer_id IN (SELECT id FROM ai_influencers WHERE name = 'ananya_dating');

UPDATE ai_influencers
SET id = 'ananya-khanna-dating-coach-ic-principal-id-placeholder-001'
WHERE name = 'ananya_dating';

-- Update Harsh Dubey
UPDATE conversations
SET influencer_id = 'harsh-dubey-astrologer-ic-principal-id-placeholder-002'
WHERE influencer_id IN (SELECT id FROM ai_influencers WHERE name = 'harsh_astro');

UPDATE ai_influencers
SET id = 'harsh-dubey-astrologer-ic-principal-id-placeholder-002'
WHERE name = 'harsh_astro';

-- Update Tech Guru
UPDATE conversations
SET influencer_id = 'tech-guru-ai-technology-ic-principal-id-placeholder-003'
WHERE influencer_id IN (SELECT id FROM ai_influencers WHERE name = 'tech_guru_ai');

UPDATE ai_influencers
SET id = 'tech-guru-ai-technology-ic-principal-id-placeholder-003'
WHERE name = 'tech_guru_ai';

-- Update Luna Wellness
UPDATE conversations
SET influencer_id = 'luna-wellness-guide-ic-principal-id-placeholder-004'
WHERE influencer_id IN (SELECT id FROM ai_influencers WHERE name = 'luna_wellness');

UPDATE ai_influencers
SET id = 'luna-wellness-guide-ic-principal-id-placeholder-004'
WHERE name = 'luna_wellness';

-- Update Chef Marco
UPDATE conversations
SET influencer_id = 'chef-marco-cooking-ic-principal-id-placeholder-005'
WHERE influencer_id IN (SELECT id FROM ai_influencers WHERE name = 'chef_marco');

UPDATE ai_influencers
SET id = 'chef-marco-cooking-ic-principal-id-placeholder-005'
WHERE name = 'chef_marco';

-- Update Nova Creative
UPDATE conversations
SET influencer_id = 'nova-creative-spark-ic-principal-id-placeholder-006'
WHERE influencer_id IN (SELECT id FROM ai_influencers WHERE name = 'nova_creative');

UPDATE ai_influencers
SET id = 'nova-creative-spark-ic-principal-id-placeholder-006'
WHERE name = 'nova_creative';

-- Re-enable foreign key checks
PRAGMA foreign_keys = ON;
