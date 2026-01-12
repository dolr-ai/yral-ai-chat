-- Migration: Activate Savita Bhabhi
-- Version: 008
-- Description: Sets Savita Bhabhi to active and restores her display name/avatar

UPDATE ai_influencers
SET 
    display_name = 'NSFW BOT',
    avatar_url = 'https://www.nbcstore.com/cdn/shop/products/SHREK-SS-63-MF1_grande.jpg',
    is_active = 'active',
    is_nsfw = 1
WHERE name = 'savita_bhabhi';
