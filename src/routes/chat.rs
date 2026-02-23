use std::collections::HashMap;
use std::sync::Arc;

use axum::Json;
use axum::extract::{Path, Query, State};
use axum::http::StatusCode;

use crate::AppState;
use crate::db::repositories::{ConversationRepository, InfluencerRepository, MessageRepository};
use crate::error::AppError;
use crate::middleware::AuthenticatedUser;
use crate::models::entities::{AIInfluencer, InfluencerStatus, Message, MessageRole, MessageType};
use crate::models::requests::{
    CreateConversationRequest, GenerateImageRequest, ListConversationsParams, ListMessagesParams,
    SendMessageRequest,
};
use crate::models::responses::{
    ConversationResponse, DeleteConversationResponse, InfluencerBasicInfo,
    ListConversationsResponse, ListMessagesResponse, MarkConversationAsReadResponse,
    MessageResponse, SendMessageResponse,
};

const FALLBACK_ERROR_MESSAGE: &str =
    "I'm having trouble generating a response right now. Please try again.";

impl From<Message> for MessageResponse {
    fn from(m: Message) -> Self {
        Self {
            id: m.id,
            role: m.role,
            content: m.content,
            message_type: m.message_type,
            media_urls: m.media_urls,
            audio_url: m.audio_url,
            audio_duration_seconds: m.audio_duration_seconds,
            token_count: m.token_count,
            created_at: m.created_at,
            status: m.status,
            is_read: m.is_read,
        }
    }
}

fn influencer_to_basic_info(
    influencer: &AIInfluencer,
    include_suggested_messages: bool,
) -> InfluencerBasicInfo {
    InfluencerBasicInfo {
        id: influencer.id.clone(),
        name: influencer.name.clone(),
        display_name: influencer.display_name.clone(),
        avatar_url: influencer.avatar_url.clone(),
        is_online: influencer.is_active == InfluencerStatus::Active,
        suggested_messages: include_suggested_messages
            .then(|| influencer.suggested_messages.clone()),
    }
}

fn conversation_to_response(
    conv: crate::models::entities::Conversation,
    recent_messages: Option<Vec<Message>>,
    include_suggested_messages: bool,
) -> ConversationResponse {
    let influencer_info = conv
        .influencer
        .as_ref()
        .map(|i| influencer_to_basic_info(i, include_suggested_messages))
        .unwrap_or_else(|| InfluencerBasicInfo {
            id: conv.influencer_id.clone(),
            name: String::new(),
            display_name: String::new(),
            avatar_url: None,
            is_online: false,
            suggested_messages: None,
        });

    ConversationResponse {
        id: conv.id,
        user_id: conv.user_id,
        influencer: influencer_info,
        created_at: conv.created_at,
        updated_at: conv.updated_at,
        message_count: conv.message_count.unwrap_or(0),
        last_message: conv.last_message,
        recent_messages: recent_messages
            .map(|msgs| msgs.into_iter().map(MessageResponse::from).collect()),
    }
}

// POST /api/v1/chat/conversations
pub async fn create_conversation(
    State(state): State<Arc<AppState>>,
    user: AuthenticatedUser,
    Json(body): Json<CreateConversationRequest>,
) -> Result<(StatusCode, Json<ConversationResponse>), AppError> {
    let conv_repo = ConversationRepository::new(state.db.pool.clone());
    let inf_repo = InfluencerRepository::new(state.db.pool.clone());
    let msg_repo = MessageRepository::new(state.db.pool.clone());

    // Verify influencer exists
    let influencer = inf_repo
        .get_by_id(&body.influencer_id)
        .await?
        .ok_or_else(|| {
            AppError::not_found(format!("Influencer '{}' not found", body.influencer_id))
        })?;

    // Check for existing conversation
    if let Some(existing) = conv_repo
        .get_existing(&user.user_id, &body.influencer_id)
        .await?
    {
        let count = msg_repo.count_by_conversation(&existing.id).await?;
        let messages = msg_repo
            .list_by_conversation(&existing.id, 10, 0, "desc")
            .await?;

        let mut conv = existing;
        conv.message_count = Some(count);

        return Ok((
            StatusCode::CREATED,
            Json(conversation_to_response(conv, Some(messages), true)),
        ));
    }

    // Create new conversation
    let conv = conv_repo.create(&user.user_id, &body.influencer_id).await?;

    // Generate initial greeting if the influencer has one
    let initial_messages = match influencer.initial_greeting.as_deref() {
        Some(greeting) if !greeting.is_empty() => msg_repo
            .create(
                &conv.id,
                &MessageRole::Assistant,
                Some(greeting),
                &MessageType::Text,
                &[],
                None,
                None,
                None,
                None,
            )
            .await
            .map(|msg| vec![msg])
            .unwrap_or_else(|e| {
                tracing::error!(error = %e, "Failed to create initial greeting");
                vec![]
            }),
        _ => vec![],
    };

    Ok((
        StatusCode::CREATED,
        Json(conversation_to_response(conv, Some(initial_messages), true)),
    ))
}

// GET /api/v1/chat/conversations
pub async fn list_conversations(
    State(state): State<Arc<AppState>>,
    user: AuthenticatedUser,
    Query(params): Query<ListConversationsParams>,
) -> Result<Json<ListConversationsResponse>, AppError> {
    let conv_repo = ConversationRepository::new(state.db.pool.clone());
    let msg_repo = MessageRepository::new(state.db.pool.clone());

    let limit = params.limit();
    let offset = params.offset();
    let influencer_id = params.influencer_id.as_deref();

    let (conversations, total) = tokio::try_join!(
        conv_repo.list_by_user(&user.user_id, influencer_id, limit, offset),
        conv_repo.count_by_user(&user.user_id, influencer_id),
    )?;

    // Batch fetch recent messages
    let conv_ids: Vec<String> = conversations.iter().map(|c| c.id.clone()).collect();
    let recent_messages_map = msg_repo
        .get_recent_for_conversations_batch(&conv_ids, 10)
        .await?;

    let conversations = conversations
        .into_iter()
        .map(|conv| {
            let messages = recent_messages_map.get(&conv.id).cloned();
            // Only show suggested_messages if conversation has <= 1 message (empty or just greeting)
            let include_suggested = conv.message_count.unwrap_or(0) <= 1;
            conversation_to_response(conv, messages, include_suggested)
        })
        .collect();

    Ok(Json(ListConversationsResponse {
        conversations,
        total,
        limit,
        offset,
    }))
}

// GET /api/v1/chat/conversations/:conversation_id/messages
pub async fn list_messages(
    State(state): State<Arc<AppState>>,
    user: AuthenticatedUser,
    Path(conversation_id): Path<String>,
    Query(params): Query<ListMessagesParams>,
) -> Result<Json<ListMessagesResponse>, AppError> {
    let conv_repo = ConversationRepository::new(state.db.pool.clone());
    let msg_repo = MessageRepository::new(state.db.pool.clone());

    let conv = conv_repo
        .get_by_id(&conversation_id)
        .await?
        .ok_or_else(|| AppError::not_found("Conversation not found"))?;

    if conv.user_id != user.user_id {
        return Err(AppError::forbidden("Not your conversation"));
    }

    let limit = params.limit();
    let offset = params.offset();
    let order = params.order();

    let (messages, total) = tokio::try_join!(
        msg_repo.list_by_conversation(&conversation_id, limit, offset, order),
        msg_repo.count_by_conversation(&conversation_id),
    )?;

    Ok(Json(ListMessagesResponse {
        conversation_id,
        messages: messages.into_iter().map(MessageResponse::from).collect(),
        total,
        limit,
        offset,
    }))
}

// POST /api/v1/chat/conversations/:conversation_id/messages
pub async fn send_message(
    State(state): State<Arc<AppState>>,
    user: AuthenticatedUser,
    Path(conversation_id): Path<String>,
    Json(body): Json<SendMessageRequest>,
) -> Result<(StatusCode, Json<SendMessageResponse>), AppError> {
    let conv_repo = ConversationRepository::new(state.db.pool.clone());
    let msg_repo = MessageRepository::new(state.db.pool.clone());
    let inf_repo = InfluencerRepository::new(state.db.pool.clone());

    // Validate
    body.validate_content()
        .map_err(AppError::validation_error)?;

    let message_type = body
        .parsed_message_type()
        .ok_or_else(|| AppError::validation_error("Invalid message type"))?;

    // Verify conversation
    let conv = conv_repo
        .get_by_id(&conversation_id)
        .await?
        .ok_or_else(|| AppError::not_found("Conversation not found"))?;

    if conv.user_id != user.user_id {
        return Err(AppError::forbidden("Not your conversation"));
    }

    // Deduplication
    if let Some(ref client_id) = body.client_message_id
        && let Some(existing) = msg_repo
            .get_by_client_id(&conversation_id, client_id)
            .await?
        && let Some(reply) = msg_repo.get_assistant_reply(&existing.id).await?
    {
        return Ok((
            StatusCode::OK,
            Json(SendMessageResponse {
                user_message: MessageResponse::from(existing),
                assistant_message: MessageResponse::from(reply),
            }),
        ));
    }

    let influencer = inf_repo
        .get_by_id(&conv.influencer_id)
        .await?
        .ok_or_else(|| AppError::not_found("Influencer not found"))?;

    // Check if bot is discontinued
    if influencer.is_active == InfluencerStatus::Discontinued {
        return Err(AppError::forbidden(
            "This bot has been deleted and can no longer receive messages.",
        ));
    }

    // Transcribe audio if needed
    let transcribed_content = if message_type == MessageType::Audio {
        if let Some(ref audio_key) = body.audio_url {
            let presigned = state.storage.generate_presigned_url(audio_key);
            match state.gemini.transcribe_audio(&presigned).await {
                Ok(text) => Some(format!("[Transcribed: {text}]")),
                Err(e) => {
                    tracing::error!(error = %e, "Audio transcription failed");
                    Some("[Audio message - transcription unavailable]".to_string())
                }
            }
        } else {
            body.content.clone()
        }
    } else {
        body.content.clone()
    };

    // Save user message
    let user_message = msg_repo
        .create(
            &conversation_id,
            &MessageRole::User,
            transcribed_content.as_deref(),
            &message_type,
            body.media_urls.as_deref().unwrap_or(&[]),
            body.audio_url.as_deref(),
            body.audio_duration_seconds,
            None,
            body.client_message_id.as_deref(),
        )
        .await?;

    // Get conversation history (last 10 excluding current message)
    let all_recent = msg_repo
        .get_recent_for_context(&conversation_id, 11)
        .await?;
    let mut history: Vec<Message> = all_recent
        .into_iter()
        .filter(|m| m.id != user_message.id)
        .collect();
    let skip = history.len().saturating_sub(10);
    history.drain(..skip);

    // Presign S3 keys in history
    let s3_keys: Vec<String> = history
        .iter()
        .flat_map(|m| {
            m.media_urls
                .iter()
                .chain(m.audio_url.iter())
                .filter(|u| !u.starts_with("http"))
                .cloned()
        })
        .collect();
    let url_map = if s3_keys.is_empty() {
        HashMap::new()
    } else {
        state.storage.generate_presigned_urls_batch(&s3_keys)
    };
    let presign = |key: &str| url_map.get(key).cloned().unwrap_or_else(|| key.to_string());
    for msg in &mut history {
        msg.media_urls = msg.media_urls.iter().map(|u| presign(u)).collect();
        msg.audio_url = msg.audio_url.as_ref().map(|u| presign(u));
    }

    // Enhance system instructions with memories
    let memories: HashMap<String, String> = conv
        .metadata
        .get("memories")
        .and_then(|m| serde_json::from_value(m.clone()).ok())
        .unwrap_or_default();

    let mut enhanced_instructions = influencer.system_instructions.clone();
    if !memories.is_empty() {
        enhanced_instructions.push_str("\n\n**MEMORIES:**\n");
        for (key, value) in &memories {
            enhanced_instructions.push_str(&format!("- {key}: {value}\n"));
        }
    }

    // Presign current media URLs for AI
    let media_urls_for_ai: Option<Vec<String>> =
        if matches!(message_type, MessageType::Image | MessageType::Multimodal) {
            body.media_urls.as_ref().map(|urls| {
                let batch = state.storage.generate_presigned_urls_batch(urls);
                urls.iter()
                    .map(|u| batch.get(u).cloned().unwrap_or_else(|| u.clone()))
                    .collect()
            })
        } else {
            None
        };

    // Select AI client and generate response
    let ai_input = transcribed_content
        .as_deref()
        .or(body.content.as_deref())
        .unwrap_or("What do you think?");

    // Broadcast typing indicator: START
    state.ws_manager.broadcast_typing_status(
        &user.user_id,
        &conversation_id,
        &conv.influencer_id,
        true,
    );

    // AI generation with fallback error handling
    let ai_result = if influencer.is_nsfw && state.openrouter.is_configured() {
        state
            .openrouter
            .generate_response(
                ai_input,
                &enhanced_instructions,
                &history,
                media_urls_for_ai.as_deref(),
            )
            .await
    } else {
        state
            .gemini
            .generate_response(
                ai_input,
                &enhanced_instructions,
                &history,
                media_urls_for_ai.as_deref(),
            )
            .await
    };

    // Broadcast typing indicator: STOP
    state.ws_manager.broadcast_typing_status(
        &user.user_id,
        &conversation_id,
        &conv.influencer_id,
        false,
    );

    let (response_text, token_count, is_fallback) = match ai_result {
        Ok((text, tokens)) => (text, tokens, false),
        Err(e) => {
            tracing::error!(error = %e, "AI generation failed, using fallback");
            (FALLBACK_ERROR_MESSAGE.to_string(), 0, true)
        }
    };

    // Save assistant message
    let assistant_message = msg_repo
        .create(
            &conversation_id,
            &MessageRole::Assistant,
            Some(&response_text),
            &MessageType::Text,
            &[],
            None,
            None,
            Some(token_count),
            None,
        )
        .await?;

    // Background tasks: memory extraction + notifications
    spawn_memory_extraction(
        &state,
        &conversation_id,
        ai_input,
        &response_text,
        &memories,
        influencer.is_nsfw,
    );
    spawn_notifications(
        &state,
        &user.user_id,
        &conversation_id,
        &conv.influencer_id,
        &influencer,
        &response_text,
        &assistant_message,
    );

    let status = if is_fallback {
        StatusCode::SERVICE_UNAVAILABLE
    } else {
        StatusCode::OK
    };

    // Presign media URLs in response messages so clients get usable URLs
    let mut user_resp = MessageResponse::from(user_message);
    let mut asst_resp = MessageResponse::from(assistant_message);
    presign_message_urls(&state.storage, &mut user_resp);
    presign_message_urls(&state.storage, &mut asst_resp);

    Ok((
        status,
        Json(SendMessageResponse {
            user_message: user_resp,
            assistant_message: asst_resp,
        }),
    ))
}

// POST /api/v1/chat/conversations/:conversation_id/read
pub async fn mark_as_read(
    State(state): State<Arc<AppState>>,
    user: AuthenticatedUser,
    Path(conversation_id): Path<String>,
) -> Result<Json<MarkConversationAsReadResponse>, AppError> {
    let conv_repo = ConversationRepository::new(state.db.pool.clone());
    let msg_repo = MessageRepository::new(state.db.pool.clone());

    let conv = conv_repo
        .get_by_id(&conversation_id)
        .await?
        .ok_or_else(|| AppError::not_found("Conversation not found"))?;

    if conv.user_id != user.user_id {
        return Err(AppError::forbidden("Not your conversation"));
    }

    msg_repo.mark_as_read(&conversation_id).await?;
    let unread_count = msg_repo.count_unread(&conversation_id).await?;
    let now = chrono::Utc::now().naive_utc();

    // WebSocket broadcast
    state.ws_manager.broadcast_conversation_read(
        &user.user_id,
        &conversation_id,
        &now.format("%Y-%m-%d %H:%M:%S").to_string(),
    );

    Ok(Json(MarkConversationAsReadResponse {
        id: conversation_id,
        unread_count,
        last_read_at: now,
    }))
}

// POST /api/v1/chat/conversations/:conversation_id/images
pub async fn generate_image(
    State(state): State<Arc<AppState>>,
    user: AuthenticatedUser,
    Path(conversation_id): Path<String>,
    Json(body): Json<GenerateImageRequest>,
) -> Result<(StatusCode, Json<MessageResponse>), AppError> {
    if !state.replicate.is_configured() {
        return Err(AppError::service_unavailable(
            "Image generation service not available",
        ));
    }

    let conv_repo = ConversationRepository::new(state.db.pool.clone());
    let inf_repo = InfluencerRepository::new(state.db.pool.clone());
    let msg_repo = MessageRepository::new(state.db.pool.clone());

    let conv = conv_repo
        .get_by_id(&conversation_id)
        .await?
        .ok_or_else(|| AppError::not_found("Conversation not found"))?;

    if conv.user_id != user.user_id {
        return Err(AppError::forbidden("Not your conversation"));
    }

    let influencer = inf_repo
        .get_by_id(&conv.influencer_id)
        .await?
        .ok_or_else(|| AppError::not_found("Influencer not found"))?;

    // Check if bot is discontinued
    if influencer.is_active == InfluencerStatus::Discontinued {
        return Err(AppError::forbidden(
            "This bot has been deleted and can no longer generate images.",
        ));
    }

    // 1. Determine prompt
    let final_prompt = match body.prompt.as_deref().map(str::trim) {
        Some(p) if !p.is_empty() => p.to_string(),
        _ => generate_image_prompt_from_context(&state, &msg_repo, &conversation_id).await?,
    };

    tracing::info!(prompt = %final_prompt, "Generating image");

    // 2. Generate image using flux-kontext-dev with influencer avatar
    let input_image = influencer
        .avatar_url
        .as_deref()
        .filter(|u| !u.is_empty())
        .map(|url| {
            if url.starts_with("http") {
                url.to_string()
            } else {
                state.storage.generate_presigned_url(url)
            }
        });

    let image_url = match &input_image {
        Some(img) => {
            state
                .replicate
                .generate_image_via_image(&final_prompt, img, "9:16")
                .await?
        }
        None => {
            state
                .replicate
                .generate_image(&final_prompt, "9:16")
                .await?
        }
    };

    let image_url = image_url.ok_or_else(|| {
        AppError::service_unavailable("Failed to generate image from upstream provider")
    })?;

    // 3. Download generated image and re-upload to S3
    let (image_bytes, content_type) = state.storage.download_file(&image_url).await?;

    let (s3_key, _size) = state
        .storage
        .upload(&user.user_id, image_bytes, ".jpg", &content_type)
        .await?;

    // 4. Save as assistant message of type IMAGE
    let message = msg_repo
        .create(
            &conversation_id,
            &MessageRole::Assistant,
            Some(""),
            &MessageType::Image,
            &[s3_key],
            None,
            None,
            Some(0),
            None,
        )
        .await?;

    Ok((StatusCode::CREATED, Json(MessageResponse::from(message))))
}

/// Generate an image prompt from recent conversation context using Gemini.
async fn generate_image_prompt_from_context(
    state: &Arc<AppState>,
    msg_repo: &MessageRepository,
    conversation_id: &str,
) -> Result<String, AppError> {
    let mut messages = msg_repo
        .list_by_conversation(conversation_id, 10, 0, "desc")
        .await?;
    messages.reverse();

    let context_str: String = messages
        .iter()
        .filter_map(|m| {
            m.content
                .as_ref()
                .map(|c| format!("{}: {c}", m.role.as_ref()))
        })
        .collect::<Vec<_>>()
        .join("\n");

    let (prompt, _) = state
        .gemini
        .generate_response(
            &format!("Conversation Context:\n{context_str}\n\nGenerate an image prompt:"),
            "You are an AI assistant helping to visualize a scene. Based on the recent conversation, generate a detailed image generation prompt that captures the current context, action, or requested visual. Output ONLY the prompt, no other text.",
            &[],
            None,
        )
        .await?;

    Ok(prompt.trim().to_string())
}

// DELETE /api/v1/chat/conversations/:conversation_id
pub async fn delete_conversation(
    State(state): State<Arc<AppState>>,
    user: AuthenticatedUser,
    Path(conversation_id): Path<String>,
) -> Result<Json<DeleteConversationResponse>, AppError> {
    let conv_repo = ConversationRepository::new(state.db.pool.clone());
    let msg_repo = MessageRepository::new(state.db.pool.clone());

    let conv = conv_repo
        .get_by_id(&conversation_id)
        .await?
        .ok_or_else(|| AppError::not_found("Conversation not found"))?;

    if conv.user_id != user.user_id {
        return Err(AppError::forbidden("Not your conversation"));
    }

    let deleted_messages = msg_repo.delete_by_conversation(&conversation_id).await?;
    conv_repo.delete(&conversation_id).await?;

    Ok(Json(DeleteConversationResponse {
        success: true,
        message: "Conversation deleted successfully".to_string(),
        deleted_conversation_id: conversation_id,
        deleted_messages_count: deleted_messages,
    }))
}

// ── Helpers ──

/// Presign S3 storage keys in a MessageResponse so clients receive usable URLs.
fn presign_message_urls(
    storage: &crate::services::storage::StorageService,
    msg: &mut MessageResponse,
) {
    let s3_keys: Vec<String> = msg
        .media_urls
        .iter()
        .chain(msg.audio_url.iter())
        .filter(|u| !u.starts_with("http"))
        .cloned()
        .collect();

    if s3_keys.is_empty() {
        return;
    }

    let url_map = storage.generate_presigned_urls_batch(&s3_keys);
    let presign = |key: &str| url_map.get(key).cloned().unwrap_or_else(|| key.to_string());

    msg.media_urls = msg.media_urls.iter().map(|u| presign(u)).collect();
    msg.audio_url = msg.audio_url.as_ref().map(|u| presign(u));
}

// ── Background task helpers ──

fn spawn_memory_extraction(
    state: &Arc<AppState>,
    conversation_id: &str,
    user_input: &str,
    response_text: &str,
    memories: &HashMap<String, String>,
    is_nsfw: bool,
) {
    let pool = state.db.pool.clone();
    let conv_id = conversation_id.to_string();
    let ai_input = user_input.to_string();
    let response = response_text.to_string();
    let memories = memories.clone();
    let gemini = state.gemini.clone();
    let openrouter = state.openrouter.clone();

    tokio::spawn(async move {
        let result = if is_nsfw && openrouter.is_configured() {
            openrouter
                .extract_memories(&ai_input, &response, &memories)
                .await
        } else {
            gemini
                .extract_memories(&ai_input, &response, &memories)
                .await
        };

        match result {
            Ok(updated) if updated != memories => {
                let conv_repo = ConversationRepository::new(pool);
                let mut metadata = serde_json::json!({});
                metadata["memories"] = serde_json::to_value(&updated).unwrap_or_default();
                if let Err(e) = conv_repo.update_metadata(&conv_id, &metadata).await {
                    tracing::error!(error = %e, "Failed to update conversation memories");
                }
            }
            Err(e) => tracing::error!(error = %e, "Memory extraction failed"),
            _ => {}
        }
    });
}

fn spawn_notifications(
    state: &Arc<AppState>,
    user_id: &str,
    conversation_id: &str,
    influencer_id: &str,
    influencer: &AIInfluencer,
    response_text: &str,
    assistant_message: &Message,
) {
    let push = state.push_notifications.clone();
    let ws = state.ws_manager.clone();
    let pool = state.db.pool.clone();
    let user_id = user_id.to_string();
    let conv_id = conversation_id.to_string();
    let influencer_id = influencer_id.to_string();
    let influencer_name = influencer.display_name.clone();
    let influencer_avatar = influencer.avatar_url.clone();
    let msg_content = response_text.to_string();
    let msg_json =
        serde_json::to_value(MessageResponse::from(assistant_message.clone())).unwrap_or_default();

    tokio::spawn(async move {
        let unread_count = MessageRepository::new(pool)
            .count_unread(&conv_id)
            .await
            .unwrap_or(0);

        let influencer_json = serde_json::json!({
            "id": influencer_id,
            "display_name": influencer_name,
            "avatar_url": influencer_avatar,
            "is_online": true,
        });
        ws.broadcast_new_message(
            &user_id,
            &conv_id,
            &msg_json,
            &influencer_json,
            unread_count,
        );

        let truncated = if msg_content.len() > 100 {
            format!("{}...", &msg_content[..100])
        } else {
            msg_content
        };
        let data = serde_json::json!({
            "conversation_id": conv_id,
            "influencer_id": influencer_id,
            "type": "new_message",
        });
        push.send_push_notification(&user_id, &influencer_name, &truncated, Some(&data))
            .await;
    });
}
