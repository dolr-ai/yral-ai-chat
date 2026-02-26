use utoipa::OpenApi;
use utoipa_swagger_ui::SwaggerUi;

#[derive(OpenApi)]
#[openapi(
    info(
        title = "Yral AI Chat API",
        version = "1.0.0",
        description = "AI Chat API for Yral"
    ),
    paths(
        // Health
        super::health::root,
        super::health::health,
        super::health::status,
        // Influencers
        super::influencers::list_influencers,
        super::influencers::list_trending,
        super::influencers::get_influencer,
        super::influencers::generate_prompt,
        super::influencers::validate_and_generate_metadata,
        super::influencers::create_influencer,
        super::influencers::update_system_prompt,
        super::influencers::delete_influencer,
        // Chat V1
        super::chat::create_conversation,
        super::chat::list_conversations,
        super::chat::list_messages,
        super::chat::send_message,
        super::chat::mark_as_read,
        super::chat::generate_image,
        super::chat::delete_conversation,
        // Chat V2
        super::chat_v2::list_conversations_v2,
        // Media
        super::media::upload_media,
        // WebSocket
        super::websocket::ws_inbox,
        super::websocket::ws_docs,
    ),
    components(schemas(
        // Requests
        crate::models::requests::CreateConversationRequest,
        crate::models::requests::SendMessageRequest,
        crate::models::requests::GeneratePromptRequest,
        crate::models::requests::ValidateMetadataRequest,
        crate::models::requests::CreateInfluencerRequest,
        crate::models::requests::GenerateImageRequest,
        crate::models::requests::UpdateSystemPromptRequest,
        crate::models::requests::UploadMediaBody,
        // Responses
        crate::models::responses::InfluencerBasicInfo,
        crate::models::responses::InfluencerBasicInfoV2,
        crate::models::responses::MessageResponse,
        crate::models::responses::ConversationResponse,
        crate::models::responses::ConversationResponseV2,
        crate::models::responses::SendMessageResponse,
        crate::models::responses::ListConversationsResponse,
        crate::models::responses::ListConversationsResponseV2,
        crate::models::responses::ListMessagesResponse,
        crate::models::responses::InfluencerResponse,
        crate::models::responses::ListInfluencersResponse,
        crate::models::responses::TrendingInfluencerResponse,
        crate::models::responses::ListTrendingInfluencersResponse,
        crate::models::responses::SystemPromptResponse,
        crate::models::responses::GeneratedMetadataResponse,
        crate::models::responses::MarkConversationAsReadResponse,
        crate::models::responses::ServiceHealth,
        crate::models::responses::HealthResponse,
        crate::models::responses::StatusResponse,
        crate::models::responses::DatabaseStats,
        crate::models::responses::SystemStatistics,
        crate::models::responses::MediaUploadResponse,
        crate::models::responses::DeleteConversationResponse,
        // WebSocket event schemas
        crate::models::responses::NewMessageEvent,
        crate::models::responses::NewMessageEventData,
        crate::models::responses::ConversationReadEvent,
        crate::models::responses::ConversationReadEventData,
        crate::models::responses::TypingStatusEvent,
        crate::models::responses::TypingStatusEventData,
        crate::models::responses::WsDocsResponse,
        // Entities (enums + shared types)
        crate::models::entities::MessageType,
        crate::models::entities::MessageRole,
        crate::models::entities::InfluencerStatus,
        crate::models::entities::LastMessageInfo,
        // Error
        crate::error::ErrorBody,
    )),
    modifiers(&SecurityAddon),
    tags(
        (name = "Health", description = "Health and status endpoints"),
        (name = "Influencers", description = "AI influencer management"),
        (name = "Chat", description = "Chat conversations and messages (V1)"),
        (name = "Chat V2", description = "Chat conversations (V2)"),
        (name = "Media", description = "Media upload"),
        (name = "WebSocket", description = "Real-time WebSocket endpoints"),
    )
)]
pub struct ApiDoc;

struct SecurityAddon;

impl utoipa::Modify for SecurityAddon {
    fn modify(&self, openapi: &mut utoipa::openapi::OpenApi) {
        if let Some(components) = openapi.components.as_mut() {
            components.add_security_scheme(
                "BearerAuth",
                utoipa::openapi::security::SecurityScheme::Http(
                    utoipa::openapi::security::Http::new(
                        utoipa::openapi::security::HttpAuthScheme::Bearer,
                    ),
                ),
            );
        }
    }
}

pub fn swagger_ui() -> SwaggerUi {
    SwaggerUi::new("/explore").url("/api-docs/openapi.json", ApiDoc::openapi())
}
