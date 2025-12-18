-- Update Ahaan Sharma's avatar URL
-- Date: December 2025
-- Changes avatar from cdn.yral.com to objectstorage.com

UPDATE ai_influencers
SET avatar_url = 'https://yral-profile.hel1.your-objectstorage.com/users/qg2pi-g3xl4-uprdd-macwr-64q7r-plotv-xm3bg-iayu3-rnpux-7ikkz-hqe/profile-1763023478.jpg'
WHERE name = 'ahaanfitness'
  AND id = 'qg2pi-g3xl4-uprdd-macwr-64q7r-plotv-xm3bg-iayu3-rnpux-7ikkz-hqe';

-- Verify the update
SELECT 
    name,
    display_name,
    avatar_url
FROM ai_influencers
WHERE name = 'ahaanfitness';
