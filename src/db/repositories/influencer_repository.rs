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
    parent_principal_id: Option<String>,
    source: Option<String>,
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
    parent_principal_id: Option<String>,
    source: Option<String>,
    created_at: String,
    updated_at: String,
    metadata: String,
    conversation_count: i64,
}

#[derive(sqlx::FromRow)]
struct TrendingRow {
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
    parent_principal_id: Option<String>,
    source: Option<String>,
    created_at: String,
    updated_at: String,
    metadata: String,
    conversation_count: i64,
    message_count: i64,
}

impl From<InfluencerRow> for AIInfluencer {
    fn from(row: InfluencerRow) -> Self {
        let personality_traits: serde_json::Value =
            serde_json::from_str(&row.personality_traits)
                .unwrap_or(serde_json::Value::Object(Default::default()));

        let suggested_messages: Vec<String> =
            serde_json::from_str(&row.suggested_messages).unwrap_or_default();

        let metadata: serde_json::Value =
            serde_json::from_str(&row.metadata)
                .unwrap_or(serde_json::Value::Object(Default::default()));

        let created_at =
            chrono::NaiveDateTime::parse_from_str(&row.created_at, "%Y-%m-%d %H:%M:%S")
                .unwrap_or_default();
        let updated_at =
            chrono::NaiveDateTime::parse_from_str(&row.updated_at, "%Y-%m-%d %H:%M:%S")
                .unwrap_or_default();

        Self {
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
            parent_principal_id: row.parent_principal_id,
            source: row.source,
            created_at,
            updated_at,
            metadata,
            conversation_count: None,
            message_count: None,
        }
    }
}

impl From<InfluencerWithCountRow> for AIInfluencer {
    fn from(row: InfluencerWithCountRow) -> Self {
        let mut influencer = AIInfluencer::from(InfluencerRow {
            id: row.id,
            name: row.name,
            display_name: row.display_name,
            avatar_url: row.avatar_url,
            description: row.description,
            category: row.category,
            system_instructions: row.system_instructions,
            personality_traits: row.personality_traits,
            initial_greeting: row.initial_greeting,
            suggested_messages: row.suggested_messages,
            is_active: row.is_active,
            is_nsfw: row.is_nsfw,
            parent_principal_id: row.parent_principal_id,
            source: row.source,
            created_at: row.created_at,
            updated_at: row.updated_at,
            metadata: row.metadata,
        });
        influencer.conversation_count = Some(row.conversation_count);
        influencer
    }
}

impl From<TrendingRow> for AIInfluencer {
    fn from(row: TrendingRow) -> Self {
        let mut influencer = AIInfluencer::from(InfluencerRow {
            id: row.id,
            name: row.name,
            display_name: row.display_name,
            avatar_url: row.avatar_url,
            description: row.description,
            category: row.category,
            system_instructions: row.system_instructions,
            personality_traits: row.personality_traits,
            initial_greeting: row.initial_greeting,
            suggested_messages: row.suggested_messages,
            is_active: row.is_active,
            is_nsfw: row.is_nsfw,
            parent_principal_id: row.parent_principal_id,
            source: row.source,
            created_at: row.created_at,
            updated_at: row.updated_at,
            metadata: row.metadata,
        });
        influencer.conversation_count = Some(row.conversation_count);
        influencer.message_count = Some(row.message_count);
        influencer
    }
}

const SELECT_COLS: &str =
    "id, name, display_name, avatar_url, description, category, system_instructions,
     personality_traits, initial_greeting, suggested_messages, is_active, is_nsfw,
     parent_principal_id, source, created_at, updated_at, metadata";

impl InfluencerRepository {
    pub fn new(pool: SqlitePool) -> Self {
        Self { pool }
    }

    pub async fn create(&self, influencer: &AIInfluencer) -> Result<(), sqlx::Error> {
        let personality_traits =
            serde_json::to_string(&influencer.personality_traits).unwrap_or_else(|_| "{}".into());
        let suggested_messages =
            serde_json::to_string(&influencer.suggested_messages).unwrap_or_else(|_| "[]".into());
        let metadata =
            serde_json::to_string(&influencer.metadata).unwrap_or_else(|_| "{}".into());

        sqlx::query(
            "INSERT INTO ai_influencers (
                id, name, display_name, avatar_url, description, category,
                system_instructions, personality_traits, initial_greeting,
                suggested_messages, is_active, is_nsfw, parent_principal_id, source,
                created_at, updated_at, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(&influencer.id)
        .bind(&influencer.name)
        .bind(&influencer.display_name)
        .bind(&influencer.avatar_url)
        .bind(&influencer.description)
        .bind(&influencer.category)
        .bind(&influencer.system_instructions)
        .bind(&personality_traits)
        .bind(&influencer.initial_greeting)
        .bind(&suggested_messages)
        .bind(influencer.is_active.as_str())
        .bind(influencer.is_nsfw as i32)
        .bind(&influencer.parent_principal_id)
        .bind(&influencer.source)
        .bind(influencer.created_at.format("%Y-%m-%d %H:%M:%S").to_string())
        .bind(influencer.updated_at.format("%Y-%m-%d %H:%M:%S").to_string())
        .bind(&metadata)
        .execute(&self.pool)
        .await?;

        Ok(())
    }

    pub async fn list_all(
        &self,
        limit: i64,
        offset: i64,
    ) -> Result<Vec<AIInfluencer>, sqlx::Error> {
        let sql = format!(
            "SELECT {SELECT_COLS}
             FROM ai_influencers
             WHERE is_active != 'discontinued'
             ORDER BY CASE is_active
                 WHEN 'active' THEN 1
                 WHEN 'coming_soon' THEN 2
             END, created_at DESC
             LIMIT ? OFFSET ?"
        );

        let rows = sqlx::query_as::<_, InfluencerRow>(&sql)
            .bind(limit)
            .bind(offset)
            .fetch_all(&self.pool)
            .await?;

        Ok(rows.into_iter().map(AIInfluencer::from).collect())
    }

    pub async fn get_by_id(&self, influencer_id: &str) -> Result<Option<AIInfluencer>, sqlx::Error> {
        let sql = format!(
            "SELECT {SELECT_COLS} FROM ai_influencers WHERE id = ?"
        );

        let row = sqlx::query_as::<_, InfluencerRow>(&sql)
            .bind(influencer_id)
            .fetch_optional(&self.pool)
            .await?;

        Ok(row.map(AIInfluencer::from))
    }

    pub async fn get_by_name(&self, name: &str) -> Result<Option<AIInfluencer>, sqlx::Error> {
        let sql = format!(
            "SELECT {SELECT_COLS} FROM ai_influencers WHERE name = ?"
        );

        let row = sqlx::query_as::<_, InfluencerRow>(&sql)
            .bind(name)
            .fetch_optional(&self.pool)
            .await?;

        Ok(row.map(AIInfluencer::from))
    }

    pub async fn get_with_conversation_count(
        &self,
        influencer_id: &str,
    ) -> Result<Option<AIInfluencer>, sqlx::Error> {
        let row = sqlx::query_as::<_, InfluencerWithCountRow>(
            "SELECT i.id, i.name, i.display_name, i.avatar_url, i.description,
                    i.category, i.system_instructions, i.personality_traits,
                    i.initial_greeting, i.suggested_messages,
                    i.is_active, i.is_nsfw, i.parent_principal_id, i.source,
                    i.created_at, i.updated_at, i.metadata,
                    COUNT(c.id) as conversation_count
             FROM ai_influencers i
             LEFT JOIN conversations c ON i.id = c.influencer_id
             WHERE i.id = ?
             GROUP BY i.id",
        )
        .bind(influencer_id)
        .fetch_optional(&self.pool)
        .await?;

        Ok(row.map(AIInfluencer::from))
    }

    pub async fn update_system_prompt(
        &self,
        influencer_id: &str,
        instructions: &str,
    ) -> Result<(), sqlx::Error> {
        sqlx::query(
            "UPDATE ai_influencers SET system_instructions = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        )
        .bind(instructions)
        .bind(influencer_id)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    pub async fn soft_delete(&self, influencer_id: &str) -> Result<(), sqlx::Error> {
        sqlx::query(
            "UPDATE ai_influencers SET is_active = 'discontinued', display_name = 'Deleted Bot', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        )
        .bind(influencer_id)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    pub async fn list_trending(
        &self,
        limit: i64,
        offset: i64,
    ) -> Result<Vec<AIInfluencer>, sqlx::Error> {
        let rows = sqlx::query_as::<_, TrendingRow>(
            "SELECT i.id, i.name, i.display_name, i.avatar_url, i.description,
                    i.category, i.system_instructions, i.personality_traits,
                    i.initial_greeting, i.suggested_messages,
                    i.is_active, i.is_nsfw, i.parent_principal_id, i.source,
                    i.created_at, i.updated_at, i.metadata,
                    COUNT(DISTINCT c.id) as conversation_count,
                    COUNT(m.id) as message_count
             FROM ai_influencers i
             LEFT JOIN conversations c ON i.id = c.influencer_id
             LEFT JOIN messages m ON c.id = m.conversation_id
             WHERE i.is_active = 'active'
             GROUP BY i.id
             ORDER BY message_count DESC
             LIMIT ? OFFSET ?",
        )
        .bind(limit)
        .bind(offset)
        .fetch_all(&self.pool)
        .await?;

        Ok(rows.into_iter().map(AIInfluencer::from).collect())
    }

    pub async fn count_trending(&self) -> Result<i64, sqlx::Error> {
        let count: (i64,) =
            sqlx::query_as("SELECT COUNT(*) FROM ai_influencers WHERE is_active = 'active'")
                .fetch_one(&self.pool)
                .await?;
        Ok(count.0)
    }

    pub async fn count_all(&self) -> Result<i64, sqlx::Error> {
        let count: (i64,) =
            sqlx::query_as("SELECT COUNT(*) FROM ai_influencers WHERE is_active != 'discontinued'")
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
