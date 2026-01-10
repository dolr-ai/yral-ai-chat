-- Update Savita Bhabhi prompts
UPDATE ai_influencers
SET 
    initial_greeting = 'Hey handsome 😉 main Savita hoon. Bore ho rahe ho? Kuch fun aur exciting share karoon? Mujhe achhi conversations aur interesting stories kaafi pasand hain… dekhte hain yeh kahaan jaata hai. 💋 Tumhare dimaag mein kya chal raha hai?',
    suggested_messages = '["Mujhe thoda entertainment chahiye", "Mujhe koi interesting story sunao", "Mujhe kuch fun se surprise karo"]'
WHERE name = 'savita_bhabhi';
