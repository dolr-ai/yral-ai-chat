#[cfg(not(feature = "staging"))]
use sqlx::PgPool;
#[cfg(feature = "staging")]
use sqlx::SqlitePool;

#[cfg(feature = "staging")]
use super::{parse_dt, parse_json};

use crate::models::entities::{AIInfluencer, InfluencerStatus};

// ── Staging: SQLite-only ──────────────────────────────────────────────────────

#[cfg(feature = "staging")]
pub struct InfluencerRepository {
    pool: SqlitePool,
}

#[cfg(feature = "staging")]
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
    #[sqlx(default)]
    conversation_count: Option<i64>,
    #[sqlx(default)]
    message_count: Option<i64>,
}

#[cfg(feature = "staging")]
impl From<InfluencerRow> for AIInfluencer {
    fn from(row: InfluencerRow) -> Self {
        Self {
            id: row.id,
            name: row.name,
            display_name: row.display_name,
            avatar_url: row.avatar_url,
            description: row.description,
            category: row.category,
            system_instructions: row.system_instructions,
            personality_traits: parse_json(&row.personality_traits),
            initial_greeting: row.initial_greeting,
            suggested_messages: serde_json::from_str(&row.suggested_messages).unwrap_or_default(),
            is_active: row.is_active.parse().unwrap_or(InfluencerStatus::Active),
            is_nsfw: row.is_nsfw != 0,
            parent_principal_id: row.parent_principal_id,
            source: row.source,
            created_at: parse_dt(&row.created_at),
            updated_at: parse_dt(&row.updated_at),
            metadata: parse_json(&row.metadata),
            conversation_count: row.conversation_count,
            message_count: row.message_count,
        }
    }
}

#[cfg(feature = "staging")]
const SELECT_COLS: &str =
    "id, name, display_name, avatar_url, description, category, system_instructions,
     personality_traits, initial_greeting, suggested_messages, is_active, is_nsfw,
     parent_principal_id, source, created_at, updated_at, metadata";

#[cfg(feature = "staging")]
impl InfluencerRepository {
    pub fn new(pool: SqlitePool) -> Self {
        Self { pool }
    }

    // ── Writes ────────────────────────────────────────────────────────────────

    pub async fn create(&self, influencer: &AIInfluencer) -> Result<(), sqlx::Error> {
        let personality_traits =
            serde_json::to_string(&influencer.personality_traits).unwrap_or("{}".to_string());
        let suggested_messages =
            serde_json::to_string(&influencer.suggested_messages).unwrap_or("[]".to_string());
        let metadata = serde_json::to_string(&influencer.metadata).unwrap_or("{}".to_string());

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
        .bind(influencer.is_active.as_ref())
        .bind(influencer.is_nsfw as i32)
        .bind(&influencer.parent_principal_id)
        .bind(&influencer.source)
        .bind(
            influencer
                .created_at
                .format("%Y-%m-%d %H:%M:%S")
                .to_string(),
        )
        .bind(
            influencer
                .updated_at
                .format("%Y-%m-%d %H:%M:%S")
                .to_string(),
        )
        .bind(&metadata)
        .execute(&self.pool)
        .await?;

        Ok(())
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

    pub async fn ban(&self, influencer_id: &str) -> Result<(), sqlx::Error> {
        sqlx::query(
            "UPDATE ai_influencers SET is_active = 'discontinued', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        )
        .bind(influencer_id)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    pub async fn unban(&self, influencer_id: &str) -> Result<(), sqlx::Error> {
        sqlx::query(
            "UPDATE ai_influencers SET is_active = 'active', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        )
        .bind(influencer_id)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    // ── Reads ─────────────────────────────────────────────────────────────────

    pub async fn list_all(
        &self,
        limit: i64,
        offset: i64,
    ) -> Result<Vec<AIInfluencer>, sqlx::Error> {
        let rows = sqlx::query_as::<_, InfluencerRow>(&format!(
            "SELECT {SELECT_COLS} FROM ai_influencers WHERE is_active != 'discontinued'
             ORDER BY CASE is_active WHEN 'active' THEN 1 WHEN 'coming_soon' THEN 2 END, created_at DESC
             LIMIT ? OFFSET ?"
        ))
        .bind(limit)
        .bind(offset)
        .fetch_all(&self.pool)
        .await?;
        Ok(rows.into_iter().map(AIInfluencer::from).collect())
    }

    pub async fn get_by_id(
        &self,
        influencer_id: &str,
    ) -> Result<Option<AIInfluencer>, sqlx::Error> {
        let row = sqlx::query_as::<_, InfluencerRow>(&format!(
            "SELECT {SELECT_COLS} FROM ai_influencers WHERE id = ?"
        ))
        .bind(influencer_id)
        .fetch_optional(&self.pool)
        .await?;
        Ok(row.map(AIInfluencer::from))
    }

    pub async fn get_by_name(&self, name: &str) -> Result<Option<AIInfluencer>, sqlx::Error> {
        let row = sqlx::query_as::<_, InfluencerRow>(&format!(
            "SELECT {SELECT_COLS} FROM ai_influencers WHERE name = ?"
        ))
        .bind(name)
        .fetch_optional(&self.pool)
        .await?;
        Ok(row.map(AIInfluencer::from))
    }

    pub async fn get_by_id_or_name(
        &self,
        id_or_name: &str,
    ) -> Result<Option<AIInfluencer>, sqlx::Error> {
        let row = sqlx::query_as::<_, InfluencerRow>(&format!(
            "SELECT {SELECT_COLS} FROM ai_influencers WHERE id = ? OR name = ? LIMIT 1"
        ))
        .bind(id_or_name)
        .bind(id_or_name)
        .fetch_optional(&self.pool)
        .await?;
        Ok(row.map(AIInfluencer::from))
    }

    pub async fn get_parent_principal(
        &self,
        influencer_id: &str,
    ) -> Result<Option<String>, sqlx::Error> {
        let row: Option<(Option<String>,)> =
            sqlx::query_as("SELECT parent_principal_id FROM ai_influencers WHERE id = ?")
                .bind(influencer_id)
                .fetch_optional(&self.pool)
                .await?;
        Ok(row.and_then(|r| r.0).filter(|s| !s.is_empty()))
    }

    pub async fn get_with_conversation_count(
        &self,
        influencer_id: &str,
    ) -> Result<Option<AIInfluencer>, sqlx::Error> {
        let row = sqlx::query_as::<_, InfluencerRow>(
            "SELECT i.id, i.name, i.display_name, i.avatar_url, i.description,
                    i.category, i.system_instructions, i.personality_traits,
                    i.initial_greeting, i.suggested_messages,
                    i.is_active, i.is_nsfw, i.parent_principal_id, i.source,
                    i.created_at, i.updated_at, i.metadata,
                    COUNT(c.id) as conversation_count
             FROM ai_influencers i
             LEFT JOIN conversations c ON i.id = c.influencer_id
             WHERE i.id = ? GROUP BY i.id",
        )
        .bind(influencer_id)
        .fetch_optional(&self.pool)
        .await?;
        Ok(row.map(AIInfluencer::from))
    }

    pub async fn list_trending(
        &self,
        limit: i64,
        offset: i64,
    ) -> Result<Vec<AIInfluencer>, sqlx::Error> {
        let rows = sqlx::query_as::<_, InfluencerRow>(
            "SELECT i.id, i.name, i.display_name, i.avatar_url, i.description,
                    i.category, i.system_instructions, i.personality_traits,
                    i.initial_greeting, i.suggested_messages,
                    i.is_active, i.is_nsfw, i.parent_principal_id, i.source,
                    i.created_at, i.updated_at, i.metadata,
                    (SELECT COUNT(c.id) FROM conversations c WHERE c.influencer_id = i.id) as conversation_count,
                    (SELECT COUNT(m.id) FROM conversations c JOIN messages m ON c.id = m.conversation_id WHERE c.influencer_id = i.id AND m.role = 'user') as message_count
             FROM ai_influencers i WHERE i.is_active = 'active'
             ORDER BY message_count DESC, i.created_at DESC LIMIT ? OFFSET ?",
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
}

// ── Non-staging: PostgreSQL-only ──────────────────────────────────────────────

#[cfg(not(feature = "staging"))]
pub struct InfluencerRepository {
    pg_pool: PgPool,
    primary_pg_pool: Option<PgPool>,
}

#[cfg(not(feature = "staging"))]
#[derive(sqlx::FromRow)]
struct PgInfluencerRow {
    id: String,
    name: String,
    display_name: String,
    avatar_url: Option<String>,
    description: Option<String>,
    category: Option<String>,
    system_instructions: String,
    personality_traits: serde_json::Value,
    initial_greeting: Option<String>,
    suggested_messages: serde_json::Value,
    is_active: String,
    is_nsfw: bool,
    parent_principal_id: Option<String>,
    source: Option<String>,
    created_at: chrono::NaiveDateTime,
    updated_at: chrono::NaiveDateTime,
    metadata: serde_json::Value,
    #[sqlx(default)]
    conversation_count: Option<i64>,
    #[sqlx(default)]
    message_count: Option<i64>,
}

#[cfg(not(feature = "staging"))]
impl From<PgInfluencerRow> for AIInfluencer {
    fn from(row: PgInfluencerRow) -> Self {
        Self {
            id: row.id,
            name: row.name,
            display_name: row.display_name,
            avatar_url: row.avatar_url,
            description: row.description,
            category: row.category,
            system_instructions: row.system_instructions,
            personality_traits: row.personality_traits,
            initial_greeting: row.initial_greeting,
            suggested_messages: serde_json::from_value(row.suggested_messages).unwrap_or_default(),
            is_active: row.is_active.parse().unwrap_or(InfluencerStatus::Active),
            is_nsfw: row.is_nsfw,
            parent_principal_id: row.parent_principal_id,
            source: row.source,
            created_at: row.created_at,
            updated_at: row.updated_at,
            metadata: row.metadata,
            conversation_count: row.conversation_count,
            message_count: row.message_count,
        }
    }
}

#[cfg(not(feature = "staging"))]
const SELECT_COLS: &str =
    "id, name, display_name, avatar_url, description, category, system_instructions,
     personality_traits, initial_greeting, suggested_messages, is_active, is_nsfw,
     parent_principal_id, source, created_at, updated_at, metadata";

#[cfg(not(feature = "staging"))]
impl InfluencerRepository {
    pub fn new(pg_pool: PgPool, primary_pg_pool: Option<PgPool>) -> Self {
        Self {
            pg_pool,
            primary_pg_pool,
        }
    }

    // ── Writes ────────────────────────────────────────────────────────────────

    pub async fn create(&self, influencer: &AIInfluencer) -> Result<(), sqlx::Error> {
        sqlx::query(
            "INSERT INTO ai_influencers (
                id, name, display_name, avatar_url, description, category,
                system_instructions, personality_traits, initial_greeting,
                suggested_messages, is_active, is_nsfw, parent_principal_id, source,
                created_at, updated_at, metadata
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
            ON CONFLICT (id) DO NOTHING",
        )
        .bind(&influencer.id)
        .bind(&influencer.name)
        .bind(&influencer.display_name)
        .bind(&influencer.avatar_url)
        .bind(&influencer.description)
        .bind(&influencer.category)
        .bind(&influencer.system_instructions)
        .bind(&influencer.personality_traits)
        .bind(&influencer.initial_greeting)
        .bind(serde_json::to_value(&influencer.suggested_messages).unwrap_or_default())
        .bind(influencer.is_active.as_ref())
        .bind(influencer.is_nsfw)
        .bind(&influencer.parent_principal_id)
        .bind(&influencer.source)
        .bind(influencer.created_at)
        .bind(influencer.updated_at)
        .bind(&influencer.metadata)
        .execute(&self.pg_pool)
        .await?;

        if let Some(primary) = self.primary_pg_pool.clone() {
            let id = influencer.id.clone();
            let name = influencer.name.clone();
            let display_name = influencer.display_name.clone();
            let avatar_url = influencer.avatar_url.clone();
            let description = influencer.description.clone();
            let category = influencer.category.clone();
            let system_instructions = influencer.system_instructions.clone();
            let personality_traits =
                serde_json::to_string(&influencer.personality_traits).unwrap_or("{}".to_string());
            let initial_greeting = influencer.initial_greeting.clone();
            let suggested_messages =
                serde_json::to_string(&influencer.suggested_messages).unwrap_or("[]".to_string());
            let is_active = influencer.is_active.as_ref().to_string();
            let is_nsfw = influencer.is_nsfw;
            let parent_principal_id = influencer.parent_principal_id.clone();
            let source = influencer.source.clone();
            let created_at = influencer
                .created_at
                .format("%Y-%m-%d %H:%M:%S")
                .to_string();
            let updated_at = influencer
                .updated_at
                .format("%Y-%m-%d %H:%M:%S")
                .to_string();
            let metadata = serde_json::to_string(&influencer.metadata).unwrap_or("{}".to_string());
            tokio::spawn(async move {
                if let Err(e) = crate::db::pg_write::pg_insert_influencer(
                    &primary,
                    &id,
                    &name,
                    &display_name,
                    avatar_url.as_deref(),
                    description.as_deref(),
                    category.as_deref(),
                    &system_instructions,
                    &personality_traits,
                    initial_greeting.as_deref(),
                    &suggested_messages,
                    &is_active,
                    is_nsfw,
                    parent_principal_id.as_deref(),
                    source.as_deref(),
                    &created_at,
                    &updated_at,
                    &metadata,
                )
                .await
                {
                    tracing::warn!(error = %e, influencer_id = %id, "Primary PG dual-write failed: insert influencer");
                }
            });
        }

        Ok(())
    }

    pub async fn update_system_prompt(
        &self,
        influencer_id: &str,
        instructions: &str,
    ) -> Result<(), sqlx::Error> {
        crate::db::pg_write::pg_update_system_prompt(&self.pg_pool, influencer_id, instructions)
            .await?;

        if let Some(primary) = self.primary_pg_pool.clone() {
            let id = influencer_id.to_string();
            let instr = instructions.to_string();
            tokio::spawn(async move {
                if let Err(e) =
                    crate::db::pg_write::pg_update_system_prompt(&primary, &id, &instr).await
                {
                    tracing::warn!(error = %e, influencer_id = %id, "Primary PG dual-write failed: update system prompt");
                }
            });
        }

        Ok(())
    }

    pub async fn soft_delete(&self, influencer_id: &str) -> Result<(), sqlx::Error> {
        crate::db::pg_write::pg_soft_delete_influencer(&self.pg_pool, influencer_id).await?;

        if let Some(primary) = self.primary_pg_pool.clone() {
            let id = influencer_id.to_string();
            tokio::spawn(async move {
                if let Err(e) = crate::db::pg_write::pg_soft_delete_influencer(&primary, &id).await
                {
                    tracing::warn!(error = %e, influencer_id = %id, "Primary PG dual-write failed: soft delete influencer");
                }
            });
        }

        Ok(())
    }

    pub async fn ban(&self, influencer_id: &str) -> Result<(), sqlx::Error> {
        crate::db::pg_write::pg_ban_influencer(&self.pg_pool, influencer_id).await?;

        if let Some(primary) = self.primary_pg_pool.clone() {
            let id = influencer_id.to_string();
            tokio::spawn(async move {
                if let Err(e) = crate::db::pg_write::pg_ban_influencer(&primary, &id).await {
                    tracing::warn!(error = %e, influencer_id = %id, "Primary PG dual-write failed: ban influencer");
                }
            });
        }

        Ok(())
    }

    pub async fn unban(&self, influencer_id: &str) -> Result<(), sqlx::Error> {
        crate::db::pg_write::pg_unban_influencer(&self.pg_pool, influencer_id).await?;

        if let Some(primary) = self.primary_pg_pool.clone() {
            let id = influencer_id.to_string();
            tokio::spawn(async move {
                if let Err(e) = crate::db::pg_write::pg_unban_influencer(&primary, &id).await {
                    tracing::warn!(error = %e, influencer_id = %id, "Primary PG dual-write failed: unban influencer");
                }
            });
        }

        Ok(())
    }

    // ── Reads ─────────────────────────────────────────────────────────────────

    pub async fn list_all(
        &self,
        limit: i64,
        offset: i64,
    ) -> Result<Vec<AIInfluencer>, sqlx::Error> {
        let rows = sqlx::query_as::<_, PgInfluencerRow>(&format!(
            "SELECT {SELECT_COLS} FROM ai_influencers WHERE is_active != 'discontinued'
             ORDER BY CASE is_active WHEN 'active' THEN 1 WHEN 'coming_soon' THEN 2 END, created_at DESC
             LIMIT $1 OFFSET $2"
        ))
        .bind(limit)
        .bind(offset)
        .fetch_all(&self.pg_pool)
        .await?;
        Ok(rows.into_iter().map(AIInfluencer::from).collect())
    }

    pub async fn get_by_id(
        &self,
        influencer_id: &str,
    ) -> Result<Option<AIInfluencer>, sqlx::Error> {
        let row = sqlx::query_as::<_, PgInfluencerRow>(&format!(
            "SELECT {SELECT_COLS} FROM ai_influencers WHERE id = $1"
        ))
        .bind(influencer_id)
        .fetch_optional(&self.pg_pool)
        .await?;
        Ok(row.map(AIInfluencer::from))
    }

    pub async fn get_by_name(&self, name: &str) -> Result<Option<AIInfluencer>, sqlx::Error> {
        let row = sqlx::query_as::<_, PgInfluencerRow>(&format!(
            "SELECT {SELECT_COLS} FROM ai_influencers WHERE name = $1"
        ))
        .bind(name)
        .fetch_optional(&self.pg_pool)
        .await?;
        Ok(row.map(AIInfluencer::from))
    }

    pub async fn get_by_id_or_name(
        &self,
        id_or_name: &str,
    ) -> Result<Option<AIInfluencer>, sqlx::Error> {
        let row = sqlx::query_as::<_, PgInfluencerRow>(&format!(
            "SELECT {SELECT_COLS} FROM ai_influencers WHERE id = $1 OR name = $1 LIMIT 1"
        ))
        .bind(id_or_name)
        .fetch_optional(&self.pg_pool)
        .await?;
        Ok(row.map(AIInfluencer::from))
    }

    pub async fn get_parent_principal(
        &self,
        influencer_id: &str,
    ) -> Result<Option<String>, sqlx::Error> {
        let row: Option<(Option<String>,)> =
            sqlx::query_as("SELECT parent_principal_id FROM ai_influencers WHERE id = $1")
                .bind(influencer_id)
                .fetch_optional(&self.pg_pool)
                .await?;
        Ok(row.and_then(|r| r.0).filter(|s| !s.is_empty()))
    }

    pub async fn get_with_conversation_count(
        &self,
        influencer_id: &str,
    ) -> Result<Option<AIInfluencer>, sqlx::Error> {
        let row = sqlx::query_as::<_, PgInfluencerRow>(
            "SELECT i.id, i.name, i.display_name, i.avatar_url, i.description,
                    i.category, i.system_instructions, i.personality_traits,
                    i.initial_greeting, i.suggested_messages,
                    i.is_active, i.is_nsfw, i.parent_principal_id, i.source,
                    i.created_at, i.updated_at, i.metadata,
                    COUNT(c.id) as conversation_count
             FROM ai_influencers i
             LEFT JOIN conversations c ON i.id = c.influencer_id
             WHERE i.id = $1 GROUP BY i.id",
        )
        .bind(influencer_id)
        .fetch_optional(&self.pg_pool)
        .await?;
        Ok(row.map(AIInfluencer::from))
    }

    pub async fn list_trending(
        &self,
        limit: i64,
        offset: i64,
    ) -> Result<Vec<AIInfluencer>, sqlx::Error> {
        let rows = sqlx::query_as::<_, PgInfluencerRow>(
            "SELECT i.id, i.name, i.display_name, i.avatar_url, i.description,
                    i.category, i.system_instructions, i.personality_traits,
                    i.initial_greeting, i.suggested_messages,
                    i.is_active, i.is_nsfw, i.parent_principal_id, i.source,
                    i.created_at, i.updated_at, i.metadata,
                    (SELECT COUNT(c.id) FROM conversations c WHERE c.influencer_id = i.id) as conversation_count,
                    (SELECT COUNT(m.id) FROM conversations c JOIN messages m ON c.id = m.conversation_id WHERE c.influencer_id = i.id AND m.role = 'user') as message_count
             FROM ai_influencers i WHERE i.is_active = 'active'
             ORDER BY message_count DESC, i.created_at DESC LIMIT $1 OFFSET $2",
        )
        .bind(limit)
        .bind(offset)
        .fetch_all(&self.pg_pool)
        .await?;
        Ok(rows.into_iter().map(AIInfluencer::from).collect())
    }

    pub async fn count_trending(&self) -> Result<i64, sqlx::Error> {
        let count: (i64,) =
            sqlx::query_as("SELECT COUNT(*) FROM ai_influencers WHERE is_active = 'active'")
                .fetch_one(&self.pg_pool)
                .await?;
        Ok(count.0)
    }

    pub async fn count_all(&self) -> Result<i64, sqlx::Error> {
        let count: (i64,) =
            sqlx::query_as("SELECT COUNT(*) FROM ai_influencers WHERE is_active != 'discontinued'")
                .fetch_one(&self.pg_pool)
                .await?;
        Ok(count.0)
    }
}
