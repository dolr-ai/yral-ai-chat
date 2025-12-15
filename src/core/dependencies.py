"""
Central dependency injection for FastAPI
"""
from typing import Annotated

from fastapi import Depends

from src.db.repositories.conversation_repository import ConversationRepository
from src.db.repositories.influencer_repository import InfluencerRepository
from src.db.repositories.message_repository import MessageRepository
from src.services.chat_service import ChatService
from src.services.gemini_client import GeminiClient
from src.services.influencer_service import InfluencerService
from src.services.storage_service import StorageService


# Repository Dependencies
def get_conversation_repository() -> ConversationRepository:
    """Get conversation repository instance"""
    return ConversationRepository()


def get_influencer_repository() -> InfluencerRepository:
    """Get influencer repository instance"""
    return InfluencerRepository()


def get_message_repository() -> MessageRepository:
    """Get message repository instance"""
    return MessageRepository()


# Service Dependencies
def get_gemini_client() -> GeminiClient:
    """Get Gemini client singleton"""
    from src.services.gemini_client import gemini_client
    return gemini_client


def get_storage_service() -> StorageService:
    """Get storage service singleton"""
    from src.services.storage_service import storage_service
    return storage_service


def get_chat_service(
    influencer_repo: Annotated[InfluencerRepository, Depends(get_influencer_repository)],
    conversation_repo: Annotated[ConversationRepository, Depends(get_conversation_repository)],
    message_repo: Annotated[MessageRepository, Depends(get_message_repository)],
) -> ChatService:
    """Get chat service instance with injected dependencies"""
    service = ChatService()
    service.influencer_repo = influencer_repo
    service.conversation_repo = conversation_repo
    service.message_repo = message_repo
    return service


def get_influencer_service(
    influencer_repo: Annotated[InfluencerRepository, Depends(get_influencer_repository)]
) -> InfluencerService:
    """Get influencer service instance with injected dependencies"""
    service = InfluencerService()
    service.influencer_repo = influencer_repo
    return service


# Type aliases for cleaner endpoint signatures
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
InfluencerServiceDep = Annotated[InfluencerService, Depends(get_influencer_service)]
StorageServiceDep = Annotated[StorageService, Depends(get_storage_service)]
GeminiClientDep = Annotated[GeminiClient, Depends(get_gemini_client)]
ConversationRepositoryDep = Annotated[ConversationRepository, Depends(get_conversation_repository)]
InfluencerRepositoryDep = Annotated[InfluencerRepository, Depends(get_influencer_repository)]
MessageRepositoryDep = Annotated[MessageRepository, Depends(get_message_repository)]
