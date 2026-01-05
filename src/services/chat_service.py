"""
Chat service - Business logic for conversations and messages
"""
from uuid import UUID

from loguru import logger

from src.core.exceptions import ForbiddenException, NotFoundException
from src.db.repositories import ConversationRepository, InfluencerRepository, MessageRepository
from src.models.entities import Conversation, Message, MessageRole, MessageType
from src.services.gemini_client import GeminiClient
from src.services.storage_service import StorageService


class ChatService:
    """Service for chat operations"""

    def __init__(
        self,
        gemini_client: GeminiClient,
        influencer_repo: InfluencerRepository,
        conversation_repo: ConversationRepository,
        message_repo: MessageRepository,
        storage_service: StorageService | None = None,
    ):
        self.influencer_repo = influencer_repo
        self.conversation_repo = conversation_repo
        self.message_repo = message_repo
        self.storage_service = storage_service
        self.gemini_client = gemini_client

    async def create_conversation(
        self,
        user_id: str,
        influencer_id: UUID
    ) -> tuple[Conversation, bool]:
        """Create a new conversation or return existing one"""
        influencer = await self.influencer_repo.get_by_id(influencer_id)
        if not influencer:
            raise NotFoundException("Influencer not found")

        existing = await self.conversation_repo.get_existing(user_id, influencer_id)
        if existing:
            logger.info(f"Returning existing conversation: {existing.id}")
            existing.influencer = influencer
            return existing, False

        conversation = await self.conversation_repo.create(user_id, influencer_id)
        logger.info(f"Created new conversation: {conversation.id}")

        if influencer.initial_greeting:
            logger.info(f"Creating initial greeting for conversation {conversation.id}")
            try:
                greeting_msg = await self.message_repo.create(
                    conversation_id=conversation.id,
                    role=MessageRole.ASSISTANT,
                    content=influencer.initial_greeting,
                    message_type=MessageType.TEXT
                )
                logger.info(f"Created initial greeting message {greeting_msg.id} for conversation {conversation.id}")
            except Exception as e:
                logger.error(
                    f"Failed to create initial greeting message for conversation {conversation.id}: {e}",
                    exc_info=True
                )
        else:
            logger.info(f"No initial_greeting configured for influencer {influencer.id} ({influencer.display_name})")

        conversation.influencer = influencer
        return conversation, True

    async def _transcribe_audio(self, audio_url: str) -> str:
        """Transcribe audio and return transcribed content"""
        try:
            audio_url_for_transcription = audio_url
            if self.storage_service:
                s3_key = self.storage_service.extract_key_from_url(audio_url)
                audio_url_for_transcription = self.storage_service.generate_presigned_url(s3_key)
            
            transcription = await self.gemini_client.transcribe_audio(audio_url_for_transcription)
            transcribed_content = f"[Transcribed: {transcription}]"
            logger.info(f"Audio transcribed: {transcription[:100]}...")
            return transcribed_content
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return "[Audio message - transcription failed]"

    def _convert_storage_key_to_url(self, storage_key: str) -> str | None:
        """Convert a storage key to presigned URL, or return None if conversion fails"""
        if not self.storage_service:
            return None
        try:
            s3_key = self.storage_service.extract_key_from_url(storage_key)
            return self.storage_service.generate_presigned_url(s3_key)
        except Exception as e:
            logger.warning(f"Failed to convert storage key {storage_key} to presigned URL: {e}")
            if storage_key.startswith(("http://", "https://")):
                return storage_key
            return None

    def _convert_history_storage_keys(self, history: list[Message]) -> None:
        """Convert storage keys to presigned URLs in message history"""
        if not self.storage_service:
            return
        
        for msg in history:
            if msg.media_urls and msg.message_type in [MessageType.IMAGE, MessageType.MULTIMODAL]:
                converted_urls = []
                for media_key in msg.media_urls:
                    if media_key:
                        url = self._convert_storage_key_to_url(media_key)
                        if url:
                            converted_urls.append(url)
                msg.media_urls = converted_urls
            
            if msg.audio_url and msg.message_type == MessageType.AUDIO:
                url = self._convert_storage_key_to_url(msg.audio_url)
                if url:
                    msg.audio_url = url
                elif not msg.audio_url.startswith(("http://", "https://")):
                    msg.audio_url = None

    def _convert_media_urls_for_ai(self, media_urls: list[str] | None) -> list[str] | None:
        """Convert storage keys to presigned URLs for AI processing"""
        if not media_urls:
            return None
        
        if not self.storage_service:
            return media_urls
        
        converted_urls = []
        for media_key in media_urls:
            if media_key:
                url = self._convert_storage_key_to_url(media_key)
                if url:
                    converted_urls.append(url)
                else:
                    logger.error(f"Cannot use storage key as URL: {media_key}")
        return converted_urls if converted_urls else None

    async def _update_conversation_memories(
        self,
        conversation_id: UUID,
        conversation: Conversation,
        user_message: str,
        assistant_response: str,
        memories: dict[str, object]
    ) -> None:
        """Extract and update memories from conversation"""
        try:
            updated_memories = await self.gemini_client.extract_memories(
                user_message=user_message,
                assistant_response=assistant_response,
                existing_memories=memories.copy()
            )
            
            if updated_memories != memories:
                conversation.metadata["memories"] = updated_memories
                await self.conversation_repo.update_metadata(conversation_id, conversation.metadata)
                logger.info(f"Updated memories: {len(updated_memories)} total memories")
        except Exception as e:
            logger.error(f"Failed to update memories: {e}", exc_info=True)

    async def send_message(
        self,
        conversation_id: UUID,
        user_id: str,
        content: str | None,
        message_type: MessageType,
        media_urls: list[str] = None,
        audio_url: str | None = None,
        audio_duration_seconds: int | None = None
    ) -> tuple[Message, Message]:
        """
        Send a message and get AI response
        
        Args:
            conversation_id: Conversation ID
            user_id: User ID
            content: Message text content
            message_type: Type of message
            media_urls: Optional image URLs
            audio_url: Optional audio URL
            audio_duration_seconds: Optional audio duration
            
        Returns:
            Tuple of (user_message, assistant_message)
        """
        conversation = await self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            raise NotFoundException("Conversation not found")

        if conversation.user_id != user_id:
            raise ForbiddenException("Not your conversation")

        influencer = await self.influencer_repo.get_by_id(conversation.influencer_id)
        if not influencer:
            raise NotFoundException("Influencer not found")

        memories = conversation.metadata.get("memories", {})

        transcribed_content = content
        if message_type == MessageType.AUDIO and audio_url:
            transcribed_content = await self._transcribe_audio(audio_url)

        user_message = await self.message_repo.create(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=transcribed_content or "",
            message_type=message_type,
            media_urls=media_urls or [],
            audio_url=audio_url,
            audio_duration_seconds=audio_duration_seconds
        )

        logger.info(f"User message saved: {user_message.id}")

        all_recent = await self.message_repo.get_recent_for_context(
            conversation_id=conversation_id,
            limit=11
        )
        history = [msg for msg in all_recent if msg.id != user_message.id][:10]

        self._convert_history_storage_keys(history)

        ai_input_content = str(content or transcribed_content or "What do you think?")

        enhanced_system_instructions = influencer.system_instructions
        if memories:
            memories_text = "\n\n**MEMORIES:**\n" + "\n".join(
                f"- {key}: {value}" for key, value in memories.items()
            )
            enhanced_system_instructions = influencer.system_instructions + memories_text

        media_urls_for_ai = None
        if message_type in [MessageType.IMAGE, MessageType.MULTIMODAL] and media_urls:
            media_urls_for_ai = self._convert_media_urls_for_ai(media_urls)

        try:
            response_text, token_count = await self.gemini_client.generate_response(
                user_message=ai_input_content,
                system_instructions=enhanced_system_instructions,
                conversation_history=history,
                media_urls=media_urls_for_ai
            )
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            response_text = "I'm having trouble generating a response right now. Please try again."
            token_count = 0

        assistant_message = await self.message_repo.create(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=response_text,
            message_type=MessageType.TEXT,
            token_count=token_count
        )

        logger.info(f"Assistant message saved: {assistant_message.id}")

        await self._update_conversation_memories(
            conversation_id,
            conversation,
            ai_input_content,
            response_text,
            memories
        )

        return user_message, assistant_message

    async def get_conversation(
        self,
        conversation_id: UUID,
        user_id: str
    ) -> Conversation:
        """Get conversation by ID and verify ownership"""
        conversation = await self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            raise NotFoundException("Conversation not found")

        if conversation.user_id != user_id:
            raise ForbiddenException("Not your conversation")

        return conversation

    async def list_conversations(
        self,
        user_id: str,
        influencer_id: UUID | None = None,
        limit: int = 20,
        offset: int = 0
    ) -> tuple[list[Conversation], int]:
        """List user's conversations"""
        conversations = await self.conversation_repo.list_by_user(
            user_id=user_id,
            influencer_id=influencer_id,
            limit=limit,
            offset=offset
        )

        total = await self.conversation_repo.count_by_user(
            user_id=user_id,
            influencer_id=influencer_id
        )

        return conversations, total

    async def list_messages(
        self,
        conversation_id: UUID,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        order: str = "desc"
    ) -> tuple[list[Message], int]:
        """List messages in a conversation"""
        await self.get_conversation(conversation_id, user_id)

        messages = await self.message_repo.list_by_conversation(
            conversation_id=conversation_id,
            limit=limit,
            offset=offset,
            order=order
        )

        total = await self.message_repo.count_by_conversation(conversation_id)

        return messages, total

    async def delete_conversation(
        self,
        conversation_id: UUID,
        user_id: str
    ) -> int:
        """Delete a conversation"""
        await self.get_conversation(conversation_id, user_id)

        deleted_messages = await self.conversation_repo.delete(conversation_id)

        logger.info(f"Deleted conversation {conversation_id} with {deleted_messages} messages")

        return deleted_messages

