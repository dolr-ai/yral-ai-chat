-- Update Ahaan Sharma's influencer ID to use IC Principal ID
-- Date: December 2024
-- Note: Must handle foreign key constraints from conversations table

-- Temporarily disable foreign key checks
PRAGMA foreign_keys = OFF;

-- Update all conversations that reference Ahaan's old influencer ID
UPDATE conversations
SET influencer_id = 'qg2pi-g3xl4-uprdd-macwr-64q7r-plotv-xm3bg-iayu3-rnpux-7ikkz-hqe'
WHERE influencer_id IN (SELECT id FROM ai_influencers WHERE name = 'ahaanfitness');

-- Now update the influencer ID
UPDATE ai_influencers
SET id = 'qg2pi-g3xl4-uprdd-macwr-64q7r-plotv-xm3bg-iayu3-rnpux-7ikkz-hqe'
WHERE name = 'ahaanfitness';

-- Re-enable foreign key checks
PRAGMA foreign_keys = ON;
