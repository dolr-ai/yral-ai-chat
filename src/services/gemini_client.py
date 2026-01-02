"""
Gemini AI Client via OpenRouter (more uncensored)
"""
import base64
import json
import re
import time
from typing import Any

import httpx
from loguru import logger

from src.config import settings
from src.core.exceptions import AIServiceException, TranscriptionException
from src.models.entities import Message, MessageRole, MessageType


class GeminiClient:
    """Gemini AI client wrapper using OpenRouter API"""

    def __init__(self):
        """Initialize Gemini client via OpenRouter"""
        self.api_key = settings.openrouter_api_key
        self.model = settings.openrouter_model
        self.base_url = settings.openrouter_base_url
        self.http_client = httpx.AsyncClient(
            timeout=60.0,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://yral.com",
                "X-Title": "Yral AI Chat"
            }
        )
        logger.info(f"Gemini client initialized via OpenRouter with model: {self.model}")

    async def generate_response(
        self,
        user_message: str,
        system_instructions: str,
        conversation_history: list[Message] | None = None,
        media_urls: list[str] | None = None,
        safety_settings: list[dict[str, Any]] | None = None
    ) -> tuple[str, int]:
        """
        Generate AI response
        
        Args:
            user_message: Current user message
            system_instructions: AI personality instructions
            conversation_history: Previous messages for context
            media_urls: Optional image URLs for multimodal input
            safety_settings: Optional safety settings for NSFW content
            
        Returns:
            Tuple of (response_text, token_count)
        """
        try:
            # Ensure user_message is a string
            user_message_str = str(user_message) if not isinstance(user_message, str) else user_message
            
            # Build messages in OpenRouter format
            messages = await self._build_messages_for_openrouter(
                system_instructions,
                conversation_history,
                user_message_str,
                media_urls
            )

            # Generate response via OpenRouter
            response_text, token_count = await self._generate_content_openrouter(messages, safety_settings)
            
            return response_text, int(token_count)

        except AIServiceException:
            raise
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise AIServiceException(f"Failed to generate AI response: {e!s}") from e

    async def _build_messages_for_openrouter(
        self,
        system_instructions: str,
        conversation_history: list[Message] | None,
        user_message: str,
        media_urls: list[str] | None
    ) -> list[dict]:
        """Build messages in OpenAI format for OpenRouter"""
        messages = []
        
        # Add system message
        messages.append({
            "role": "system",
            "content": f"{system_instructions}\n\nAlways answer in the same language as the user's message."
        })
        
        # Add conversation history
        if conversation_history:
            for msg in conversation_history[-10:]:  # Last 10 messages
                role = "user" if msg.role == MessageRole.USER else "assistant"
                content_parts = []
                
                # Add text content
                if msg.content:
                    text_content = str(msg.content) if not isinstance(msg.content, str) else msg.content
                    content_parts.append({
                        "type": "text",
                        "text": text_content
                    })
                
                # Add images from history if available
                if msg.message_type in [MessageType.IMAGE, MessageType.MULTIMODAL] and msg.media_urls:
                    for image_url in msg.media_urls[:3]:
                        try:
                            image_data = await self._download_image_for_openrouter(image_url)
                            content_parts.append(image_data)
                        except Exception as e:
                            logger.warning(f"Failed to load image from history: {e}")
                
                if content_parts:
                    # If only one text part, use string format; otherwise use array format
                    if len(content_parts) == 1 and content_parts[0].get("type") == "text":
                        msg_content: Any = content_parts[0]["text"]
                    else:
                        msg_content = content_parts
                    messages.append({
                        "role": role,
                        "content": msg_content
                    })
        
        # Add current user message
        current_content_parts = []
        if user_message:
            current_content_parts.append({
                "type": "text",
                "text": str(user_message)
            })
        
        # Add current images
        if media_urls:
            for image_url in media_urls[:5]:
                try:
                    image_data = await self._download_image_for_openrouter(image_url)
                    current_content_parts.append(image_data)
                except Exception as e:
                    logger.error(f"Failed to download image {image_url}: {e}")
                    raise AIServiceException(f"Failed to process image: {e}") from e
        
        if current_content_parts:
            # If only one text part, use string format; otherwise use array format
            if len(current_content_parts) == 1 and current_content_parts[0].get("type") == "text":
                user_content: Any = current_content_parts[0]["text"]
            else:
                user_content = current_content_parts
            messages.append({
                "role": "user",
                "content": user_content
            })
        
        return messages

    async def _download_image_for_openrouter(self, url: str) -> dict:
        """Download and encode image for OpenRouter (base64 format)"""
        try:
            response = await self.http_client.get(url)
            response.raise_for_status()
            
            image_data = response.content
            mime_type = response.headers.get("content-type", "image/jpeg")
            
            # Encode to base64
            base64_image = base64.b64encode(image_data).decode('utf-8')
            
            return {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{base64_image}"
                }
            }
        except Exception as e:
            logger.error(f"Failed to download image {url}: {e}")
            raise

    async def _generate_content_openrouter(
        self,
        messages: list[dict],
        safety_settings: list[dict[str, Any]] | None = None
    ) -> tuple[str, float]:
        """Generate content using OpenRouter API"""
        logger.info(f"Generating Gemini response via OpenRouter with {len(messages)} messages")
        
        if safety_settings:
            logger.info(f"Note: OpenRouter doesn't use safety settings (already uncensored), ignoring: {safety_settings}")

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": settings.openrouter_max_tokens,
            "temperature": settings.openrouter_temperature,
        }

        try:
            response = await self.http_client.post(
                f"{self.base_url}/chat/completions",
                json=payload
            )
            response.raise_for_status()
            data = response.json()

            # Extract response
            if "choices" not in data or not data["choices"]:
                raise AIServiceException("No choices returned from OpenRouter API")

            choice = data["choices"][0]
            response_text = choice["message"]["content"]
            
            # Get token usage if available
            usage = data.get("usage", {})
            token_count = usage.get("completion_tokens", len(response_text.split()) * 1.3)

            finish_reason = choice.get("finish_reason", "stop")
            if finish_reason != "stop":
                logger.warning(f"Response finished with reason: {finish_reason} (not stop)")

            logger.info(f"Generated response: {len(response_text)} chars, ~{int(token_count)} tokens")
            return response_text, float(token_count)

        except httpx.HTTPStatusError as e:
            error_msg = f"OpenRouter API error: {e.response.status_code}"
            if e.response.text:
                try:
                    error_data = e.response.json()
                    error_msg += f" - {error_data.get('error', {}).get('message', e.response.text)}"
                except Exception:
                    error_msg += f" - {e.response.text[:200]}"
            logger.error(error_msg)
            raise AIServiceException(error_msg) from e
        except Exception as e:
            logger.error(f"OpenRouter API error: {e}")
            raise AIServiceException(f"Failed to generate AI response: {e!s}") from e


    async def transcribe_audio(self, audio_url: str) -> str:
        """
        Transcribe audio file - Note: OpenRouter doesn't support audio transcription yet.
        This method is kept for compatibility but will raise an error.
        
        Args:
            audio_url: URL to audio file
            
        Returns:
            Transcribed text
        """
        raise TranscriptionException(
            "Audio transcription is not yet supported via OpenRouter. "
            "Please use Whisper API or another transcription service."
        )

    async def _download_image(self, url: str) -> dict[str, Any]:
        """Download and encode image for Gemini"""
        try:
            response = await self.http_client.get(url)
            response.raise_for_status()

            image_data = response.content
            mime_type = response.headers.get("content-type", "image/jpeg")
        except Exception as e:
            logger.error(f"Failed to download image {url}: {e}")
            raise
        else:
            return {
                "mime_type": mime_type,
                "data": image_data
            }

    async def _download_audio(self, url: str) -> dict[str, Any]:
        """Download and encode audio for Gemini"""
        try:
            response = await self.http_client.get(url)
            response.raise_for_status()

            audio_data = response.content
            mime_type = response.headers.get("content-type", "audio/mpeg")
        except Exception as e:
            logger.error(f"Failed to download audio {url}: {e}")
            raise
        else:
            return {
                "mime_type": mime_type,
                "data": audio_data
            }

    async def extract_memories(
        self,
        user_message: str,
        assistant_response: str,
        existing_memories: dict[str, str] | None = None
    ) -> dict[str, str]:
        """
        Extract memories (like height, weight, name, preferences) from conversation
        
        Args:
            user_message: Latest user message
            assistant_response: Latest assistant response
            existing_memories: Current memories dict to merge with
            
        Returns:
            Updated memories dict
        """
        try:
            existing_memories = existing_memories or {}
            
            # Build prompt to extract memories
            existing_memories_text = ""
            if existing_memories:
                existing_memories_text = "\n\nCurrent memories:\n" + "\n".join(
                    f"- {key}: {value}" for key, value in existing_memories.items()
                )
            
            prompt = f"""Extract any factual information about the user from this conversation that should be remembered for future interactions.

Examples of things to remember:
- Physical attributes: height, weight, age, appearance
- Personal information: name, location, occupation, interests
- Preferences: favorite foods, hobbies, goals
- Context: relationship status, family, pets

Recent conversation:
User: {user_message}
Assistant: {assistant_response}
{existing_memories_text}

Return ONLY a JSON object with key-value pairs. Use lowercase keys with underscores (e.g., "height", "weight", "name"). 
If no new information was provided, return an empty object {{}}.
If information updates an existing memory, use the new value.
Format: {{"key1": "value1", "key2": "value2"}}"""

            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Try to extract JSON from response
            extracted = {}
            try:
                # First, try parsing the entire response as JSON
                extracted = json.loads(response_text)
            except json.JSONDecodeError:
                # If that fails, try to find JSON object in the response
                # Look for content between { and } (handling nested objects)
                brace_count = 0
                start_idx = -1
                for i, char in enumerate(response_text):
                    if char == '{':
                        if brace_count == 0:
                            start_idx = i
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0 and start_idx != -1:
                            json_str = response_text[start_idx:i+1]
                            try:
                                extracted = json.loads(json_str)
                                break
                            except json.JSONDecodeError:
                                continue
            
            # Merge extracted memories with existing ones
            if extracted and isinstance(extracted, dict):
                existing_memories.update(extracted)
                logger.info(f"Extracted {len(extracted)} new/updated memories")
            elif not extracted:
                logger.debug("No new memories extracted from conversation")
                
            return existing_memories
            
        except Exception as e:
            logger.error(f"Memory extraction failed: {e}")
            # Return existing memories if extraction fails
            return existing_memories or {}

    async def health_check(self) -> dict:
        """Check Gemini API health"""
        try:
            start = time.time()

            # Simple test request
            self.model.generate_content("Hi")

            latency_ms = int((time.time() - start) * 1000)
        except Exception as e:
            logger.error(f"Gemini health check failed: {e}")
            return {
                "status": "down",
                "error": str(e)
            }
        else:
            return {
                "status": "up",
                "latency_ms": latency_ms
            }

    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()


# Global Gemini client instance
gemini_client = GeminiClient()


