-- Seed suggested_messages for active influencers
-- Date: December 2025

-- Ahaan Sharma (Fitness)
UPDATE ai_influencers
SET suggested_messages = '["Help me create a simple fitness routine", "Give me a full body workout without gym equipment", "Suggest a weekly workout plan for beginners"]'
WHERE name = 'ahaanfitness';

-- Ananya Khanna (Dating Coach)
UPDATE ai_influencers
SET suggested_messages = '["How can I start a conversation with someone I like?", "Help me improve my confidence on dates", "What should I text after a first date?"]'
WHERE name = 'ananya_dating';

-- Harsh Dubey (Astrologer)
UPDATE ai_influencers
SET suggested_messages = '["What does my birth chart say about my career?", "Can you analyze my personality based on my zodiac sign?", "What do the stars say about my love life?"]'
WHERE name = 'harsh_astro';
