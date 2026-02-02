"""
Chat service - Business logic for conversations and messages
"""
import sqlite3
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from fastapi import BackgroundTasks

from loguru import logger

from src.core.background_tasks import (
    invalidate_cache_for_user,
    log_ai_usage,
    update_conversation_stats,
)
from src.core.cache import cache
from src.core.exceptions import ForbiddenException, NotFoundException
from src.db.repositories import ConversationRepository, InfluencerRepository, MessageRepository
from src.models.entities import Conversation, Message, MessageRole, MessageType
from src.services.gemini_client import GeminiClient
from src.services.openrouter_client import OpenRouterClient
from src.services.storage_service import StorageService


class ChatService:
    """Service for chat operations"""

    FALLBACK_ERROR_MESSAGE = "I'm having trouble generating a response right now. Please try again."

    def __init__(
        self,
        gemini_client: GeminiClient,
        influencer_repo: InfluencerRepository,
        conversation_repo: ConversationRepository,
        message_repo: MessageRepository,
        storage_service: StorageService | None = None,
        openrouter_client: OpenRouterClient | None = None,
    ):
        self.influencer_repo = influencer_repo
        self.conversation_repo = conversation_repo
        self.message_repo = message_repo
        self.storage_service = storage_service
        self.gemini_client = gemini_client
        self.openrouter_client = openrouter_client

    def _select_ai_client(self, is_nsfw: bool):
        """Select appropriate AI client based on content type (NSFW or regular)"""
        if is_nsfw and self.openrouter_client:
            logger.info("Using OpenRouter client for NSFW influencer")
            return self.openrouter_client
        logger.info("Using Gemini client for regular influencer")
        return self.gemini_client

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

        try:
            conversation = await self.conversation_repo.create(user_id, influencer_id)
        except sqlite3.IntegrityError:
            logger.warning(
                f"Race condition detected creating conversation for user {user_id} "
                f"and influencer {influencer_id}. Retrying fetch."
            )
            existing = await self.conversation_repo.get_existing(user_id, influencer_id)
            if existing:
                existing.influencer = influencer
                return existing, False
            raise
        logger.info(f"Created new conversation: {conversation.id}")

        if influencer.initial_greeting:
            logger.info(f"Creating initial greeting for conversation {conversation.id}")
            await self._save_message(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=influencer.initial_greeting,
                message_type=MessageType.TEXT
            )
            await self.conversation_repo.touch_updated_at(conversation.id)
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
                audio_url_for_transcription = await self.storage_service.generate_presigned_url(s3_key)
            
            transcription = await self.gemini_client.transcribe_audio(audio_url_for_transcription)
            transcribed_content = f"[Transcribed: {transcription}]"
            logger.info(f"Audio transcribed: {transcription[:100]}...")
            return transcribed_content
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return "[Audio message - transcription failed]"

    async def _persist_message(self, **kwargs) -> None:
        """Background task helper to persist message and log errors"""
        try:
            await self._save_message(**kwargs)
        except Exception as e:
            logger.error(f"Failed to persist message in background: {e}", exc_info=True)

    async def _convert_history_storage_keys_async(self, history: list[Message]) -> None:
        """Convert storage keys to presigned URLs in message history asynchronously"""
        if not self.storage_service or not history:
            return
            
        all_keys = []
        for msg in history:
            if msg.media_urls and msg.message_type in [MessageType.IMAGE, MessageType.MULTIMODAL]:
                for media_key in msg.media_urls:
                    if media_key and not media_key.startswith(("http://", "https://")):
                        all_keys.append(media_key)
            if (
                msg.audio_url
                and msg.message_type == MessageType.AUDIO
                and not msg.audio_url.startswith(("http://", "https://"))
            ):
                all_keys.append(msg.audio_url)
        
        if not all_keys:
            return
            
        url_map = await self.storage_service.generate_presigned_urls_batch(all_keys)
        
        # Apply the map back to the history
        for msg in history:
            if msg.media_urls and msg.message_type in [MessageType.IMAGE, MessageType.MULTIMODAL]:
                msg.media_urls = [url_map.get(k, k) for k in msg.media_urls]
            if msg.audio_url and msg.message_type == MessageType.AUDIO:
                msg.audio_url = url_map.get(msg.audio_url, msg.audio_url)

    async def _convert_media_urls_for_ai_async(self, media_urls: list[str] | None) -> list[str] | None:
        """Convert storage keys to presigned URLs for AI processing asynchronously"""
        if not media_urls or not self.storage_service:
            return media_urls
        
        url_map = await self.storage_service.generate_presigned_urls_batch(media_urls)
        return [url_map.get(k, k) for k in media_urls]

    async def _update_conversation_memories(
        self,
        conversation_id: UUID,
        conversation: Conversation,
        user_message: str,
        assistant_response: str,
        memories: dict[str, object],
        is_nsfw: bool = False
    ) -> None:
        """Extract and update memories from conversation using appropriate client"""
        try:
            ai_client = self._select_ai_client(is_nsfw)
            updated_memories = await ai_client.extract_memories(
                user_message=user_message,
                assistant_response=assistant_response,
                existing_memories=memories.copy()
            )
            if updated_memories != memories:
                conversation.metadata["memories"] = updated_memories
                await self.conversation_repo.update_metadata(conversation_id, conversation.metadata)
                logger.info(f"Updated memories: {len(updated_memories)} total memories")
            else:
                # Still touch updated_at to ensure conversation moves to top
                await self.conversation_repo.touch_updated_at(conversation_id)
        except Exception as e:
            logger.error(f"Failed to update memories: {e}", exc_info=True)

    async def _validate_and_get_context(
        self,
        conversation_id: str,
        user_id: str
    ) -> tuple[Conversation, object]:
        """Validate conversation/user and return conversation and influencer"""
        conversation = await self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            raise NotFoundException("Conversation not found")

        if conversation.user_id != user_id:
            raise ForbiddenException("Not your conversation")

        influencer = await self.influencer_repo.get_by_id(conversation.influencer_id)
        if not influencer:
            raise NotFoundException("Influencer not found")

        return conversation, influencer

    async def _prepare_user_message(
        self,
        conversation_id: str,
        content: str,
        message_type: str,
        audio_url: str | None,
        audio_duration_seconds: int | None,
        media_urls: list[str] | None,
        timings: dict[str, float]
    ) -> tuple[Message, str]:
        """Transcribe (if needed) and prepare user message"""
        transcribed_content = content
        if message_type == MessageType.AUDIO and audio_url:
            t0 = time.time()
            transcribed_content = await self._transcribe_audio(audio_url)
            timings["transcribe_audio"] = time.time() - t0

        return transcribed_content, transcribed_content or ""

    async def _build_ai_context(
        self,
        conversation_id: str,
        user_message_id: str,
        influencer: object,
        memories: dict[str, object],
        timings: dict[str, float]
    ) -> tuple[list[Message], str]:
        """Fetch history and build system instructions"""
        # Try Redis cache first (Write-Through Cache for immediate consistency)
        cache_key = f"conversation:{conversation_id}:messages"
        cached_messages = await cache.lrange(cache_key, 0, 10)
        
        if cached_messages:
            history = [msg for msg in cached_messages if msg.id != user_message_id]
            history.reverse()  # Convert to oldest->newest for AI context
            history = history[:10]
            logger.debug(f"Context cache hit for {conversation_id}: {len(history)} msgs")
        else:
            # Cache miss: fetch from DB and populate cache
            logger.debug(f"Context cache miss for {conversation_id}. Fetching from DB.")
            t0 = time.time()
            all_recent = await self.message_repo.get_recent_for_context(
                conversation_id=conversation_id,
                limit=11
            )
            history = [msg for msg in all_recent if msg.id != user_message_id][:10]
            timings["get_history"] = time.time() - t0
            
            if history:
                await cache.lpush(cache_key, *history)
                await cache.expire(cache_key, 3600)

        t0 = time.time()
        await self._convert_history_storage_keys_async(history)
        timings["convert_history_urls"] = time.time() - t0

        enhanced_system_instructions = influencer.system_instructions
        if memories:
            memories_text = "\n\n**MEMORIES:**\n" + "\n".join(
                f"- {key}: {value}" for key, value in memories.items()
            )
            enhanced_system_instructions = influencer.system_instructions + memories_text
            
        return history, enhanced_system_instructions

    async def _generate_ai_response(
        self,
        influencer: object,
        ai_input_content: str,
        enhanced_instructions: str,
        history: list[Message],
        media_urls_for_ai: list[str] | None,
        timings: dict[str, float]
    ) -> tuple[str, int]:
        """Select client and generate AI response"""
        try:
            ai_client = self._select_ai_client(influencer.is_nsfw)
            provider_name = "OpenRouter" if influencer.is_nsfw else "Gemini"
            logger.info(
                f"Generating response for influencer {influencer.id} ({influencer.display_name}) "
                f"using {provider_name} provider"
            )
            t0 = time.time()
            response_text, token_count = await ai_client.generate_response(
                user_message=ai_input_content,
                system_instructions=enhanced_instructions,
                conversation_history=history,
                media_urls=media_urls_for_ai
            )
            timings["ai_generate_response"] = time.time() - t0
            logger.info(
                f"Response generated successfully from {provider_name}: "
                f"{len(response_text)} chars, {token_count} tokens"
            )
            return response_text, token_count
        except Exception as e:
            timings["ai_generate_response"] = time.time() - t0
            logger.error(
                "AI response generation failed for influencer {}: {}",
                influencer.id,
                str(e),
                exc_info=True
            )
            return self.FALLBACK_ERROR_MESSAGE, 0

    async def send_message(
        self,
        conversation_id: str,
        user_id: str,
        content: str,
        message_type: str = "text",
        media_urls: list[str] | None = None,
        audio_url: str | None = None,
        audio_duration_seconds: int | None = None,
        background_tasks: "BackgroundTasks | None" = None
    ) -> tuple[Message, Message]:
        """Send a message and get AI response"""
        timings: dict[str, float] = {}
        total_start = time.time()

        # 1. Validation & Context
        t0 = time.time()
        conversation, influencer = await self._validate_and_get_context(conversation_id, user_id)
        timings["get_context"] = time.time() - t0
        memories = conversation.metadata.get("memories", {})

        # 2. User Message
        t0 = time.time()
        user_message_id = str(uuid.uuid4())
        transcribed_content, transcribed_payload = await self._prepare_user_message(
            conversation_id, content, message_type, audio_url, audio_duration_seconds, media_urls, timings
        )
        
        user_message = Message(
            id=user_message_id,
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=transcribed_content or "",
            message_type=MessageType(message_type),
            media_urls=media_urls or [],
            audio_url=audio_url,
            audio_duration_seconds=audio_duration_seconds,
            created_at=datetime.now(UTC),
            metadata={}
        )
        timings["prepare_user_message"] = time.time() - t0

        # 3. Context & History
        history, enhanced_instructions = await self._build_ai_context(
            conversation_id, user_message.id, influencer, memories, timings
        )
        ai_input_content = str(content or transcribed_payload or "What do you think?")

        # 4. Multimodal Preparation
        media_urls_for_ai = None
        if message_type in [MessageType.IMAGE, MessageType.MULTIMODAL] and media_urls:
            t0 = time.time()
            media_urls_for_ai = await self._convert_media_urls_for_ai_async(media_urls)
            timings["convert_media_urls"] = time.time() - t0

        # 5. AI Generation
        response_text, token_count = await self._generate_ai_response(
            influencer, ai_input_content, enhanced_instructions, history, media_urls_for_ai, timings
        )

        # 6. Assistant Message
        assistant_message_id = str(uuid.uuid4())
        assistant_message = Message(
            id=assistant_message_id,
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=response_text,
            message_type=MessageType.TEXT,
            token_count=token_count,
            created_at=datetime.now(UTC),
            metadata={}
        )

        # 7. Persistence & Post-Processing
        user_msg_kwargs = {
            "conversation_id": conversation_id,
            "role": MessageRole.USER,
            "content": transcribed_content or "",
            "message_type": MessageType(message_type),
            "media_urls": media_urls or [],
            "audio_url": audio_url,
            "audio_duration_seconds": audio_duration_seconds,
            "message_id_override": user_message_id
        }
        
        assistant_msg_kwargs = {
            "conversation_id": conversation_id,
            "role": MessageRole.ASSISTANT,
            "content": response_text,
            "message_type": MessageType.TEXT,
            "token_count": token_count,
            "message_id_override": assistant_message_id
        }


        # 7. Write-Through Cache (Immediate Consistency)
        cache_key = f"conversation:{conversation_id}:messages"
        await cache.lpush(cache_key, user_message, assistant_message)
        await cache.expire(cache_key, 3600)

        # 8. Queue persistence & secondary tasks
        if background_tasks:
            background_tasks.add_task(self._persist_message, **user_msg_kwargs)
            background_tasks.add_task(self._persist_message, **assistant_msg_kwargs)
            logger.info(f"Messages queued for background persistence: {user_message_id}, {assistant_message_id}")
            
            # Queue secondary tasks
            background_tasks.add_task(self._update_conversation_memories, conversation_id, conversation, ai_input_content, response_text, memories, is_nsfw=influencer.is_nsfw)
            background_tasks.add_task(log_ai_usage, model="gemini", tokens=token_count, user_id=user_id, conversation_id=str(conversation_id))
            background_tasks.add_task(update_conversation_stats, conversation_id=str(conversation_id))
            background_tasks.add_task(invalidate_cache_for_user, user_id=user_id)
        else:
            logger.warning(f"No background_tasks provided for send_message in conversation {conversation_id}. Messages will not be persisted.")

        # 9. Latency Tracking
        timings["total"] = time.time() - total_start
        timing_str = ", ".join(f"{k}={v*1000:.0f}ms" for k, v in timings.items())
        log_lvl = logger.warning if timings["total"] > 5 else logger.info
        log_lvl(f"send_message timings [{conversation_id}]: {timing_str}")

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
        """List user's conversations with recent messages populated"""
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
        
        # Batch fetch recent messages for all conversations to avoid N+1 queries
        if conversations:
            conversation_ids = [UUID(conv.id) for conv in conversations]
            recent_messages_map = await self.message_repo.get_recent_for_conversations_batch(
                conversation_ids=conversation_ids,
                limit_per_conv=10
            )
            
            # Map back to conversations
            for conv in conversations:
                conv.recent_messages = recent_messages_map.get(conv.id, [])

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

        deleted_messages = await self.message_repo.delete_by_conversation(conversation_id)

        await self.conversation_repo.delete(conversation_id)

        logger.info(f"Deleted conversation {conversation_id} with {deleted_messages} messages")

        return deleted_messages

    async def _save_message(self, **kwargs) -> Message:
        """
        Helper to save a message and handle conversation deletion race conditions.
        
        Automatically converts conversation_id to UUID if provided as string.
        Raises NotFoundException if the conversation was deleted.
        """
        conv_id = kwargs.get("conversation_id")
        if conv_id and isinstance(conv_id, str):
            kwargs["conversation_id"] = UUID(conv_id)

        try:
            return await self.message_repo.create(**kwargs)
        except sqlite3.IntegrityError as e:
            if "foreign key" in str(e).lower():
                logger.warning(f"Failed to save message: Conversation {conv_id} was deleted during processing.")
                raise NotFoundException("Conversation no longer exists") from e
            raise

