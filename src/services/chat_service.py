"""
Chat service - Business logic for conversations and messages
"""

import sqlite3
from datetime import UTC, datetime
from uuid import UUID

import httpx
from loguru import logger
from pydantic import validate_call

from src.core.exceptions import ForbiddenException, NotFoundException
from src.core.websocket import manager
from src.db.repositories import ConversationRepository, InfluencerRepository, MessageRepository
from src.models.entities import (
    AIInfluencer,
    Conversation,
    InfluencerStatus,
    LastMessageInfo,
    Message,
    MessageRole,
    MessageType,
)
from src.models.internal import LLMGenerateParams, PushNotificationData, SendMessageParams
from src.models.responses import InfluencerBasicInfo, MessageResponse
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
        if not influencer or influencer.is_active == InfluencerStatus.DISCONTINUED:
            raise NotFoundException("Influencer not found")

        existing = await self.conversation_repo.get_existing(user_id, influencer_id)
        if existing:
            return await self._hydrate_existing_conversation(existing, influencer), False

        try:
            conversation = await self.conversation_repo.create(user_id, influencer_id)
        except sqlite3.IntegrityError:
            # Race condition: someone else created it just now
            existing = await self.conversation_repo.get_existing(user_id, influencer_id)
            if existing:
                return await self._hydrate_existing_conversation(existing, influencer), False
            raise

        logger.info(f"Created new conversation: {conversation.id}")
        conversation.influencer = influencer
        
        # Add initial greeting if configured
        greeting_msg = None
        if influencer.initial_greeting:
            logger.info(f"Creating initial greeting for conversation {conversation.id}")
            greeting_msg = await self._save_message(
                conversation_id=conversation.id,
                role=MessageRole.ASSISTANT,
                content=influencer.initial_greeting,
                message_type=MessageType.TEXT
            )

        conversation.recent_messages = [greeting_msg] if greeting_msg else []
        conversation.message_count = 1 if greeting_msg else 0
        if greeting_msg:
            conversation.last_message = LastMessageInfo(
                content=greeting_msg.content,
                role=greeting_msg.role,
                created_at=greeting_msg.created_at,
                status=greeting_msg.status,
                is_read=greeting_msg.is_read
            )
        return conversation, True

    async def _hydrate_existing_conversation(self, conversation: Conversation, influencer: AIInfluencer) -> Conversation:
        """Populate history and metadata for an existing conversation"""
        logger.info(f"Returning existing conversation: {conversation.id}")
        conversation.influencer = influencer
        conversation.recent_messages = await self.message_repo.get_recent_for_context(
            conversation_id=UUID(conversation.id),
            limit=10
        )
        conversation.last_message = await self.conversation_repo._get_last_message(UUID(conversation.id))
        conversation.message_count = await self.message_repo.count_by_conversation(UUID(conversation.id))
        return conversation

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

    async def validate_access_and_get_context(
        self,
        conversation_id: str,
        user_id: str
    ) -> tuple[Conversation, AIInfluencer]:
        """Validate conversation/user and return conversation and influencer"""
        conversation = await self.conversation_repo.get_by_id(conversation_id)
        if not conversation:
            raise NotFoundException("Conversation not found")

        if conversation.user_id != user_id:
            raise ForbiddenException("Not your conversation")

        influencer = await self.influencer_repo.get_by_id(conversation.influencer_id)
        if not influencer:
            raise NotFoundException("Influencer not found")

        if influencer.is_active == InfluencerStatus.DISCONTINUED:
            raise ForbiddenException("This bot has been deleted and can no longer receive messages.")

        return conversation, influencer

    async def persist_user_message(
        self,
        conversation_id: str,
        content: str,
        message_type: str,
        audio_url: str | None,
        audio_duration_seconds: int | None,
        media_urls: list[str] | None,
        is_nsfw: bool = False,
        client_message_id: str | None = None
    ) -> tuple[Message, str]:
        """Transcribe (if needed) and save user message"""
        transcribed_content = content
        if message_type == MessageType.AUDIO and audio_url:
            transcribed_content = await self._transcribe_audio(audio_url, is_nsfw=is_nsfw)

        user_message = await self._save_message(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=transcribed_content or "",
            message_type=message_type,
            media_urls=media_urls or [],
            audio_url=audio_url,
            audio_duration_seconds=audio_duration_seconds,
            client_message_id=client_message_id
        )
        return user_message, transcribed_content or ""

    async def assemble_ai_context(
        self,
        conversation_id: str,
        user_message_id: str,
        influencer: AIInfluencer,
        memories: dict[str, object]
    ) -> tuple[list[Message], str]:
        """Fetch history and build system instructions"""
        all_recent = await self.message_repo.get_recent_for_context(
            conversation_id=conversation_id,
            limit=11
        )
        history = [msg for msg in all_recent if msg.id != user_message_id][:10]

        await self._convert_history_storage_keys_async(history)

        enhanced_system_instructions = influencer.system_instructions
        if memories:
            memories_text = "\n\n**MEMORIES:**\n" + "\n".join(f"- {key}: {value}" for key, value in memories.items())
            enhanced_system_instructions = influencer.system_instructions + memories_text
            
        return history, enhanced_system_instructions

    async def invoke_ai_provider(
        self,
        influencer: AIInfluencer,
        ai_input_content: str,
        enhanced_instructions: str,
        history: list[Message],
        media_urls_for_ai: list[str] | None
    ) -> tuple[str, int]:
        """Select client and generate AI response"""
        try:
            ai_client = self._select_ai_client(influencer.is_nsfw)
            provider_name = "OpenRouter" if influencer.is_nsfw else "Gemini"
            logger.info(
                f"Generating response for influencer {influencer.id} ({influencer.display_name}) "
                f"using {provider_name} provider"
            )
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
            logger.info(
                f"Response generated successfully from {provider_name}: "
                f"{len(response_text)} chars, {token_count} tokens"
            )
            return response_text, token_count
        except Exception:
            return self.FALLBACK_ERROR_MESSAGE, 0

    @validate_call(config={"arbitrary_types_allowed": True})
    async def send_message(self, params: SendMessageParams) -> tuple[Message, Message, bool]:
        """
        Send a message and get AI response
        """
        # 1. Validation & Context
        conversation, influencer = await self.validate_access_and_get_context(params.conversation_id, params.user_id)
        memories = conversation.metadata.get("memories", {})

        # 2. Deduplication Check
        if params.client_message_id:
            existing_user_msg = await self.message_repo.get_by_client_id(
                UUID(params.conversation_id), params.client_message_id
            )
            if existing_user_msg:
                logger.info(f"Duplicate message detected: client_message_id={params.client_message_id}")
                assistant_reply = await self.message_repo.get_assistant_reply(existing_user_msg.id)
                if assistant_reply:
                    return existing_user_msg, assistant_reply, True

        # 3. Persist User Message
        user_message, transcribed_payload = await self.persist_user_message(
            params.conversation_id,
            params.content,
            params.message_type,
            params.audio_url,
            params.audio_duration_seconds,
            params.media_urls,
            is_nsfw=influencer.is_nsfw,
            client_message_id=params.client_message_id
        )

        # 4. Context & History
        history, enhanced_instructions = await self.assemble_ai_context(
            params.conversation_id, user_message.id, influencer, memories
        )
        ai_input_content = str(params.content or transcribed_payload or "What do you think?")

        # 5. Multimodal Preparation
        media_urls_for_ai = None
        if params.message_type in [MessageType.IMAGE, MessageType.MULTIMODAL] and params.media_urls:
            media_urls_for_ai = await self._convert_media_urls_for_ai_async(params.media_urls)

        # 6. AI Generation
        await self._broadcast_typing(params.user_id, params.conversation_id, influencer.id, True)
        
        response_text, token_count = await self.invoke_ai_provider(
            influencer, ai_input_content, enhanced_instructions, history, media_urls_for_ai
        )

        await self._broadcast_typing(params.user_id, params.conversation_id, influencer.id, False)

        # 7. Save Assistant Message
        assistant_message = await self._save_message(
            conversation_id=params.conversation_id,
            role=MessageRole.ASSISTANT,
            content=response_text,
            message_type=MessageType.TEXT,
            token_count=token_count
        )

        # 8. Background Tasks & Notifications
        await self._trigger_post_message_tasks(params, conversation, ai_input_content, response_text, memories, influencer, assistant_message)

        return user_message, assistant_message, False

    async def _broadcast_typing(self, user_id: str, conversation_id: str, influencer_id: str, is_typing: bool):
        """Helper to broadcast typing status safely"""
        try:
            await manager.emit_typing_status_event(
                user_id=user_id,
                conversation_id=UUID(conversation_id),
                influencer_id=str(influencer_id),
                is_typing=is_typing
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast typing status: {e}")

    async def _trigger_post_message_tasks(
        self, params: SendMessageParams, conversation: Conversation,
        ai_input_content: str, response_text: str, memories: dict,
        influencer: AIInfluencer, assistant_message: Message
    ):
        """Handle background tasks and notifications after message exchange"""
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
            await manager.emit_new_message_event(
                user_id=user_id,
                conversation_id=UUID(str(conversation_id)),
                message=MessageResponse(
                    id=assistant_message.id,
                    role=assistant_message.role,
                    content=assistant_message.content,
                    message_type=assistant_message.message_type,
                    created_at=assistant_message.created_at,
                    status=assistant_message.status,
                    is_read=assistant_message.is_read,
                ),
                influencer=InfluencerBasicInfo(
                    id=influencer.id,
                    name=influencer.name,
                    display_name=influencer.display_name,
                    avatar_url=influencer.avatar_url,
                    is_online=True,  # Influencers are always "online"
                ),
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
                data=PushNotificationData(
                    conversation_id=str(conversation_id),
                    message_id=str(assistant_message.id),
                    influencer_id=str(influencer.id),
                ),
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

        if influencer.is_active == InfluencerStatus.DISCONTINUED:
            raise ForbiddenException("This bot has been deleted and can no longer generate images.")

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
            await manager.emit_conversation_read_event(
                user_id=user_id,
                conversation_id=UUID(str(conversation_id)),
                read_at=read_at.isoformat()
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
            msg = str(e).lower()
            if "foreign key" in msg:
                logger.warning(f"Failed to save message: Conversation {conv_id} was deleted during processing.")
                raise NotFoundException("Conversation no longer exists") from e
            if "unique" in msg and "client_message_id" in msg:
                logger.warning(f"Deduplication triggered at DB level for client_message_id: {kwargs.get('client_message_id')}")
                # This could happen in rare race condition.
                # Ideally, get_by_client_id should have caught it, but we handle it here too.
                # However, repo's create doesn't catch it and return existing, it raises.
                # Since return type is Message, we'd need to fetch the existing one.
                existing = await self.message_repo.get_by_client_id(
                    kwargs["conversation_id"], kwargs["client_message_id"]
                )
                if existing:
                    return existing
            raise

