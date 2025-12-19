"""
Chat service - Business logic for conversations and messages
"""
from uuid import UUID

from loguru import logger

from src.core.exceptions import ForbiddenException, NotFoundException
from src.db.repositories import ConversationRepository, InfluencerRepository, MessageRepository
from src.models.entities import Conversation, Message, MessageRole, MessageType
from src.services.gemini_client import gemini_client


class ChatService:
    """Service for chat operations"""

    def __init__(self):
        self.influencer_repo = InfluencerRepository()
        self.conversation_repo = ConversationRepository()
        self.message_repo = MessageRepository()

    async def create_conversation(
        self,
        user_id: str,
        influencer_id: UUID
    ) -> tuple[Conversation, bool]:
        """
        Create a new conversation or return existing one
        
        Args:
            user_id: User ID
            influencer_id: AI Influencer ID
            
        Returns:
            Tuple of (Conversation object, is_new_conversation: bool)
        """
        # Verify influencer exists
        influencer = await self.influencer_repo.get_by_id(influencer_id)
        if not influencer:
            raise NotFoundException("Influencer not found")

        # Check if conversation already exists
        existing = await self.conversation_repo.get_existing(user_id, influencer_id)
        if existing:
            logger.info(f"Returning existing conversation: {existing.id}")
            existing.influencer = influencer
            return existing, False

        # Create new conversation
        conversation = await self.conversation_repo.create(user_id, influencer_id)
        logger.info(f"Created new conversation: {conversation.id}")

        # Create initial greeting message if configured
        if influencer.initial_greeting:
            logger.info(
                f"Creating initial greeting for conversation {conversation.id}. "
                f"Greeting content length: {len(influencer.initial_greeting)}"
            )
            try:
                greeting_msg = await self.message_repo.create(
                    conversation_id=conversation.id,
                    role=MessageRole.ASSISTANT,
                    content=influencer.initial_greeting,
                    message_type=MessageType.TEXT
                )
                logger.info(
                    f"✅ Created initial greeting message for conversation: {conversation.id}. "
                    f"Message ID: {greeting_msg.id}, Content preview: {greeting_msg.content[:50]}..."
                )
            except Exception as e:
                logger.error(
                    f"❌ Failed to create initial greeting message for conversation {conversation.id}: {e}",
                    exc_info=True
                )
                # Continue even if greeting creation fails
        else:
            logger.info(
                f"No initial_greeting configured for influencer {influencer.id} "
                f"({influencer.display_name}). initial_greeting value: {influencer.initial_greeting}"
            )

        # Attach influencer info
        conversation.influencer = influencer

        return conversation, True  # Return True to indicate this is a new conversation

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
        # Get conversation and verify ownership
        conversation = await self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            raise NotFoundException("Conversation not found")

        if conversation.user_id != user_id:
            raise ForbiddenException("Not your conversation")

        # Get influencer for system instructions
        influencer = await self.influencer_repo.get_by_id(conversation.influencer_id)
        if not influencer:
            raise NotFoundException("Influencer not found")

        # Handle audio transcription
        transcribed_content = content
        if message_type == MessageType.AUDIO and audio_url:
            try:
                transcription = await gemini_client.transcribe_audio(audio_url)
                transcribed_content = f"[Transcribed: {transcription}]"
                logger.info(f"Audio transcribed: {transcription[:100]}...")
            except Exception as e:
                logger.error(f"Transcription failed: {e}")
                transcribed_content = "[Audio message - transcription failed]"

        # Save user message
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

        # Get conversation history for context
        history = await self.message_repo.get_recent_for_context(
            conversation_id=conversation_id,
            limit=10
        )

        # Prepare content for AI
        ai_input_content = content or transcribed_content or "What do you think?"

        # Generate AI response
        try:
            response_text, token_count = await gemini_client.generate_response(
                user_message=ai_input_content,
                system_instructions=influencer.system_instructions,
                conversation_history=history,
                media_urls=media_urls if message_type in [MessageType.IMAGE, MessageType.MULTIMODAL] else None
            )
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            # Save a fallback message
            response_text = "I'm having trouble generating a response right now. Please try again."
            token_count = 0

        # Save assistant message
        assistant_message = await self.message_repo.create(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=response_text,
            message_type=MessageType.TEXT,
            token_count=token_count
        )

        logger.info(f"Assistant message saved: {assistant_message.id}")

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
        # Verify ownership
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
        # Verify ownership
        await self.get_conversation(conversation_id, user_id)

        # Delete conversation (messages cascade)
        deleted_messages = await self.conversation_repo.delete(conversation_id)

        logger.info(f"Deleted conversation {conversation_id} with {deleted_messages} messages")

        return deleted_messages


# Global chat service instance
chat_service = ChatService()


