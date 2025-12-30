"""
Chat service - Business logic for conversations and messages
"""
from uuid import UUID

from loguru import logger

from src.core.exceptions import ForbiddenException, NotFoundException
from src.db.repositories import ConversationRepository, InfluencerRepository, MessageRepository
from src.models.entities import Conversation, Message, MessageRole, MessageType
from src.services.gemini_client import gemini_client
from src.services.storage_service import StorageService


class ChatService:
    """Service for chat operations"""

    def __init__(self, storage_service: StorageService | None = None):
        self.influencer_repo = InfluencerRepository()
        self.conversation_repo = ConversationRepository()
        self.message_repo = MessageRepository()
        self.storage_service = storage_service

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
        greeting_created = False
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
                greeting_created = True
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

        # Get existing memories from conversation metadata
        memories = conversation.metadata.get("memories", {})

        # Handle audio transcription
        transcribed_content = content
        if message_type == MessageType.AUDIO and audio_url:
            try:
                # Convert storage key to presigned URL if needed
                audio_url_for_transcription = audio_url
                if self.storage_service:
                    s3_key = self.storage_service.extract_key_from_url(audio_url)
                    audio_url_for_transcription = self.storage_service.generate_presigned_url(s3_key)
                
                transcription = await gemini_client.transcribe_audio(audio_url_for_transcription)
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

        # Convert storage keys to presigned URLs in history for Gemini
        if self.storage_service:
            for msg in history:
                # Convert media_urls from storage keys to presigned URLs
                if msg.media_urls and msg.message_type in [MessageType.IMAGE, MessageType.MULTIMODAL]:
                    converted_urls = []
                    for media_key in msg.media_urls:
                        if media_key:
                            try:
                                s3_key = self.storage_service.extract_key_from_url(media_key)
                                presigned_url = self.storage_service.generate_presigned_url(s3_key)
                                converted_urls.append(presigned_url)
                            except Exception as e:
                                logger.warning(f"Failed to convert history media key {media_key} to presigned URL: {e}")
                                # If it's already a URL, keep it
                                if media_key.startswith(("http://", "https://")):
                                    converted_urls.append(media_key)
                    msg.media_urls = converted_urls
                
                # Convert audio_url from storage key to presigned URL
                if msg.audio_url and msg.message_type == MessageType.AUDIO:
                    try:
                        s3_key = self.storage_service.extract_key_from_url(msg.audio_url)
                        msg.audio_url = self.storage_service.generate_presigned_url(s3_key)
                    except Exception as e:
                        logger.warning(f"Failed to convert history audio key {msg.audio_url} to presigned URL: {e}")
                        # If it's already a URL, keep it
                        if not msg.audio_url.startswith(("http://", "https://")):
                            msg.audio_url = None  # Can't use storage key as URL

        # Prepare content for AI
        ai_input_content = str(content or transcribed_content or "What do you think?")

        # Enhance system instructions with memories
        enhanced_system_instructions = influencer.system_instructions
        if memories:
            memories_text = "\n\n**MEMORIES:**\n" + "\n".join(
                f"- {key}: {value}" for key, value in memories.items()
            )
            enhanced_system_instructions = influencer.system_instructions + memories_text

        # Convert storage keys to presigned URLs for Gemini (if storage service is available)
        media_urls_for_ai = None
        if message_type in [MessageType.IMAGE, MessageType.MULTIMODAL] and media_urls:
            if self.storage_service:
                media_urls_for_ai = []
                for media_key in media_urls:
                    if media_key:
                        try:
                            # Extract key from URL if it's an old public URL (backward compat)
                            s3_key = self.storage_service.extract_key_from_url(media_key)
                            presigned_url = self.storage_service.generate_presigned_url(s3_key)
                            media_urls_for_ai.append(presigned_url)
                        except Exception as e:
                            logger.warning(f"Failed to generate presigned URL for {media_key}: {e}")
                            # Fallback: if it already looks like a URL, use it as-is
                            if media_key.startswith(("http://", "https://")):
                                media_urls_for_ai.append(media_key)
                            else:
                                logger.error(f"Cannot use storage key as URL: {media_key}")
            else:
                # No storage service available, use as-is (might be URLs already)
                media_urls_for_ai = media_urls

        # Generate AI response
        try:
            response_text, token_count = await gemini_client.generate_response(
                user_message=ai_input_content,
                system_instructions=enhanced_system_instructions,
                conversation_history=history,
                media_urls=media_urls_for_ai
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

        # Extract and update memories from this exchange
        try:
            updated_memories = await gemini_client.extract_memories(
                user_message=ai_input_content,
                assistant_response=response_text,
                existing_memories=memories.copy()
            )
            
            # Update conversation metadata with new memories
            if updated_memories != memories:
                conversation.metadata["memories"] = updated_memories
                await self.conversation_repo.update_metadata(conversation_id, conversation.metadata)
                logger.info(f"Updated memories: {len(updated_memories)} total memories")
        except Exception as e:
            logger.error(f"Failed to update memories: {e}", exc_info=True)
            # Don't fail the request if memory extraction fails

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


