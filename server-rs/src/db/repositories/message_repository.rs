use sqlx::SqlitePool;
use uuid::Uuid;

use crate::models::entities::{Message, MessageRole, MessageType};

pub struct MessageRepository {
    pool: SqlitePool,
}

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
}

impl From<MessageRow> for Message {
    fn from(row: MessageRow) -> Self {
        let media_urls: Vec<String> = serde_json::from_str(&row.media_urls).unwrap_or_default();
        let metadata: serde_json::Value = serde_json::from_str(&row.metadata)
            .unwrap_or(serde_json::Value::Object(Default::default()));
        let role = MessageRole::from_str(&row.role).unwrap_or(MessageRole::User);
        let message_type = MessageType::from_str(&row.message_type).unwrap_or(MessageType::Text);
        let created_at =
            chrono::NaiveDateTime::parse_from_str(&row.created_at, "%Y-%m-%d %H:%M:%S")
                .unwrap_or_default();

        Self {
            id: row.id,
            conversation_id: row.conversation_id,
            role,
            content: row.content,
            message_type,
            media_urls,
            audio_url: row.audio_url,
            audio_duration_seconds: row.audio_duration_seconds,
            token_count: row.token_count,
            client_message_id: row.client_message_id,
            created_at,
            metadata,
        }
    }
}

impl MessageRepository {
    pub fn new(pool: SqlitePool) -> Self {
        Self { pool }
    }

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
        let media_urls_json = serde_json::to_string(media_urls).unwrap_or_else(|_| "[]".to_string());

        sqlx::query(
            "INSERT INTO messages (
                id, conversation_id, role, content, message_type,
                media_urls, audio_url, audio_duration_seconds, token_count,
                client_message_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(&message_id)
        .bind(conversation_id)
        .bind(role.as_str())
        .bind(content)
        .bind(message_type.as_str())
        .bind(&media_urls_json)
        .bind(audio_url)
        .bind(audio_duration_seconds)
        .bind(token_count)
        .bind(client_message_id)
        .execute(&self.pool)
        .await?;

        self.get_by_id(&message_id)
            .await?
            .ok_or(sqlx::Error::RowNotFound)
    }

    pub async fn get_by_id(&self, message_id: &str) -> Result<Option<Message>, sqlx::Error> {
        let row = sqlx::query_as::<_, MessageRow>(
            "SELECT id, conversation_id, role, content, message_type,
                    media_urls, audio_url, audio_duration_seconds,
                    token_count, client_message_id, created_at, metadata
             FROM messages WHERE id = ?",
        )
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
        let row = sqlx::query_as::<_, MessageRow>(
            "SELECT id, conversation_id, role, content, message_type,
                    media_urls, audio_url, audio_duration_seconds,
                    token_count, client_message_id, created_at, metadata
             FROM messages
             WHERE conversation_id = ? AND client_message_id = ?",
        )
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

        let row = sqlx::query_as::<_, MessageRow>(
            "SELECT id, conversation_id, role, content, message_type,
                    media_urls, audio_url, audio_duration_seconds,
                    token_count, client_message_id, created_at, metadata
             FROM messages
             WHERE conversation_id = ?
               AND role = 'assistant'
               AND created_at >= ?
               AND id != ?
             ORDER BY created_at ASC
             LIMIT 1",
        )
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
            "SELECT id, conversation_id, role, content, message_type,
                    media_urls, audio_url, audio_duration_seconds,
                    token_count, client_message_id, created_at, metadata
             FROM messages
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
        let rows = sqlx::query_as::<_, MessageRow>(
            "SELECT id, conversation_id, role, content, message_type,
                    media_urls, audio_url, audio_duration_seconds,
                    token_count, client_message_id, created_at, metadata
             FROM messages
             WHERE conversation_id = ?
             ORDER BY created_at DESC
             LIMIT ?",
        )
        .bind(conversation_id)
        .bind(limit)
        .fetch_all(&self.pool)
        .await?;

        let mut messages: Vec<Message> = rows.into_iter().map(Message::from).collect();
        messages.reverse(); // oldest first for context
        Ok(messages)
    }

    pub async fn get_recent_for_conversations_batch(
        &self,
        conversation_ids: &[String],
        limit_per_conv: i64,
    ) -> Result<std::collections::HashMap<String, Vec<Message>>, sqlx::Error> {
        if conversation_ids.is_empty() {
            return Ok(std::collections::HashMap::new());
        }

        let placeholders: Vec<&str> = conversation_ids.iter().map(|_| "?").collect();
        let sql = format!(
            "WITH RankedMessages AS (
                SELECT id, conversation_id, role, content, message_type,
                       media_urls, audio_url, audio_duration_seconds,
                       token_count, client_message_id, created_at, metadata,
                       ROW_NUMBER() OVER (
                           PARTITION BY conversation_id
                           ORDER BY created_at DESC
                       ) as rn
                FROM messages
                WHERE conversation_id IN ({})
            )
            SELECT id, conversation_id, role, content, message_type,
                   media_urls, audio_url, audio_duration_seconds,
                   token_count, client_message_id, created_at, metadata
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

        let mut result: std::collections::HashMap<String, Vec<Message>> = conversation_ids
            .iter()
            .map(|id| (id.clone(), Vec::new()))
            .collect();

        for row in rows {
            let conv_id = row.conversation_id.clone();
            let msg = Message::from(row);
            if let Some(messages) = result.get_mut(&conv_id) {
                messages.push(msg);
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

    pub async fn count_all(&self) -> Result<i64, sqlx::Error> {
        let count: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM messages")
            .fetch_one(&self.pool)
            .await?;
        Ok(count.0)
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
}
