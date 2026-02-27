use sqlx::SqlitePool;
use uuid::Uuid;

use super::{parse_dt, parse_json};
use crate::models::entities::{
    AIInfluencer, Conversation, InfluencerStatus, LastMessageInfo, MessageRole,
};

pub struct ConversationRepository {
    pool: SqlitePool,
}

#[derive(sqlx::FromRow)]
struct ConversationRow {
    id: String,
    user_id: String,
    influencer_id: String,
    created_at: String,
    updated_at: String,
    metadata: String,
    // Joined influencer fields
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

impl ConversationRepository {
    pub fn new(pool: SqlitePool) -> Self {
        Self { pool }
    }

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

        self.get_by_id(&conversation_id)
            .await?
            .ok_or(sqlx::Error::RowNotFound)
    }

    pub async fn get_by_id(
        &self,
        conversation_id: &str,
    ) -> Result<Option<Conversation>, sqlx::Error> {
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
        let rows = if let Some(inf_id) = influencer_id {
            sqlx::query_as::<_, ConversationRow>(
                "SELECT c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                        i.id as inf_id, i.name, i.display_name, i.avatar_url, i.suggested_messages,
                        COUNT(m.id) as message_count,
                        (SELECT COUNT(*) FROM messages m2 WHERE m2.conversation_id = c.id AND m2.is_read = 0 AND m2.role = 'assistant') as unread_count
                 FROM conversations c
                 JOIN ai_influencers i ON c.influencer_id = i.id
                 LEFT JOIN messages m ON c.id = m.conversation_id
                 WHERE c.user_id = ? AND c.influencer_id = ?
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
        } else {
            sqlx::query_as::<_, ConversationRow>(
                "SELECT c.id, c.user_id, c.influencer_id, c.created_at, c.updated_at, c.metadata,
                        i.id as inf_id, i.name, i.display_name, i.avatar_url, i.suggested_messages,
                        COUNT(m.id) as message_count,
                        (SELECT COUNT(*) FROM messages m2 WHERE m2.conversation_id = c.id AND m2.is_read = 0 AND m2.role = 'assistant') as unread_count
                 FROM conversations c
                 JOIN ai_influencers i ON c.influencer_id = i.id
                 LEFT JOIN messages m ON c.id = m.conversation_id
                 WHERE c.user_id = ?
                 GROUP BY c.id, i.id
                 ORDER BY c.updated_at DESC
                 LIMIT ? OFFSET ?",
            )
            .bind(user_id)
            .bind(limit)
            .bind(offset)
            .fetch_all(&self.pool)
            .await?
        };

        let mut conversations: Vec<Conversation> =
            rows.into_iter().map(Conversation::from).collect();

        // Batch fetch last messages
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
        if let Some(inf_id) = influencer_id {
            let count: (i64,) = sqlx::query_as(
                "SELECT COUNT(*) FROM conversations WHERE user_id = ? AND influencer_id = ?",
            )
            .bind(user_id)
            .bind(inf_id)
            .fetch_one(&self.pool)
            .await?;
            Ok(count.0)
        } else {
            let count: (i64,) =
                sqlx::query_as("SELECT COUNT(*) FROM conversations WHERE user_id = ?")
                    .bind(user_id)
                    .fetch_one(&self.pool)
                    .await?;
            Ok(count.0)
        }
    }

    /// List conversations where the given influencer_id is the bot (for bot callers).
    pub async fn list_by_influencer(
        &self,
        influencer_id: &str,
        limit: i64,
        offset: i64,
    ) -> Result<Vec<Conversation>, sqlx::Error> {
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

        // Batch fetch last messages
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
        let count: (i64,) =
            sqlx::query_as("SELECT COUNT(*) FROM conversations WHERE influencer_id = ?")
                .bind(influencer_id)
                .fetch_one(&self.pool)
                .await?;
        Ok(count.0)
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
        Ok(())
    }

    pub async fn delete(&self, conversation_id: &str) -> Result<(), sqlx::Error> {
        sqlx::query("DELETE FROM conversations WHERE id = ?")
            .bind(conversation_id)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

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
}
