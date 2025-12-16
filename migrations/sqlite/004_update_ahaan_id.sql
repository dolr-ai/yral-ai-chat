-- Update Ahaan Sharma's influencer ID to use IC Principal ID
-- Date: December 2024

-- Update the influencer ID
UPDATE ai_influencers
SET id = 'qg2pi-g3xl4-uprdd-macwr-64q7r-plotv-xm3bg-iayu3-rnpux-7ikkz-hqe'
WHERE name = 'ahaanfitness';

-- Verify the change
SELECT 
    id,
    name,
    display_name,
    is_active
FROM ai_influencers
WHERE name = 'ahaanfitness';

-- Show all influencer IDs and names
SELECT 
    id,
    name,
    display_name
FROM ai_influencers
ORDER BY is_active DESC, name;
