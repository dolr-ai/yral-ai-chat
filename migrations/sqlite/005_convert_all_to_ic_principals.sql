-- Convert all influencer IDs from UUID to IC Principal format
-- Date: December 2024

-- Update Ananya Khanna (Dating Coach)
UPDATE ai_influencers
SET id = 'ananya-khanna-dating-coach-ic-principal-id-placeholder-001'
WHERE name = 'ananya_dating';

-- Update Harsh Dubey (Astrologer)  
UPDATE ai_influencers
SET id = 'harsh-dubey-astrologer-ic-principal-id-placeholder-002'
WHERE name = 'harsh_astro';

-- Update Tech Guru
UPDATE ai_influencers
SET id = 'tech-guru-ai-technology-ic-principal-id-placeholder-003'
WHERE name = 'tech_guru_ai';

-- Update Luna Wellness
UPDATE ai_influencers
SET id = 'luna-wellness-guide-ic-principal-id-placeholder-004'
WHERE name = 'luna_wellness';

-- Update Chef Marco
UPDATE ai_influencers
SET id = 'chef-marco-cooking-ic-principal-id-placeholder-005'
WHERE name = 'chef_marco';

-- Update Nova Creative
UPDATE ai_influencers
SET id = 'nova-creative-spark-ic-principal-id-placeholder-006'
WHERE name = 'nova_creative';

-- Verify all changes
SELECT 
    name,
    display_name,
    id,
    is_active
FROM ai_influencers
ORDER BY is_active DESC, name;
