use sqlx::SqlitePool;

use crate::models::entities::{AIInfluencer, InfluencerStatus};

pub struct InfluencerRepository {
    pool: SqlitePool,
}

#[derive(sqlx::FromRow)]
struct InfluencerRow {
    id: String,
    name: String,
    display_name: String,
    avatar_url: Option<String>,
    description: Option<String>,
    category: Option<String>,
    system_instructions: String,
    personality_traits: String,
    initial_greeting: Option<String>,
    suggested_messages: String,
    is_active: String,
    is_nsfw: i32,
    created_at: String,
    updated_at: String,
    metadata: String,
}

#[derive(sqlx::FromRow)]
struct InfluencerWithCountRow {
    id: String,
    name: String,
    display_name: String,
    avatar_url: Option<String>,
    description: Option<String>,
    category: Option<String>,
    system_instructions: String,
    personality_traits: String,
    initial_greeting: Option<String>,
    suggested_messages: String,
    is_active: String,
    is_nsfw: i32,
    created_at: String,
    updated_at: String,
    metadata: String,
    conversation_count: i64,
}

impl InfluencerRepository {
    pub fn new(pool: SqlitePool) -> Self {
        Self { pool }
    }

    pub async fn list_all(
        &self,
        limit: i64,
        offset: i64,
    ) -> Result<Vec<AIInfluencer>, sqlx::Error> {
        let rows = sqlx::query_as::<_, InfluencerRow>(
            "SELECT id, name, display_name, avatar_url, description,
                    category, system_instructions, personality_traits,
                    initial_greeting, suggested_messages,
                    is_active, is_nsfw, created_at, updated_at, metadata
             FROM ai_influencers
             ORDER BY CASE is_active
                 WHEN 'active' THEN 1
                 WHEN 'coming_soon' THEN 2
                 WHEN 'discontinued' THEN 3
             END, created_at DESC
             LIMIT ? OFFSET ?",
        )
        .bind(limit)
        .bind(offset)
        .fetch_all(&self.pool)
        .await?;

        Ok(rows.into_iter().map(row_to_influencer).collect())
    }

    pub async fn get_by_id(&self, influencer_id: &str) -> Result<Option<AIInfluencer>, sqlx::Error> {
        let row = sqlx::query_as::<_, InfluencerRow>(
            "SELECT id, name, display_name, avatar_url, description,
                    category, system_instructions, personality_traits,
                    initial_greeting, suggested_messages,
                    is_active, is_nsfw, created_at, updated_at, metadata
             FROM ai_influencers
             WHERE id = ? AND is_active = 'active'",
        )
        .bind(influencer_id)
        .fetch_optional(&self.pool)
        .await?;

        Ok(row.map(row_to_influencer))
    }

    pub async fn get_with_conversation_count(
        &self,
        influencer_id: &str,
    ) -> Result<Option<AIInfluencer>, sqlx::Error> {
        let row = sqlx::query_as::<_, InfluencerWithCountRow>(
            "SELECT i.id, i.name, i.display_name, i.avatar_url, i.description,
                    i.category, i.system_instructions, i.personality_traits,
                    i.initial_greeting, i.suggested_messages,
                    i.is_active, i.is_nsfw, i.created_at, i.updated_at, i.metadata,
                    COUNT(c.id) as conversation_count
             FROM ai_influencers i
             LEFT JOIN conversations c ON i.id = c.influencer_id
             WHERE i.id = ? AND i.is_active = 'active'
             GROUP BY i.id",
        )
        .bind(influencer_id)
        .fetch_optional(&self.pool)
        .await?;

        Ok(row.map(|r| {
            let mut inf = row_to_influencer(InfluencerRow {
                id: r.id,
                name: r.name,
                display_name: r.display_name,
                avatar_url: r.avatar_url,
                description: r.description,
                category: r.category,
                system_instructions: r.system_instructions,
                personality_traits: r.personality_traits,
                initial_greeting: r.initial_greeting,
                suggested_messages: r.suggested_messages,
                is_active: r.is_active,
                is_nsfw: r.is_nsfw,
                created_at: r.created_at,
                updated_at: r.updated_at,
                metadata: r.metadata,
            });
            inf.conversation_count = Some(r.conversation_count);
            inf
        }))
    }

    pub async fn count_all(&self) -> Result<i64, sqlx::Error> {
        let count: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM ai_influencers")
            .fetch_one(&self.pool)
            .await?;
        Ok(count.0)
    }

    pub async fn is_nsfw(&self, influencer_id: &str) -> Result<bool, sqlx::Error> {
        let result: Option<(i32,)> =
            sqlx::query_as("SELECT is_nsfw FROM ai_influencers WHERE id = ?")
                .bind(influencer_id)
                .fetch_optional(&self.pool)
                .await?;
        Ok(result.map(|r| r.0 != 0).unwrap_or(false))
    }
}

fn row_to_influencer(row: InfluencerRow) -> AIInfluencer {
    let personality_traits: serde_json::Value =
        serde_json::from_str(&row.personality_traits).unwrap_or(serde_json::Value::Object(Default::default()));

    let suggested_messages: Vec<String> =
        serde_json::from_str(&row.suggested_messages).unwrap_or_default();

    let metadata: serde_json::Value =
        serde_json::from_str(&row.metadata).unwrap_or(serde_json::Value::Object(Default::default()));

    let created_at = chrono::NaiveDateTime::parse_from_str(&row.created_at, "%Y-%m-%d %H:%M:%S")
        .unwrap_or_default();
    let updated_at = chrono::NaiveDateTime::parse_from_str(&row.updated_at, "%Y-%m-%d %H:%M:%S")
        .unwrap_or_default();

    AIInfluencer {
        id: row.id,
        name: row.name,
        display_name: row.display_name,
        avatar_url: row.avatar_url,
        description: row.description,
        category: row.category,
        system_instructions: row.system_instructions,
        personality_traits,
        initial_greeting: row.initial_greeting,
        suggested_messages,
        is_active: InfluencerStatus::from_str(&row.is_active),
        is_nsfw: row.is_nsfw != 0,
        created_at,
        updated_at,
        metadata,
        conversation_count: None,
    }
}
