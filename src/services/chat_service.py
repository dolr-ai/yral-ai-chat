"""
Chat service - Business logic for conversations and messages
"""

import sqlite3
import time
from datetime import UTC, datetime
from uuid import UUID

import httpx
from loguru import logger
from pydantic import validate_call

from src.core.exceptions import ForbiddenException, NotFoundException
from src.core.websocket import manager
from src.db.repositories import ConversationRepository, InfluencerRepository, MessageRepository
from src.models.entities import AIInfluencer, Conversation, Message, MessageRole, MessageType
from src.models.internal import LLMGenerateParams, SendMessageParams
from src.services.gemini_client import GeminiClient
from src.services.notification_service import notification_service
from src.services.openrouter_client import OpenRouterClient
from src.services.replicate_client import ReplicateClient
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
        replicate_client: ReplicateClient | None = None,
    ):
        self.influencer_repo = influencer_repo
        self.conversation_repo = conversation_repo
        self.message_repo = message_repo
        self.storage_service = storage_service
        self.gemini_client = gemini_client
        self.openrouter_client = openrouter_client
        self.replicate_client = replicate_client

    def _select_ai_client(self, is_nsfw: bool):
        """Select appropriate AI client based on content type (NSFW or regular)"""
        if is_nsfw and self.openrouter_client:
            logger.info("Using OpenRouter client for NSFW influencer")
            return self.openrouter_client
        logger.info("Using Gemini client for regular influencer")
        return self.gemini_client

    @validate_call(config={"arbitrary_types_allowed": True})
    async def create_conversation(self, user_id: str, influencer_id: str) -> tuple[Conversation, bool]:
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
        else:
            logger.info(f"No initial_greeting configured for influencer {influencer.id} ({influencer.display_name})")

        conversation.influencer = influencer
        return conversation, True

    async def _transcribe_audio(self, audio_url: str, is_nsfw: bool = False) -> str:
        """Transcribe audio and return transcribed content"""
        try:
            audio_url_for_transcription = audio_url
            if self.storage_service:
                s3_key = self.storage_service.extract_key_from_url(audio_url)
                audio_url_for_transcription = await self.storage_service.generate_presigned_url(s3_key)
            
            ai_client = self._select_ai_client(is_nsfw)
            transcription = await ai_client.transcribe_audio(audio_url_for_transcription)
            transcribed_content = f"[Transcribed: {transcription}]"
            logger.info(f"Audio transcribed by {ai_client.provider_name}: {transcription[:100]}...")
            return transcribed_content
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return "[Audio message - transcription failed]"

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
        conversation_id: str,
        conversation: Conversation,
        user_message: str,
        assistant_response: str,
        memories: dict[str, object],
        is_nsfw: bool = False,
    ) -> None:
        """Extract and update memories from conversation using appropriate client"""
        try:
            ai_client = self._select_ai_client(is_nsfw)
            updated_memories = await ai_client.extract_memories(
                user_message=user_message, assistant_response=assistant_response, existing_memories=memories.copy()
            )

            if updated_memories != memories:
                conversation.metadata["memories"] = updated_memories
                await self.conversation_repo.update_metadata(conversation_id, conversation.metadata)
                logger.info(f"Updated memories: {len(updated_memories)} total memories")
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
        timings: dict[str, float],
        is_nsfw: bool = False,
    ) -> tuple[Message, str]:
        """Transcribe (if needed) and save user message"""
        transcribed_content = content
        if message_type == MessageType.AUDIO and audio_url:
            t0 = time.time()
            transcribed_content = await self._transcribe_audio(audio_url, is_nsfw=is_nsfw)
            timings["transcribe_audio"] = time.time() - t0

        t0 = time.time()
        user_message = await self._save_message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=transcribed_content or "",
            message_type=message_type,
            media_urls=media_urls or [],
            audio_url=audio_url,
            audio_duration_seconds=audio_duration_seconds,
        )
        timings["save_user_message"] = time.time() - t0
        return user_message, transcribed_content or ""

    async def _build_ai_context(
        self,
        conversation_id: str,
        user_message_id: str,
        influencer: object,
        memories: dict[str, object],
        timings: dict[str, float]
    ) -> tuple[list[Message], str]:
        """Fetch history and build system instructions"""
        t0 = time.time()
        all_recent = await self.message_repo.get_recent_for_context(
            conversation_id=conversation_id,
            limit=11
        )
        history = [msg for msg in all_recent if msg.id != user_message_id][:10]
        timings["get_history"] = time.time() - t0

        t0 = time.time()
        await self._convert_history_storage_keys_async(history)
        timings["convert_history_urls"] = time.time() - t0

        enhanced_system_instructions = influencer.system_instructions
        if memories:
            memories_text = "\n\n**MEMORIES:**\n" + "\n".join(f"- {key}: {value}" for key, value in memories.items())
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
            response = await ai_client.generate_response(
                LLMGenerateParams(
                    user_message=ai_input_content,
                    system_instructions=enhanced_instructions,
                    conversation_history=history,
                    media_urls=media_urls_for_ai,
                )
            )
            response_text = response.text
            token_count = response.token_count
            timings["ai_generate_response"] = time.time() - t0
            logger.info(
                f"Response generated successfully from {provider_name}: "
                f"{len(response_text)} chars, {token_count} tokens"
            )
            return response_text, token_count
        except Exception as e:
            if "t0" in locals():
                timings["ai_generate_response"] = time.time() - t0
            logger.error("AI response generation failed for influencer {}: {}", influencer.id, str(e), exc_info=True)
            return self.FALLBACK_ERROR_MESSAGE, 0

    @validate_call(config={"arbitrary_types_allowed": True})
    async def send_message(self, params: SendMessageParams) -> tuple[Message, Message]:
        """
        Send a message and get AI response

        Args:
            params: Message sending parameters

        Returns:
            Tuple of (user_message, assistant_message)
        """
        timings: dict[str, float] = {}
        total_start = time.time()

        # 1. Validation & Context
        t0 = time.time()
        conversation, influencer = await self._validate_and_get_context(params.conversation_id, params.user_id)
        timings["get_context"] = time.time() - t0
        memories = conversation.metadata.get("memories", {})

        # 2. User Message
        user_message, transcribed_payload = await self._prepare_user_message(
            params.conversation_id,
            params.content,
            params.message_type,
            params.audio_url,
            params.audio_duration_seconds,
            params.media_urls,
            timings,
            is_nsfw=influencer.is_nsfw
        )
        logger.info(f"User message saved: {user_message.id}")

        # 3. Context & History
        history, enhanced_instructions = await self._build_ai_context(
            params.conversation_id, user_message.id, influencer, memories, timings
        )
        ai_input_content = str(params.content or transcribed_payload or "What do you think?")

        # 4. Multimodal Preparation
        media_urls_for_ai = None
        if params.message_type in [MessageType.IMAGE, MessageType.MULTIMODAL] and params.media_urls:
            t0 = time.time()
            media_urls_for_ai = await self._convert_media_urls_for_ai_async(params.media_urls)
            timings["convert_media_urls"] = time.time() - t0

        # 5. AI Generation
        response_text, token_count = await self._generate_ai_response(
            influencer, ai_input_content, enhanced_instructions, history, media_urls_for_ai, timings
        )

        # 6. Save Assistant Message
        t0 = time.time()
        assistant_message = await self._save_message(
            conversation_id=params.conversation_id,
            role=MessageRole.ASSISTANT,
            content=response_text,
            message_type=MessageType.TEXT,
            token_count=token_count
        )
        timings["save_assistant_message"] = time.time() - t0
        logger.info(f"Assistant message saved: {assistant_message.id}")

        # 7. Finalize & Latency Tracking
        timings["total"] = time.time() - total_start
        timing_str = ", ".join(f"{k}={v*1000:.0f}ms" for k, v in timings.items())
        log_lvl = logger.warning if timings["total"] > 5 else logger.info
        log_lvl(f"send_message timings [{params.conversation_id}]: {timing_str}")

        if params.background_tasks and hasattr(params.background_tasks, "add_task"):
            params.background_tasks.add_task(
                self._update_conversation_memories,
                params.conversation_id,
                conversation,
                ai_input_content,
                response_text,
                memories,
                is_nsfw=influencer.is_nsfw,
            )
        else:
            await self._update_conversation_memories(
                params.conversation_id, conversation, ai_input_content, response_text, memories, is_nsfw=influencer.is_nsfw
            )

        # Handle real-time updates and notifications
        await self._handle_message_notifications(
            user_id=params.user_id,
            conversation_id=params.conversation_id,
            assistant_message=assistant_message,
            influencer=influencer,
        )

        return user_message, assistant_message

    async def _handle_message_notifications(
        self,
        user_id: str,
        conversation_id: UUID | str,
        assistant_message: Message,
        influencer: AIInfluencer,
    ) -> None:
        """Handle real-time updates and push notifications for a new message"""
        # Broadcast new message via WebSocket
        try:
            # Get updated unread count for this conversation
            updated_conversation = await self.conversation_repo.get_by_id(conversation_id)
            unread_count = updated_conversation.unread_count if updated_conversation else 1
            
            # Broadcast to user
            await manager.broadcast_new_message(
                user_id=user_id,
                conversation_id=conversation_id,
                message={
                    "id": str(assistant_message.id),
                    "role": assistant_message.role.value,
                    "content": assistant_message.content,
                    "message_type": assistant_message.message_type.value,
                    "created_at": assistant_message.created_at.isoformat(),
                    "status": assistant_message.status,
                    "is_read": assistant_message.is_read,
                },
                influencer={
                    "id": str(influencer.id),
                    "display_name": influencer.display_name,
                    "avatar_url": influencer.avatar_url,
                    "is_online": True,  # Influencers are always "online"
                },
                unread_count=unread_count,
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast message via WebSocket: {e}")

        # Send push notification
        try:
            await notification_service.send_push_notification(
                user_id=user_id,
                title=influencer.display_name,
                body=assistant_message.content[:100] if assistant_message.content else "New message",
                data={
                    "conversation_id": str(conversation_id),
                    "message_id": str(assistant_message.id),
                    "influencer_id": str(influencer.id),
                },
            )
        except Exception as e:
            logger.warning(f"Failed to send push notification: {e}")


    async def generate_image_for_conversation(self, conversation_id: str, user_id: str, prompt: str | None = None) -> Message:
        """
        Generate an image for a conversation

        Args:
            conversation_id: Conversation ID
            user_id: User requesting the image
            prompt: Optional prompt. If None, generated from context.

        Returns:
            Created message with image
        """
        if not self.replicate_client:
            raise NotImplementedError("Image generation service not available")

        if not self.storage_service:
            raise NotImplementedError("Storage service not available")

        conversation = await self.get_conversation(UUID(conversation_id), user_id)
        influencer = await self.influencer_repo.get_by_id(conversation.influencer_id)
        if not influencer:
            raise NotFoundException("Influencer not found")

        # 1. Determine Prompt
        final_prompt = prompt
        if not final_prompt:
            logger.info("No prompt provided, generating from context...")
            # Fetch recent context
            messages = await self.message_repo.list_by_conversation(
                conversation_id=conversation.id,
                limit=10,
                order="desc"
            )
            # Reverse to chronological order
            context_msgs = messages[::-1]
            
            # Simple content join for now, could be more sophisticated
            context_str = "\n".join([f"{m.role}: {m.content}" for m in context_msgs if m.content])
            
            extract_prompt_system = (
                "You are an AI assistant helping to visualize a scene. "
                "Based on the recent conversation, generate a detailed image generation prompt "
                "that captures the current context, action, or requested visual. "
                "Output ONLY the prompt, no other text."
            )
            
            response = await self.gemini_client.generate_response(
                LLMGenerateParams(
                    user_message=f"Conversation Context:\n{context_str}\n\nGenerate an image prompt:",
                    system_instructions=extract_prompt_system,
                )
            )
            final_prompt = response.text.strip()
            logger.info(f"Generated prompt: {final_prompt}")

        # 2. Generate Image
        logger.info(f"Generating image with prompt: {final_prompt}")
        image_url = await self.replicate_client.generate_image_via_image(
            prompt=final_prompt,
            aspect_ratio="9:16",
            input_image=influencer.avatar_url
        )
        
        if not image_url:
            raise RuntimeError("Failed to generate image from upstream provider")

        # 3. Download and Upload to S3
        async with httpx.AsyncClient() as client:
            resp = await client.get(image_url)
            if resp.status_code != 200:
                raise RuntimeError(f"Failed to download generated image: {resp.status_code}")
            image_data = resp.content

        # Save to S3
        s3_key, _, _ = await self.storage_service.save_file(
            file_content=image_data,
            filename=f"generated_{UUID(int=0)}.jpg",
            user_id=user_id
        )

        # 4. Create Assistant Message
        return await self._save_message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="",
            message_type=MessageType.IMAGE,
            media_urls=[s3_key],
            token_count=0
        )

    async def get_conversation(self, conversation_id: UUID, user_id: str) -> Conversation:
        """Get conversation by ID and verify ownership"""
        conversation = await self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            raise NotFoundException("Conversation not found")

        if conversation.user_id != user_id:
            raise ForbiddenException("Not your conversation")

        return conversation

    async def list_conversations(
        self, user_id: str, influencer_id: UUID | None = None, limit: int = 20, offset: int = 0
    ) -> tuple[list[Conversation], int]:
        """List user's conversations with recent messages populated"""
        conversations = await self.conversation_repo.list_by_user(
            user_id=user_id, influencer_id=influencer_id, limit=limit, offset=offset
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
        self, conversation_id: UUID, user_id: str, limit: int = 50, offset: int = 0, order: str = "desc"
    ) -> tuple[list[Message], int]:
        """List messages in a conversation"""
        await self.get_conversation(conversation_id, user_id)

        messages = await self.message_repo.list_by_conversation(
            conversation_id=conversation_id, limit=limit, offset=offset, order=order
        )

        total = await self.message_repo.count_by_conversation(conversation_id)

        return messages, total

    async def delete_conversation(self, conversation_id: UUID, user_id: str) -> int:
        """Delete a conversation"""
        await self.get_conversation(conversation_id, user_id)

        deleted_messages = await self.message_repo.delete_by_conversation(conversation_id)

        await self.conversation_repo.delete(conversation_id)

        logger.info(f"Deleted conversation {conversation_id} with {deleted_messages} messages")

        return deleted_messages
    async def mark_conversation_as_read(self, conversation_id: UUID, user_id: str) -> dict[str, object]:
        """Mark conversation as read"""
        await self.get_conversation(conversation_id, user_id)
        
        await self.message_repo.mark_as_read(conversation_id)
        
        read_at = datetime.now(UTC)
        result = {
            "id": str(conversation_id),
            "unread_count": 0,
            "last_read_at": read_at
        }
        
        # Broadcast conversation read event via WebSocket
        try:
            await manager.broadcast_conversation_read(
                user_id=user_id,
                conversation_id=conversation_id,
                read_at=read_at.isoformat(),
            )
        except Exception as e:
            # Don't fail the operation if WebSocket broadcast fails
            logger.warning(f"Failed to broadcast conversation read via WebSocket: {e}")
        
        return result


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

