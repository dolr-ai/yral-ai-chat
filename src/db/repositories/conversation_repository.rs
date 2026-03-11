use sqlx::{PgPool, SqlitePool};
use uuid::Uuid;

use super::{parse_dt, parse_json};
use crate::db::pg_write;
use crate::models::entities::{
    AIInfluencer, Conversation, InfluencerStatus, LastMessageInfo, MessageRole,
};

pub struct ConversationRepository {
    pool: SqlitePool,
    pg_pool: Option<PgPool>,
    pg_read: bool,
}

// ── SQLite rows ───────────────────────────────────────────────────────────────

#[derive(sqlx::FromRow)]
struct ConversationRow {
    id: String,
    user_id: String,
    influencer_id: String,
    created_at: String,
    updated_at: String,
    metadata: String,
    inf_id: String,
    name: String,
    display_name: String,
    avatar_url: Option<String>,
    suggested_messages: String,
    #[sqlx(default)]
    message_count: Option<i64>,
    #[sqlx(default)]
    unread_count: Option<i64>,
}

#[derive(sqlx::FromRow)]
struct LastMessageRow {
    conversation_id: String,
    content: Option<String>,
    role: String,
    created_at: String,
    status: Option<String>,
    is_read: i32,
}

#[derive(sqlx::FromRow)]
struct ConversationForBotRow {
    id: String,
    user_id: String,
    influencer_id: String,
    created_at: String,
    updated_at: String,
    metadata: String,
    #[sqlx(default)]
    message_count: Option<i64>,
    #[sqlx(default)]
    unread_count: Option<i64>,
}

impl From<ConversationForBotRow> for Conversation {
    fn from(row: ConversationForBotRow) -> Self {
        Self {
            id: row.id,
            user_id: row.user_id,
            influencer_id: row.influencer_id,
            created_at: parse_dt(&row.created_at),
            updated_at: parse_dt(&row.updated_at),
            metadata: parse_json(&row.metadata),
            influencer: None,
            message_count: row.message_count,
            unread_count: row.unread_count.unwrap_or(0),
            last_message: None,
            recent_messages: None,
        }
    }
}

impl From<ConversationRow> for Conversation {
    fn from(row: ConversationRow) -> Self {
        let created_at = parse_dt(&row.created_at);
        let updated_at = parse_dt(&row.updated_at);
        let suggested_messages: Vec<String> =
            serde_json::from_str(&row.suggested_messages).unwrap_or_default();

        let influencer = AIInfluencer {
            id: row.inf_id,
            name: row.name,
            display_name: row.display_name,
            avatar_url: row.avatar_url,
            description: None,
            category: None,
            system_instructions: String::new(),
            personality_traits: serde_json::Value::Object(Default::default()),
            initial_greeting: None,
            suggested_messages,
            is_active: InfluencerStatus::Active,
            is_nsfw: false,
            parent_principal_id: None,
            source: None,
            created_at,
            updated_at,
            metadata: serde_json::Value::Object(Default::default()),
            conversation_count: None,
            message_count: None,
        };

        Self {
            id: row.id,
            user_id: row.user_id,
            influencer_id: row.influencer_id,
            created_at,
            updated_at,
            metadata: parse_json(&row.metadata),
            influencer: Some(influencer),
            message_count: row.message_count,
            unread_count: row.unread_count.unwrap_or(0),
            last_message: None,
            recent_messages: None,
        }
    }
}

impl From<LastMessageRow> for LastMessageInfo {
    fn from(row: LastMessageRow) -> Self {
        Self {
            content: row.content,
            role: row.role.parse().unwrap_or(MessageRole::User),
            created_at: parse_dt(&row.created_at),
            status: row.status,
            is_read: row.is_read != 0,
        }
    }
}

// ── PostgreSQL rows ───────────────────────────────────────────────────────────

#[derive(sqlx::FromRow)]
struct PgConversationRow {
    id: String,
    user_id: String,
    influencer_id: String,
    created_at: chrono::NaiveDateTime,
    updated_at: chrono::NaiveDateTime,
    metadata: serde_json::Value,
    inf_id: String,
    name: String,
    display_name: String,
    avatar_url: Option<String>,
    suggested_messages: serde_json::Value,
    #[sqlx(default)]
    message_count: Option<i64>,
    #[sqlx(default)]
    unread_count: Option<i64>,
}

#[derive(sqlx::FromRow)]
struct PgLastMessageRow {
    conversation_id: String,
    content: Option<String>,
    role: String,
    created_at: chrono::NaiveDateTime,
    status: Option<String>,
    is_read: bool,
}

#[derive(sqlx::FromRow)]
struct PgConversationForBotRow {
    id: String,
    user_id: String,
    influencer_id: String,
    created_at: chrono::NaiveDateTime,
    updated_at: chrono::NaiveDateTime,
    metadata: serde_json::Value,
    #[sqlx(default)]
    message_count: Option<i64>,
    #[sqlx(default)]
    unread_count: Option<i64>,
}

impl From<PgConversationForBotRow> for Conversation {
    fn from(row: PgConversationForBotRow) -> Self {
        Self {
            id: row.id,
            user_id: row.user_id,
            influencer_id: row.influencer_id,
            created_at: row.created_at,
            updated_at: row.updated_at,
            metadata: row.metadata,
            influencer: None,
            message_count: row.message_count,
            unread_count: row.unread_count.unwrap_or(0),
            last_message: None,
            recent_messages: None,
        }
    }
}

impl From<PgConversationRow> for Conversation {
    fn from(row: PgConversationRow) -> Self {
        let created_at = row.created_at;
        let updated_at = row.updated_at;
        let suggested_messages: Vec<String> =
            serde_json::from_value(row.suggested_messages).unwrap_or_default();

        let influencer = AIInfluencer {
            id: row.inf_id,
            name: row.name,
            display_name: row.display_name,
            avatar_url: row.avatar_url,
            description: None,
            category: None,
            system_instructions: String::new(),
            personality_traits: serde_json::Value::Object(Default::default()),
            initial_greeting: None,
            suggested_messages,
            is_active: InfluencerStatus::Active,
            is_nsfw: false,
            parent_principal_id: None,
            source: None,
            created_at,
            updated_at,
            metadata: serde_json::Value::Object(Default::default()),
            conversation_count: None,
            message_count: None,
        };

        Self {
            id: row.id,
            user_id: row.user_id,
            influencer_id: row.influencer_id,
            created_at,
            updated_at,
            metadata: row.metadata,
            influencer: Some(influencer),
            message_count: row.message_count,
            unread_count: row.unread_count.unwrap_or(0),
            last_message: None,
            recent_messages: None,
        }
    }
}

impl From<PgLastMessageRow> for LastMessageInfo {
    fn from(row: PgLastMessageRow) -> Self {
        Self {
            content: row.content,
            role: row.role.parse().unwrap_or(MessageRole::User),
            created_at: row.created_at,
            status: row.status,
            is_read: row.is_read,
        }
    }
}

// ── Repository ────────────────────────────────────────────────────────────────

impl ConversationRepository {
    pub fn new(pool: SqlitePool, pg_pool: Option<PgPool>, pg_read: bool) -> Self {
        Self {
            pool,
            pg_pool,
            pg_read,
        }
    }

    fn use_pg(&self) -> Option<&PgPool> {
        if self.pg_read {
            self.pg_pool.as_ref()
        } else {
            None
        }
    }

    // ── Writes ────────────────────────────────────────────────────────────────

    pub async fn create(
        &self,
        user_id: &str,
        influencer_id: &str,
    ) -> Result<Conversation, sqlx::Error> {
        let conversation_id = Uuid::new_v4().to_string();

        sqlx::query("INSERT INTO conversations (id, user_id, influencer_id) VALUES (?, ?, ?)")
            .bind(&conversation_id)
            .bind(user_id)
            .bind(influencer_id)
            .execute(&self.pool)
            .await?;

        if let Some(ref pg) = self.pg_pool {
            let pg = pg.clone();
            let id = conversation_id.clone();
            let uid = user_id.to_string();
            let iid = influencer_id.to_string();
            tokio::spawn(async move {
                if let Err(e) = pg_write::pg_insert_conversation(&pg, &id, &uid, &iid).await {
                    tracing::warn!(error = %e, "PG dual-write failed for insert_conversation");
                }
            });
        }

        self.get_by_id(&conversation_id)
            .await?
            .ok_or(sqlx::Error::RowNotFound)
    }

    pub async fn update_metadata(
        &self,
        conversation_id: &str,
        metadata: &serde_json::Value,
    ) -> Result<(), sqlx::Error> {
        let metadata_json = serde_json::to_string(metadata).unwrap_or("{}".to_string());
        sqlx::query(
            "UPDATE conversations SET metadata = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        )
        .bind(&metadata_json)
        .bind(conversation_id)
        .execute(&self.pool)
        .await?;

        if let Some(ref pg) = self.pg_pool {
            let pg = pg.clone();
            let conv_id = conversation_id.to_string();
            let mj = metadata_json.clone();
            tokio::spawn(async move {
                if let Err(e) = pg_write::pg_update_conversation_metadata(&pg, &conv_id, &mj).await
                {
                    tracing::warn!(error = %e, "PG dual-write failed for update_conversation_metadata");
                }
            });
        }

        Ok(())
    }

    pub async fn delete(&self, conversation_id: &str) -> Result<(), sqlx::Error> {
        sqlx::query("DELETE FROM conversations WHERE id = ?")
            .bind(conversation_id)
            .execute(&self.pool)
            .await?;

        if let Some(ref pg) = self.pg_pool {
            let pg = pg.clone();
            let conv_id = conversation_id.to_string();
            tokio::spawn(async move {
                if let Err(e) = pg_write::pg_delete_conversation(&pg, &conv_id).await {
                    tracing::warn!(error = %e, "PG dual-write failed for delete_conversation");
                }
            });
        }

        Ok(())
    }

    // ── Reads ─────────────────────────────────────────────────────────────────

    pub async fn get_by_id(
        &self,
        conversation_id: &str,
    ) -> Result<Option<Conversation>, sqlx::Error> {
        if let Some(pg) = self.use_pg() {
            let row = sqlx::query_as::<_, PgConversationRow>(
                "SELECT c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                        i.id as inf_id, i.name, i.display_name, i.avatar_url, i.suggested_messages
                 FROM conversations c
                 JOIN ai_influencers i ON c.influencer_id = i.id
                 WHERE c.id = $1",
            )
            .bind(conversation_id)
            .fetch_optional(pg)
            .await?;
            return Ok(row.map(Conversation::from));
        }

        let row = sqlx::query_as::<_, ConversationRow>(
            "SELECT c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                    i.id as inf_id, i.name, i.display_name, i.avatar_url, i.suggested_messages
             FROM conversations c
             JOIN ai_influencers i ON c.influencer_id = i.id
             WHERE c.id = ?",
        )
        .bind(conversation_id)
        .fetch_optional(&self.pool)
        .await?;
        Ok(row.map(Conversation::from))
    }

    pub async fn get_existing(
        &self,
        user_id: &str,
        influencer_id: &str,
    ) -> Result<Option<Conversation>, sqlx::Error> {
        if let Some(pg) = self.use_pg() {
            let row = sqlx::query_as::<_, PgConversationRow>(
                "SELECT c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                        i.id as inf_id, i.name, i.display_name, i.avatar_url, i.suggested_messages
                 FROM conversations c
                 JOIN ai_influencers i ON c.influencer_id = i.id
                 WHERE c.user_id = $1 AND c.influencer_id = $2",
            )
            .bind(user_id)
            .bind(influencer_id)
            .fetch_optional(pg)
            .await?;
            return Ok(row.map(Conversation::from));
        }

        let row = sqlx::query_as::<_, ConversationRow>(
            "SELECT c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                    i.id as inf_id, i.name, i.display_name, i.avatar_url, i.suggested_messages
             FROM conversations c
             JOIN ai_influencers i ON c.influencer_id = i.id
             WHERE c.user_id = ? AND c.influencer_id = ?",
        )
        .bind(user_id)
        .bind(influencer_id)
        .fetch_optional(&self.pool)
        .await?;
        Ok(row.map(Conversation::from))
    }

    pub async fn list_by_user(
        &self,
        user_id: &str,
        influencer_id: Option<&str>,
        limit: i64,
        offset: i64,
    ) -> Result<Vec<Conversation>, sqlx::Error> {
        let mut conversations: Vec<Conversation> = if let Some(pg) = self.use_pg() {
            let rows = if let Some(inf_id) = influencer_id {
                sqlx::query_as::<_, PgConversationRow>(
                    "SELECT c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                            i.id as inf_id, i.name, i.display_name, i.avatar_url, i.suggested_messages,
                            COUNT(m.id) as message_count,
                            (SELECT COUNT(*) FROM messages m2 WHERE m2.conversation_id = c.id AND m2.is_read = FALSE AND m2.role = 'assistant') as unread_count
                     FROM conversations c
                     JOIN ai_influencers i ON c.influencer_id = i.id
                     LEFT JOIN messages m ON c.id = m.conversation_id
                     WHERE c.user_id = $1 AND c.influencer_id = $2 AND i.is_active != 'discontinued'
                     AND c.user_id NOT IN (SELECT id FROM ai_influencers)
                     GROUP BY c.id, i.id
                     ORDER BY c.updated_at DESC
                     LIMIT $3 OFFSET $4",
                )
                .bind(user_id)
                .bind(inf_id)
                .bind(limit)
                .bind(offset)
                .fetch_all(pg)
                .await?
            } else {
                sqlx::query_as::<_, PgConversationRow>(
                    "SELECT c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                            i.id as inf_id, i.name, i.display_name, i.avatar_url, i.suggested_messages,
                            COUNT(m.id) as message_count,
                            (SELECT COUNT(*) FROM messages m2 WHERE m2.conversation_id = c.id AND m2.is_read = FALSE AND m2.role = 'assistant') as unread_count
                     FROM conversations c
                     JOIN ai_influencers i ON c.influencer_id = i.id
                     LEFT JOIN messages m ON c.id = m.conversation_id
                     WHERE c.user_id = $1 AND i.is_active != 'discontinued'
                     AND c.user_id NOT IN (SELECT id FROM ai_influencers)
                     GROUP BY c.id, i.id
                     ORDER BY c.updated_at DESC
                     LIMIT $2 OFFSET $3",
                )
                .bind(user_id)
                .bind(limit)
                .bind(offset)
                .fetch_all(pg)
                .await?
            };

            let mut conversations: Vec<Conversation> =
                rows.into_iter().map(Conversation::from).collect();

            if !conversations.is_empty() {
                let conv_ids: Vec<String> = conversations.iter().map(|c| c.id.clone()).collect();
                let last_messages = self.pg_get_last_messages_batch(pg, &conv_ids).await?;
                for conv in &mut conversations {
                    conv.last_message = last_messages.get(&conv.id).cloned();
                }
            }
            return Ok(conversations);
        } else {
            if let Some(inf_id) = influencer_id {
                sqlx::query_as::<_, ConversationRow>(
                    "SELECT c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                            i.id as inf_id, i.name, i.display_name, i.avatar_url, i.suggested_messages,
                            COUNT(m.id) as message_count,
                            (SELECT COUNT(*) FROM messages m2 WHERE m2.conversation_id = c.id AND m2.is_read = 0 AND m2.role = 'assistant') as unread_count
                     FROM conversations c
                     JOIN ai_influencers i ON c.influencer_id = i.id
                     LEFT JOIN messages m ON c.id = m.conversation_id
                     WHERE c.user_id = ? AND c.influencer_id = ? AND i.is_active != 'discontinued'
                     AND c.user_id NOT IN (SELECT id FROM ai_influencers)
                     GROUP BY c.id, i.id
                     ORDER BY c.updated_at DESC
                     LIMIT ? OFFSET ?",
                )
                .bind(user_id)
                .bind(inf_id)
                .bind(limit)
                .bind(offset)
                .fetch_all(&self.pool)
                .await?
                .into_iter()
                .map(Conversation::from)
                .collect()
            } else {
                sqlx::query_as::<_, ConversationRow>(
                    "SELECT c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                            i.id as inf_id, i.name, i.display_name, i.avatar_url, i.suggested_messages,
                            COUNT(m.id) as message_count,
                            (SELECT COUNT(*) FROM messages m2 WHERE m2.conversation_id = c.id AND m2.is_read = 0 AND m2.role = 'assistant') as unread_count
                     FROM conversations c
                     JOIN ai_influencers i ON c.influencer_id = i.id
                     LEFT JOIN messages m ON c.id = m.conversation_id
                     WHERE c.user_id = ? AND i.is_active != 'discontinued'
                     AND c.user_id NOT IN (SELECT id FROM ai_influencers)
                     GROUP BY c.id, i.id
                     ORDER BY c.updated_at DESC
                     LIMIT ? OFFSET ?",
                )
                .bind(user_id)
                .bind(limit)
                .bind(offset)
                .fetch_all(&self.pool)
                .await?
                .into_iter()
                .map(Conversation::from)
                .collect()
            }
        };

        if !conversations.is_empty() {
            let conv_ids: Vec<String> = conversations.iter().map(|c| c.id.clone()).collect();
            let last_messages = self.get_last_messages_batch(&conv_ids).await?;
            for conv in &mut conversations {
                conv.last_message = last_messages.get(&conv.id).cloned();
            }
        }
        Ok(conversations)
    }

    pub async fn count_by_user(
        &self,
        user_id: &str,
        influencer_id: Option<&str>,
    ) -> Result<i64, sqlx::Error> {
        if let Some(pg) = self.use_pg() {
            let count: (i64,) = if let Some(inf_id) = influencer_id {
                sqlx::query_as(
                    "SELECT COUNT(*) FROM conversations c JOIN ai_influencers i ON c.influencer_id = i.id WHERE c.user_id = $1 AND c.influencer_id = $2 AND i.is_active != 'discontinued' AND c.user_id NOT IN (SELECT id FROM ai_influencers)",
                )
                .bind(user_id)
                .bind(inf_id)
                .fetch_one(pg)
                .await?
            } else {
                sqlx::query_as(
                    "SELECT COUNT(*) FROM conversations c JOIN ai_influencers i ON c.influencer_id = i.id WHERE c.user_id = $1 AND i.is_active != 'discontinued' AND c.user_id NOT IN (SELECT id FROM ai_influencers)",
                )
                .bind(user_id)
                .fetch_one(pg)
                .await?
            };
            return Ok(count.0);
        }

        if let Some(inf_id) = influencer_id {
            let count: (i64,) = sqlx::query_as(
                "SELECT COUNT(*) FROM conversations c JOIN ai_influencers i ON c.influencer_id = i.id WHERE c.user_id = ? AND c.influencer_id = ? AND i.is_active != 'discontinued' AND c.user_id NOT IN (SELECT id FROM ai_influencers)",
            )
            .bind(user_id)
            .bind(inf_id)
            .fetch_one(&self.pool)
            .await?;
            Ok(count.0)
        } else {
            let count: (i64,) =
                sqlx::query_as("SELECT COUNT(*) FROM conversations c JOIN ai_influencers i ON c.influencer_id = i.id WHERE c.user_id = ? AND i.is_active != 'discontinued' AND c.user_id NOT IN (SELECT id FROM ai_influencers)")
                    .bind(user_id)
                    .fetch_one(&self.pool)
                    .await?;
            Ok(count.0)
        }
    }

    pub async fn list_by_influencer(
        &self,
        influencer_id: &str,
        limit: i64,
        offset: i64,
    ) -> Result<Vec<Conversation>, sqlx::Error> {
        if let Some(pg) = self.use_pg() {
            let rows = sqlx::query_as::<_, PgConversationForBotRow>(
                "SELECT c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                        COUNT(m.id) as message_count,
                        (SELECT COUNT(*) FROM messages m2 WHERE m2.conversation_id = c.id AND m2.is_read = FALSE AND m2.role = 'user') as unread_count
                 FROM conversations c
                 LEFT JOIN messages m ON c.id = m.conversation_id
                 WHERE c.influencer_id = $1
                 GROUP BY c.id
                 ORDER BY c.updated_at DESC
                 LIMIT $2 OFFSET $3",
            )
            .bind(influencer_id)
            .bind(limit)
            .bind(offset)
            .fetch_all(pg)
            .await?;

            let mut conversations: Vec<Conversation> =
                rows.into_iter().map(Conversation::from).collect();

            if !conversations.is_empty() {
                let conv_ids: Vec<String> = conversations.iter().map(|c| c.id.clone()).collect();
                let last_messages = self.pg_get_last_messages_batch(pg, &conv_ids).await?;
                for conv in &mut conversations {
                    conv.last_message = last_messages.get(&conv.id).cloned();
                }
            }
            return Ok(conversations);
        }

        let rows = sqlx::query_as::<_, ConversationForBotRow>(
            "SELECT c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                    COUNT(m.id) as message_count,
                    (SELECT COUNT(*) FROM messages m2 WHERE m2.conversation_id = c.id AND m2.is_read = 0 AND m2.role = 'user') as unread_count
             FROM conversations c
             LEFT JOIN messages m ON c.id = m.conversation_id
             WHERE c.influencer_id = ?
             GROUP BY c.id
             ORDER BY c.updated_at DESC
             LIMIT ? OFFSET ?",
        )
        .bind(influencer_id)
        .bind(limit)
        .bind(offset)
        .fetch_all(&self.pool)
        .await?;

        let mut conversations: Vec<Conversation> =
            rows.into_iter().map(Conversation::from).collect();

        if !conversations.is_empty() {
            let conv_ids: Vec<String> = conversations.iter().map(|c| c.id.clone()).collect();
            let last_messages = self.get_last_messages_batch(&conv_ids).await?;
            for conv in &mut conversations {
                conv.last_message = last_messages.get(&conv.id).cloned();
            }
        }
        Ok(conversations)
    }

    pub async fn count_by_influencer(&self, influencer_id: &str) -> Result<i64, sqlx::Error> {
        if let Some(pg) = self.use_pg() {
            let count: (i64,) =
                sqlx::query_as("SELECT COUNT(*) FROM conversations WHERE influencer_id = $1")
                    .bind(influencer_id)
                    .fetch_one(pg)
                    .await?;
            return Ok(count.0);
        }

        let count: (i64,) =
            sqlx::query_as("SELECT COUNT(*) FROM conversations WHERE influencer_id = ?")
                .bind(influencer_id)
                .fetch_one(&self.pool)
                .await?;
        Ok(count.0)
    }

    // ── Last-message batch helpers ────────────────────────────────────────────

    async fn get_last_messages_batch(
        &self,
        conversation_ids: &[String],
    ) -> Result<std::collections::HashMap<String, LastMessageInfo>, sqlx::Error> {
        if conversation_ids.is_empty() {
            return Ok(std::collections::HashMap::new());
        }

        let placeholders: Vec<&str> = conversation_ids.iter().map(|_| "?").collect();
        let sql = format!(
            "SELECT m1.conversation_id, m1.content, m1.role, m1.created_at, m1.status, m1.is_read
             FROM messages m1
             INNER JOIN (
                 SELECT conversation_id, MAX(created_at) as max_created
                 FROM messages
                 WHERE conversation_id IN ({})
                 GROUP BY conversation_id
             ) m2 ON m1.conversation_id = m2.conversation_id
                 AND m1.created_at = m2.max_created",
            placeholders.join(", ")
        );

        let mut query = sqlx::query_as::<_, LastMessageRow>(&sql);
        for id in conversation_ids {
            query = query.bind(id);
        }

        let rows = query.fetch_all(&self.pool).await?;
        let mut result = std::collections::HashMap::new();
        for row in rows {
            let conv_id = row.conversation_id.clone();
            result.insert(conv_id, LastMessageInfo::from(row));
        }
        Ok(result)
    }

    async fn pg_get_last_messages_batch(
        &self,
        pg: &PgPool,
        conversation_ids: &[String],
    ) -> Result<std::collections::HashMap<String, LastMessageInfo>, sqlx::Error> {
        if conversation_ids.is_empty() {
            return Ok(std::collections::HashMap::new());
        }

        let rows = sqlx::query_as::<_, PgLastMessageRow>(
            "SELECT m1.conversation_id, m1.content, m1.role, m1.created_at, m1.status, m1.is_read
             FROM messages m1
             INNER JOIN (
                 SELECT conversation_id, MAX(created_at) as max_created
                 FROM messages
                 WHERE conversation_id = ANY($1)
                 GROUP BY conversation_id
             ) m2 ON m1.conversation_id = m2.conversation_id
                 AND m1.created_at = m2.max_created",
        )
        .bind(conversation_ids.to_vec())
        .fetch_all(pg)
        .await?;

        let mut result = std::collections::HashMap::new();
        for row in rows {
            let conv_id = row.conversation_id.clone();
            result.insert(conv_id, LastMessageInfo::from(row));
        }
        Ok(result)
    }
}
