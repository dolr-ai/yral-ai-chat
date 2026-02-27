use sqlx::PgPool;

// ── Message writes ──

pub async fn pg_insert_message(
    pool: &PgPool,
    id: &str,
    conversation_id: &str,
    role: &str,
    content: Option<&str>,
    message_type: &str,
    media_urls_json: &str,
    audio_url: Option<&str>,
    audio_duration_seconds: Option<i32>,
    token_count: Option<i32>,
    client_message_id: Option<&str>,
    status: &str,
    is_read: bool,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        "INSERT INTO messages (
            id, conversation_id, role, content, message_type,
            media_urls, audio_url, audio_duration_seconds, token_count,
            client_message_id, status, is_read
        ) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, $11, $12)
        ON CONFLICT (id) DO NOTHING",
    )
    .bind(id)
    .bind(conversation_id)
    .bind(role)
    .bind(content)
    .bind(message_type)
    .bind(media_urls_json)
    .bind(audio_url)
    .bind(audio_duration_seconds)
    .bind(token_count)
    .bind(client_message_id)
    .bind(status)
    .bind(is_read)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn pg_delete_messages_by_conversation(
    pool: &PgPool,
    conversation_id: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query("DELETE FROM messages WHERE conversation_id = $1")
        .bind(conversation_id)
        .execute(pool)
        .await?;
    Ok(())
}

pub async fn pg_mark_as_read(
    pool: &PgPool,
    conversation_id: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        "UPDATE messages SET is_read = TRUE, status = 'read'
         WHERE conversation_id = $1 AND is_read = FALSE AND role = 'assistant'",
    )
    .bind(conversation_id)
    .execute(pool)
    .await?;
    Ok(())
}

// ── Conversation writes ──

pub async fn pg_insert_conversation(
    pool: &PgPool,
    id: &str,
    user_id: &str,
    influencer_id: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        "INSERT INTO conversations (id, user_id, influencer_id)
         VALUES ($1, $2, $3)
         ON CONFLICT (id) DO NOTHING",
    )
    .bind(id)
    .bind(user_id)
    .bind(influencer_id)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn pg_update_conversation_metadata(
    pool: &PgPool,
    conversation_id: &str,
    metadata_json: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        "UPDATE conversations SET metadata = $1::jsonb, updated_at = NOW() WHERE id = $2",
    )
    .bind(metadata_json)
    .bind(conversation_id)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn pg_delete_conversation(
    pool: &PgPool,
    conversation_id: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query("DELETE FROM conversations WHERE id = $1")
        .bind(conversation_id)
        .execute(pool)
        .await?;
    Ok(())
}

// ── Influencer writes ──

pub async fn pg_insert_influencer(
    pool: &PgPool,
    id: &str,
    name: &str,
    display_name: &str,
    avatar_url: Option<&str>,
    description: Option<&str>,
    category: Option<&str>,
    system_instructions: &str,
    personality_traits_json: &str,
    initial_greeting: Option<&str>,
    suggested_messages_json: &str,
    is_active: &str,
    is_nsfw: bool,
    parent_principal_id: Option<&str>,
    source: Option<&str>,
    created_at: &str,
    updated_at: &str,
    metadata_json: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        "INSERT INTO ai_influencers (
            id, name, display_name, avatar_url, description, category,
            system_instructions, personality_traits, initial_greeting,
            suggested_messages, is_active, is_nsfw, parent_principal_id, source,
            created_at, updated_at, metadata
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10::jsonb,
            $11, $12, $13, $14, $15::timestamp, $16::timestamp, $17::jsonb
        )
        ON CONFLICT (id) DO NOTHING",
    )
    .bind(id)
    .bind(name)
    .bind(display_name)
    .bind(avatar_url)
    .bind(description)
    .bind(category)
    .bind(system_instructions)
    .bind(personality_traits_json)
    .bind(initial_greeting)
    .bind(suggested_messages_json)
    .bind(is_active)
    .bind(is_nsfw)
    .bind(parent_principal_id)
    .bind(source)
    .bind(created_at)
    .bind(updated_at)
    .bind(metadata_json)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn pg_update_system_prompt(
    pool: &PgPool,
    influencer_id: &str,
    instructions: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        "UPDATE ai_influencers SET system_instructions = $1, updated_at = NOW() WHERE id = $2",
    )
    .bind(instructions)
    .bind(influencer_id)
    .execute(pool)
    .await?;
    Ok(())
}

pub async fn pg_soft_delete_influencer(
    pool: &PgPool,
    influencer_id: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query(
        "UPDATE ai_influencers SET is_active = 'discontinued', display_name = 'Deleted Bot', updated_at = NOW() WHERE id = $1",
    )
    .bind(influencer_id)
    .execute(pool)
    .await?;
    Ok(())
}
