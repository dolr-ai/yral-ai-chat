use std::collections::HashMap;

use sqlx::{PgPool, SqlitePool};
use uuid::Uuid;

use super::parse_dt;
use crate::db::pg_write;
use crate::models::entities::{Message, MessageRole, MessageType};

pub struct MessageRepository {
    pool: SqlitePool,
    pg_pool: Option<PgPool>,
    pg_read: bool,
}

// ── SQLite row ────────────────────────────────────────────────────────────────

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

// ── PostgreSQL row ────────────────────────────────────────────────────────────

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

// ── Column list (same names for both DBs) ─────────────────────────────────────

const SELECT_COLS: &str = "id, conversation_id, role, content, message_type, media_urls, audio_url,
     audio_duration_seconds, token_count, client_message_id, created_at, metadata,
     status, is_read";

// ── Repository ────────────────────────────────────────────────────────────────

impl MessageRepository {
    pub fn new(pool: SqlitePool, pg_pool: Option<PgPool>, pg_read: bool) -> Self {
        Self {
            pool,
            pg_pool,
            pg_read,
        }
    }

    fn use_pg(&self) -> Option<&PgPool> {
        if self.pg_read { self.pg_pool.as_ref() } else { None }
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

        // Also bump conversation updated_at
        sqlx::query("UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?")
            .bind(conversation_id)
            .execute(&self.pool)
            .await?;

        // Dual-write to PG
        if let Some(ref pg) = self.pg_pool {
            let conv_info: Option<(String, String)> =
                sqlx::query_as("SELECT user_id, influencer_id FROM conversations WHERE id = ?")
                    .bind(conversation_id)
                    .fetch_optional(&self.pool)
                    .await
                    .ok()
                    .flatten();

            let pg = pg.clone();
            let id = message_id.clone();
            let conv_id = conversation_id.to_string();
            let role_str = role.as_ref().to_string();
            let content_owned = content.map(|s| s.to_string());
            let mt = message_type.as_ref().to_string();
            let mu_json = media_urls_json.clone();
            let au = audio_url.map(|s| s.to_string());
            let cmid = client_message_id.map(|s| s.to_string());
            tokio::spawn(async move {
                if let Some((user_id, influencer_id)) = conv_info
                    && let Err(e) =
                        pg_write::pg_insert_conversation(&pg, &conv_id, &user_id, &influencer_id)
                            .await
                {
                    tracing::warn!(error = %e, "PG dual-write failed for ensure_conversation");
                }
                if let Err(e) = pg_write::pg_insert_message(
                    &pg,
                    &id,
                    &conv_id,
                    &role_str,
                    content_owned.as_deref(),
                    &mt,
                    &mu_json,
                    au.as_deref(),
                    audio_duration_seconds,
                    token_count,
                    cmid.as_deref(),
                    "delivered",
                    false,
                )
                .await
                {
                    tracing::warn!(error = %e, "PG dual-write failed for insert_message");
                }
                if let Err(e) = pg_write::pg_bump_conversation_updated_at(&pg, &conv_id).await {
                    tracing::warn!(error = %e, "PG dual-write failed for bump_conversation_updated_at");
                }
            });
        }

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

        if let Some(ref pg) = self.pg_pool {
            let pg = pg.clone();
            let conv_id = conversation_id.to_string();
            tokio::spawn(async move {
                if let Err(e) = pg_write::pg_delete_messages_by_conversation(&pg, &conv_id).await {
                    tracing::warn!(error = %e, "PG dual-write failed for delete_messages_by_conversation");
                }
            });
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

        if let Some(ref pg) = self.pg_pool {
            let pg = pg.clone();
            let conv_id = conversation_id.to_string();
            tokio::spawn(async move {
                if let Err(e) = pg_write::pg_mark_as_read(&pg, &conv_id).await {
                    tracing::warn!(error = %e, "PG dual-write failed for mark_as_read");
                }
            });
        }

        Ok(())
    }

    // ── Reads ─────────────────────────────────────────────────────────────────

    pub async fn get_by_id(&self, message_id: &str) -> Result<Option<Message>, sqlx::Error> {
        if let Some(pg) = self.use_pg() {
            let row = sqlx::query_as::<_, PgMessageRow>(&format!(
                "SELECT {SELECT_COLS} FROM messages WHERE id = $1"
            ))
            .bind(message_id)
            .fetch_optional(pg)
            .await?;
            return Ok(row.map(Message::from));
        }

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
        if let Some(pg) = self.use_pg() {
            let row = sqlx::query_as::<_, PgMessageRow>(&format!(
                "SELECT {SELECT_COLS} FROM messages
                 WHERE conversation_id = $1 AND client_message_id = $2"
            ))
            .bind(conversation_id)
            .bind(client_message_id)
            .fetch_optional(pg)
            .await?;
            return Ok(row.map(Message::from));
        }

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
        // get_by_id already dispatches to PG when pg_read is true
        let msg = match self.get_by_id(message_id).await? {
            Some(m) => m,
            None => return Ok(None),
        };

        if let Some(pg) = self.use_pg() {
            let row = sqlx::query_as::<_, PgMessageRow>(&format!(
                "SELECT {SELECT_COLS} FROM messages
                 WHERE conversation_id = $1
                   AND role = 'assistant'
                   AND created_at >= $2
                   AND id != $3
                 ORDER BY created_at ASC
                 LIMIT 1"
            ))
            .bind(&msg.conversation_id)
            .bind(msg.created_at)
            .bind(message_id)
            .fetch_optional(pg)
            .await?;
            return Ok(row.map(Message::from));
        }

        let row = sqlx::query_as::<_, MessageRow>(&format!(
            "SELECT {SELECT_COLS} FROM messages
             WHERE conversation_id = ?
               AND role = 'assistant'
               AND created_at >= ?
               AND id != ?
             ORDER BY created_at ASC
             LIMIT 1"
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

        if let Some(pg) = self.use_pg() {
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
                .fetch_all(pg)
                .await?;
            return Ok(rows.into_iter().map(Message::from).collect());
        }

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
        if let Some(pg) = self.use_pg() {
            let rows = sqlx::query_as::<_, PgMessageRow>(&format!(
                "SELECT {SELECT_COLS} FROM messages
                 WHERE conversation_id = $1
                 ORDER BY created_at DESC
                 LIMIT $2"
            ))
            .bind(conversation_id)
            .bind(limit)
            .fetch_all(pg)
            .await?;
            let mut messages: Vec<Message> = rows.into_iter().map(Message::from).collect();
            messages.reverse();
            return Ok(messages);
        }

        let rows = sqlx::query_as::<_, MessageRow>(&format!(
            "SELECT {SELECT_COLS} FROM messages
             WHERE conversation_id = ?
             ORDER BY created_at DESC
             LIMIT ?"
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

        if let Some(pg) = self.use_pg() {
            let rows = sqlx::query_as::<_, PgMessageRow>(&format!(
                "WITH RankedMessages AS (
                    SELECT {SELECT_COLS},
                           ROW_NUMBER() OVER (
                               PARTITION BY conversation_id
                               ORDER BY created_at DESC
                           ) as rn
                    FROM messages
                    WHERE conversation_id = ANY($1)
                )
                SELECT {SELECT_COLS}
                FROM RankedMessages
                WHERE rn <= $2
                ORDER BY conversation_id, created_at ASC"
            ))
            .bind(conversation_ids.to_vec())
            .bind(limit_per_conv)
            .fetch_all(pg)
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
            return Ok(result);
        }

        let placeholders: Vec<&str> = conversation_ids.iter().map(|_| "?").collect();
        let sql = format!(
            "WITH RankedMessages AS (
                SELECT {SELECT_COLS},
                       ROW_NUMBER() OVER (
                           PARTITION BY conversation_id
                           ORDER BY created_at DESC
                       ) as rn
                FROM messages
                WHERE conversation_id IN ({})
            )
            SELECT {SELECT_COLS}
            FROM RankedMessages
            WHERE rn <= ?
            ORDER BY conversation_id, created_at ASC",
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
        if let Some(pg) = self.use_pg() {
            let count: (i64,) =
                sqlx::query_as("SELECT COUNT(*) FROM messages WHERE conversation_id = $1")
                    .bind(conversation_id)
                    .fetch_one(pg)
                    .await?;
            return Ok(count.0);
        }

        let count: (i64,) =
            sqlx::query_as("SELECT COUNT(*) FROM messages WHERE conversation_id = ?")
                .bind(conversation_id)
                .fetch_one(&self.pool)
                .await?;
        Ok(count.0)
    }

    pub async fn count_unread(&self, conversation_id: &str) -> Result<i64, sqlx::Error> {
        if let Some(pg) = self.use_pg() {
            let count: (i64,) = sqlx::query_as(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = $1 AND is_read = FALSE AND role = 'assistant'",
            )
            .bind(conversation_id)
            .fetch_one(pg)
            .await?;
            return Ok(count.0);
        }

        let count: (i64,) = sqlx::query_as(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ? AND is_read = 0 AND role = 'assistant'",
        )
        .bind(conversation_id)
        .fetch_one(&self.pool)
        .await?;
        Ok(count.0)
    }
}
