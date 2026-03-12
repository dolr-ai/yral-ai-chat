use std::collections::HashMap;

#[cfg(not(feature = "staging"))]
use sqlx::PgPool;
#[cfg(feature = "staging")]
use sqlx::SqlitePool;

use uuid::Uuid;

#[cfg(feature = "staging")]
use super::parse_dt;

use crate::models::entities::{Message, MessageRole, MessageType};

// ── Staging: SQLite-only ──────────────────────────────────────────────────────

#[cfg(feature = "staging")]
pub struct MessageRepository {
    pool: SqlitePool,
}

#[cfg(feature = "staging")]
#[derive(sqlx::FromRow)]
struct MessageRow {
    id: String,
    conversation_id: String,
    role: String,
    content: Option<String>,
    message_type: String,
    media_urls: String,
    audio_url: Option<String>,
    audio_duration_seconds: Option<i32>,
    token_count: Option<i32>,
    client_message_id: Option<String>,
    created_at: String,
    metadata: String,
    status: Option<String>,
    is_read: Option<i32>,
}

#[cfg(feature = "staging")]
impl From<MessageRow> for Message {
    fn from(row: MessageRow) -> Self {
        Self {
            id: row.id,
            conversation_id: row.conversation_id,
            role: row.role.parse().unwrap_or(MessageRole::User),
            content: row.content,
            message_type: row.message_type.parse().unwrap_or(MessageType::Text),
            media_urls: serde_json::from_str(&row.media_urls).unwrap_or_default(),
            audio_url: row.audio_url,
            audio_duration_seconds: row.audio_duration_seconds,
            token_count: row.token_count,
            client_message_id: row.client_message_id,
            created_at: parse_dt(&row.created_at),
            metadata: serde_json::from_str(&row.metadata)
                .unwrap_or(serde_json::Value::Object(Default::default())),
            status: row.status.unwrap_or("delivered".to_string()),
            is_read: row.is_read.unwrap_or(0) != 0,
        }
    }
}

#[cfg(feature = "staging")]
const SELECT_COLS: &str = "id, conversation_id, role, content, message_type, media_urls, audio_url,
     audio_duration_seconds, token_count, client_message_id, created_at, metadata,
     status, is_read";

#[cfg(feature = "staging")]
impl MessageRepository {
    pub fn new(pool: SqlitePool) -> Self {
        Self { pool }
    }

    // ── Writes ────────────────────────────────────────────────────────────────

    #[allow(clippy::too_many_arguments)]
    pub async fn create(
        &self,
        conversation_id: &str,
        role: &MessageRole,
        content: Option<&str>,
        message_type: &MessageType,
        media_urls: &[String],
        audio_url: Option<&str>,
        audio_duration_seconds: Option<i32>,
        token_count: Option<i32>,
        client_message_id: Option<&str>,
    ) -> Result<Message, sqlx::Error> {
        let message_id = Uuid::new_v4().to_string();
        let media_urls_json = serde_json::to_string(media_urls).unwrap_or("[]".to_string());

        sqlx::query(
            "INSERT INTO messages (
                id, conversation_id, role, content, message_type,
                media_urls, audio_url, audio_duration_seconds, token_count,
                client_message_id, status, is_read
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(&message_id)
        .bind(conversation_id)
        .bind(role.as_ref())
        .bind(content)
        .bind(message_type.as_ref())
        .bind(&media_urls_json)
        .bind(audio_url)
        .bind(audio_duration_seconds)
        .bind(token_count)
        .bind(client_message_id)
        .bind("delivered")
        .bind(0)
        .execute(&self.pool)
        .await?;

        sqlx::query("UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?")
            .bind(conversation_id)
            .execute(&self.pool)
            .await?;

        self.get_by_id(&message_id)
            .await?
            .ok_or(sqlx::Error::RowNotFound)
    }

    pub async fn delete_by_conversation(&self, conversation_id: &str) -> Result<i64, sqlx::Error> {
        let count: (i64,) =
            sqlx::query_as("SELECT COUNT(*) FROM messages WHERE conversation_id = ?")
                .bind(conversation_id)
                .fetch_one(&self.pool)
                .await?;

        if count.0 > 0 {
            sqlx::query("DELETE FROM messages WHERE conversation_id = ?")
                .bind(conversation_id)
                .execute(&self.pool)
                .await?;
        }

        Ok(count.0)
    }

    pub async fn mark_as_read(&self, conversation_id: &str) -> Result<(), sqlx::Error> {
        sqlx::query(
            "UPDATE messages SET is_read = 1, status = 'read'
             WHERE conversation_id = ? AND is_read = 0 AND role = 'assistant'",
        )
        .bind(conversation_id)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    // ── Reads ─────────────────────────────────────────────────────────────────

    pub async fn get_by_id(&self, message_id: &str) -> Result<Option<Message>, sqlx::Error> {
        let row = sqlx::query_as::<_, MessageRow>(&format!(
            "SELECT {SELECT_COLS} FROM messages WHERE id = ?"
        ))
        .bind(message_id)
        .fetch_optional(&self.pool)
        .await?;
        Ok(row.map(Message::from))
    }

    pub async fn get_by_client_id(
        &self,
        conversation_id: &str,
        client_message_id: &str,
    ) -> Result<Option<Message>, sqlx::Error> {
        let row = sqlx::query_as::<_, MessageRow>(&format!(
            "SELECT {SELECT_COLS} FROM messages WHERE conversation_id = ? AND client_message_id = ?"
        ))
        .bind(conversation_id)
        .bind(client_message_id)
        .fetch_optional(&self.pool)
        .await?;
        Ok(row.map(Message::from))
    }

    pub async fn get_assistant_reply(
        &self,
        message_id: &str,
    ) -> Result<Option<Message>, sqlx::Error> {
        let msg = match self.get_by_id(message_id).await? {
            Some(m) => m,
            None => return Ok(None),
        };
        let row = sqlx::query_as::<_, MessageRow>(&format!(
            "SELECT {SELECT_COLS} FROM messages
             WHERE conversation_id = ? AND role = 'assistant'
               AND created_at >= ? AND id != ?
             ORDER BY created_at ASC LIMIT 1"
        ))
        .bind(&msg.conversation_id)
        .bind(msg.created_at.format("%Y-%m-%d %H:%M:%S").to_string())
        .bind(message_id)
        .fetch_optional(&self.pool)
        .await?;
        Ok(row.map(Message::from))
    }

    pub async fn list_by_conversation(
        &self,
        conversation_id: &str,
        limit: i64,
        offset: i64,
        order: &str,
    ) -> Result<Vec<Message>, sqlx::Error> {
        let order_clause = if order == "asc" { "ASC" } else { "DESC" };
        let sql = format!(
            "SELECT {SELECT_COLS} FROM messages
             WHERE conversation_id = ?
             ORDER BY created_at {order_clause}
             LIMIT ? OFFSET ?"
        );
        let rows = sqlx::query_as::<_, MessageRow>(&sql)
            .bind(conversation_id)
            .bind(limit)
            .bind(offset)
            .fetch_all(&self.pool)
            .await?;
        Ok(rows.into_iter().map(Message::from).collect())
    }

    pub async fn get_recent_for_context(
        &self,
        conversation_id: &str,
        limit: i64,
    ) -> Result<Vec<Message>, sqlx::Error> {
        let rows = sqlx::query_as::<_, MessageRow>(&format!(
            "SELECT {SELECT_COLS} FROM messages
             WHERE conversation_id = ?
             ORDER BY created_at DESC LIMIT ?"
        ))
        .bind(conversation_id)
        .bind(limit)
        .fetch_all(&self.pool)
        .await?;
        let mut messages: Vec<Message> = rows.into_iter().map(Message::from).collect();
        messages.reverse();
        Ok(messages)
    }

    pub async fn get_recent_for_conversations_batch(
        &self,
        conversation_ids: &[String],
        limit_per_conv: i64,
    ) -> Result<HashMap<String, Vec<Message>>, sqlx::Error> {
        if conversation_ids.is_empty() {
            return Ok(HashMap::new());
        }

        let placeholders: Vec<&str> = conversation_ids.iter().map(|_| "?").collect();
        let sql = format!(
            "WITH RankedMessages AS (
                SELECT {SELECT_COLS},
                       ROW_NUMBER() OVER (
                           PARTITION BY conversation_id ORDER BY created_at DESC
                       ) as rn
                FROM messages WHERE conversation_id IN ({})
            )
            SELECT {SELECT_COLS} FROM RankedMessages
            WHERE rn <= ? ORDER BY conversation_id, created_at ASC",
            placeholders.join(", ")
        );

        let mut query = sqlx::query_as::<_, MessageRow>(&sql);
        for id in conversation_ids {
            query = query.bind(id);
        }
        query = query.bind(limit_per_conv);

        let rows = query.fetch_all(&self.pool).await?;
        let mut result: HashMap<String, Vec<Message>> = conversation_ids
            .iter()
            .map(|id| (id.clone(), Vec::new()))
            .collect();
        for row in rows {
            let conv_id = row.conversation_id.clone();
            if let Some(messages) = result.get_mut(&conv_id) {
                messages.push(Message::from(row));
            }
        }
        Ok(result)
    }

    pub async fn count_by_conversation(&self, conversation_id: &str) -> Result<i64, sqlx::Error> {
        let count: (i64,) =
            sqlx::query_as("SELECT COUNT(*) FROM messages WHERE conversation_id = ?")
                .bind(conversation_id)
                .fetch_one(&self.pool)
                .await?;
        Ok(count.0)
    }

    pub async fn count_unread(&self, conversation_id: &str) -> Result<i64, sqlx::Error> {
        let count: (i64,) = sqlx::query_as(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ? AND is_read = 0 AND role = 'assistant'",
        )
        .bind(conversation_id)
        .fetch_one(&self.pool)
        .await?;
        Ok(count.0)
    }
}

// ── Non-staging: PostgreSQL-only ──────────────────────────────────────────────

#[cfg(not(feature = "staging"))]
pub struct MessageRepository {
    pg_pool: PgPool,
}

#[cfg(not(feature = "staging"))]
#[derive(sqlx::FromRow)]
struct PgMessageRow {
    id: String,
    conversation_id: String,
    role: String,
    content: Option<String>,
    message_type: String,
    media_urls: serde_json::Value,
    audio_url: Option<String>,
    audio_duration_seconds: Option<i32>,
    token_count: Option<i32>,
    client_message_id: Option<String>,
    created_at: chrono::NaiveDateTime,
    metadata: serde_json::Value,
    status: Option<String>,
    is_read: Option<bool>,
}

#[cfg(not(feature = "staging"))]
impl From<PgMessageRow> for Message {
    fn from(row: PgMessageRow) -> Self {
        Self {
            id: row.id,
            conversation_id: row.conversation_id,
            role: row.role.parse().unwrap_or(MessageRole::User),
            content: row.content,
            message_type: row.message_type.parse().unwrap_or(MessageType::Text),
            media_urls: serde_json::from_value(row.media_urls).unwrap_or_default(),
            audio_url: row.audio_url,
            audio_duration_seconds: row.audio_duration_seconds,
            token_count: row.token_count,
            client_message_id: row.client_message_id,
            created_at: row.created_at,
            metadata: row.metadata,
            status: row.status.unwrap_or("delivered".to_string()),
            is_read: row.is_read.unwrap_or(false),
        }
    }
}

#[cfg(not(feature = "staging"))]
const SELECT_COLS: &str = "id, conversation_id, role, content, message_type, media_urls, audio_url,
     audio_duration_seconds, token_count, client_message_id, created_at, metadata,
     status, is_read";

#[cfg(not(feature = "staging"))]
impl MessageRepository {
    pub fn new(pg_pool: PgPool) -> Self {
        Self { pg_pool }
    }

    // ── Writes ────────────────────────────────────────────────────────────────

    #[allow(clippy::too_many_arguments)]
    pub async fn create(
        &self,
        conversation_id: &str,
        role: &MessageRole,
        content: Option<&str>,
        message_type: &MessageType,
        media_urls: &[String],
        audio_url: Option<&str>,
        audio_duration_seconds: Option<i32>,
        token_count: Option<i32>,
        client_message_id: Option<&str>,
    ) -> Result<Message, sqlx::Error> {
        let message_id = Uuid::new_v4().to_string();
        let media_urls_json =
            serde_json::to_value(media_urls).unwrap_or(serde_json::Value::Array(vec![]));

        sqlx::query(
            "INSERT INTO messages (
                id, conversation_id, role, content, message_type,
                media_urls, audio_url, audio_duration_seconds, token_count,
                client_message_id, status, is_read
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)",
        )
        .bind(&message_id)
        .bind(conversation_id)
        .bind(role.as_ref())
        .bind(content)
        .bind(message_type.as_ref())
        .bind(&media_urls_json)
        .bind(audio_url)
        .bind(audio_duration_seconds)
        .bind(token_count)
        .bind(client_message_id)
        .bind("delivered")
        .bind(false)
        .execute(&self.pg_pool)
        .await?;

        sqlx::query("UPDATE conversations SET updated_at = NOW() WHERE id = $1")
            .bind(conversation_id)
            .execute(&self.pg_pool)
            .await?;

        self.get_by_id(&message_id)
            .await?
            .ok_or(sqlx::Error::RowNotFound)
    }

    pub async fn delete_by_conversation(&self, conversation_id: &str) -> Result<i64, sqlx::Error> {
        let count: (i64,) =
            sqlx::query_as("SELECT COUNT(*) FROM messages WHERE conversation_id = $1")
                .bind(conversation_id)
                .fetch_one(&self.pg_pool)
                .await?;

        if count.0 > 0 {
            sqlx::query("DELETE FROM messages WHERE conversation_id = $1")
                .bind(conversation_id)
                .execute(&self.pg_pool)
                .await?;
        }

        Ok(count.0)
    }

    pub async fn mark_as_read(&self, conversation_id: &str) -> Result<(), sqlx::Error> {
        sqlx::query(
            "UPDATE messages SET is_read = TRUE, status = 'read'
             WHERE conversation_id = $1 AND is_read = FALSE AND role = 'assistant'",
        )
        .bind(conversation_id)
        .execute(&self.pg_pool)
        .await?;
        Ok(())
    }

    // ── Reads ─────────────────────────────────────────────────────────────────

    pub async fn get_by_id(&self, message_id: &str) -> Result<Option<Message>, sqlx::Error> {
        let row = sqlx::query_as::<_, PgMessageRow>(&format!(
            "SELECT {SELECT_COLS} FROM messages WHERE id = $1"
        ))
        .bind(message_id)
        .fetch_optional(&self.pg_pool)
        .await?;
        Ok(row.map(Message::from))
    }

    pub async fn get_by_client_id(
        &self,
        conversation_id: &str,
        client_message_id: &str,
    ) -> Result<Option<Message>, sqlx::Error> {
        let row = sqlx::query_as::<_, PgMessageRow>(&format!(
            "SELECT {SELECT_COLS} FROM messages
             WHERE conversation_id = $1 AND client_message_id = $2"
        ))
        .bind(conversation_id)
        .bind(client_message_id)
        .fetch_optional(&self.pg_pool)
        .await?;
        Ok(row.map(Message::from))
    }

    pub async fn get_assistant_reply(
        &self,
        message_id: &str,
    ) -> Result<Option<Message>, sqlx::Error> {
        let msg = match self.get_by_id(message_id).await? {
            Some(m) => m,
            None => return Ok(None),
        };
        let row = sqlx::query_as::<_, PgMessageRow>(&format!(
            "SELECT {SELECT_COLS} FROM messages
             WHERE conversation_id = $1 AND role = 'assistant'
               AND created_at >= $2 AND id != $3
             ORDER BY created_at ASC LIMIT 1"
        ))
        .bind(&msg.conversation_id)
        .bind(msg.created_at)
        .bind(message_id)
        .fetch_optional(&self.pg_pool)
        .await?;
        Ok(row.map(Message::from))
    }

    pub async fn list_by_conversation(
        &self,
        conversation_id: &str,
        limit: i64,
        offset: i64,
        order: &str,
    ) -> Result<Vec<Message>, sqlx::Error> {
        let order_clause = if order == "asc" { "ASC" } else { "DESC" };
        let sql = format!(
            "SELECT {SELECT_COLS} FROM messages
             WHERE conversation_id = $1
             ORDER BY created_at {order_clause}
             LIMIT $2 OFFSET $3"
        );
        let rows = sqlx::query_as::<_, PgMessageRow>(&sql)
            .bind(conversation_id)
            .bind(limit)
            .bind(offset)
            .fetch_all(&self.pg_pool)
            .await?;
        Ok(rows.into_iter().map(Message::from).collect())
    }

    pub async fn get_recent_for_context(
        &self,
        conversation_id: &str,
        limit: i64,
    ) -> Result<Vec<Message>, sqlx::Error> {
        let rows = sqlx::query_as::<_, PgMessageRow>(&format!(
            "SELECT {SELECT_COLS} FROM messages
             WHERE conversation_id = $1
             ORDER BY created_at DESC LIMIT $2"
        ))
        .bind(conversation_id)
        .bind(limit)
        .fetch_all(&self.pg_pool)
        .await?;
        let mut messages: Vec<Message> = rows.into_iter().map(Message::from).collect();
        messages.reverse();
        Ok(messages)
    }

    pub async fn get_recent_for_conversations_batch(
        &self,
        conversation_ids: &[String],
        limit_per_conv: i64,
    ) -> Result<HashMap<String, Vec<Message>>, sqlx::Error> {
        if conversation_ids.is_empty() {
            return Ok(HashMap::new());
        }

        let rows = sqlx::query_as::<_, PgMessageRow>(&format!(
            "WITH RankedMessages AS (
                SELECT {SELECT_COLS},
                       ROW_NUMBER() OVER (
                           PARTITION BY conversation_id ORDER BY created_at DESC
                       ) as rn
                FROM messages WHERE conversation_id = ANY($1)
            )
            SELECT {SELECT_COLS} FROM RankedMessages
            WHERE rn <= $2 ORDER BY conversation_id, created_at ASC"
        ))
        .bind(conversation_ids.to_vec())
        .bind(limit_per_conv)
        .fetch_all(&self.pg_pool)
        .await?;

        let mut result: HashMap<String, Vec<Message>> = conversation_ids
            .iter()
            .map(|id| (id.clone(), Vec::new()))
            .collect();
        for row in rows {
            let conv_id = row.conversation_id.clone();
            if let Some(messages) = result.get_mut(&conv_id) {
                messages.push(Message::from(row));
            }
        }
        Ok(result)
    }

    pub async fn count_by_conversation(&self, conversation_id: &str) -> Result<i64, sqlx::Error> {
        let count: (i64,) =
            sqlx::query_as("SELECT COUNT(*) FROM messages WHERE conversation_id = $1")
                .bind(conversation_id)
                .fetch_one(&self.pg_pool)
                .await?;
        Ok(count.0)
    }

    pub async fn count_unread(&self, conversation_id: &str) -> Result<i64, sqlx::Error> {
        let count: (i64,) = sqlx::query_as(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = $1 AND is_read = FALSE AND role = 'assistant'",
        )
        .bind(conversation_id)
        .fetch_one(&self.pg_pool)
        .await?;
        Ok(count.0)
    }
}
