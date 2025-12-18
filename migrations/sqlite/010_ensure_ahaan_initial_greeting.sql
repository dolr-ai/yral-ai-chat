-- Ensure Ahaan Sharma has initial_greeting set
-- Date: December 2025
-- This fixes cases where initial_greeting might be NULL or empty in production

UPDATE ai_influencers
SET initial_greeting = '🔥 Yo! What''s up, bro! I''m Ahaan Sharma, your bodybuilding coach! 💪 Ready to crush some fitness goals today? Whether you need workout advice, nutrition tips, or just some motivation - I got you! Let''s goooo! 🏋️ What can I help you with?'
WHERE id = 'qg2pi-g3xl4-uprdd-macwr-64q7r-plotv-xm3bg-iayu3-rnpux-7ikkz-hqe'
  AND (initial_greeting IS NULL OR initial_greeting = '');
