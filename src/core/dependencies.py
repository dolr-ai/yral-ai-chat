"""
Central dependency injection for FastAPI
"""
from typing import Annotated

from fastapi import Depends

from src.db.repositories.conversation_repository import ConversationRepository
from src.db.repositories.influencer_repository import InfluencerRepository
from src.db.repositories.message_repository import MessageRepository
from src.services.ai_provider_health import AIProviderHealthService
from src.services.chat_service import ChatService
from src.services.gemini_client import GeminiClient
from src.services.openrouter_client import OpenRouterClient
from src.services.influencer_service import InfluencerService
from src.services.storage_service import StorageService


def get_conversation_repository() -> ConversationRepository:
    """Get conversation repository instance"""
    return ConversationRepository()


def get_influencer_repository() -> InfluencerRepository:
    """Get influencer repository instance"""
    return InfluencerRepository()


def get_message_repository() -> MessageRepository:
    """Get message repository instance"""
    return MessageRepository()


def get_gemini_client() -> GeminiClient:
    """Get Gemini client instance"""
    return GeminiClient()


def get_openrouter_client() -> OpenRouterClient:
    """Get OpenRouter client instance (for NSFW content)"""
    return OpenRouterClient()


def get_storage_service() -> StorageService:
    """Get storage service instance"""
    return StorageService()


def get_chat_service(
    influencer_repo: Annotated[InfluencerRepository, Depends(get_influencer_repository)],
    conversation_repo: Annotated[ConversationRepository, Depends(get_conversation_repository)],
    message_repo: Annotated[MessageRepository, Depends(get_message_repository)],
    storage_service: Annotated[StorageService, Depends(get_storage_service)],
    gemini_client: Annotated[GeminiClient, Depends(get_gemini_client)],
    openrouter_client: Annotated[OpenRouterClient, Depends(get_openrouter_client)],
) -> ChatService:
    """Get chat service instance with injected dependencies"""
    return ChatService(
        gemini_client=gemini_client,
        openrouter_client=openrouter_client,
        influencer_repo=influencer_repo,
        conversation_repo=conversation_repo,
        message_repo=message_repo,
        storage_service=storage_service,
    )


def get_influencer_service(
    influencer_repo: Annotated[InfluencerRepository, Depends(get_influencer_repository)]
) -> InfluencerService:
    """Get influencer service instance with injected dependencies"""
    return InfluencerService(influencer_repo=influencer_repo)


def get_ai_provider_health_service(
    gemini_client: Annotated[GeminiClient, Depends(get_gemini_client)],
    openrouter_client: Annotated[OpenRouterClient, Depends(get_openrouter_client)],
) -> AIProviderHealthService:
    """Get AI provider health service instance"""
    return AIProviderHealthService(
        gemini_client=gemini_client,
        openrouter_client=openrouter_client
    )


ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
InfluencerServiceDep = Annotated[InfluencerService, Depends(get_influencer_service)]
AIProviderHealthServiceDep = Annotated[AIProviderHealthService, Depends(get_ai_provider_health_service)]
StorageServiceDep = Annotated[StorageService, Depends(get_storage_service)]
GeminiClientDep = Annotated[GeminiClient, Depends(get_gemini_client)]
OpenRouterClientDep = Annotated[OpenRouterClient, Depends(get_openrouter_client)]
ConversationRepositoryDep = Annotated[ConversationRepository, Depends(get_conversation_repository)]
InfluencerRepositoryDep = Annotated[InfluencerRepository, Depends(get_influencer_repository)]
MessageRepositoryDep = Annotated[MessageRepository, Depends(get_message_repository)]
