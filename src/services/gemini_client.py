"""
Google Gemini AI Client
"""
import json
import re
import time
from typing import Any

import google.generativeai as genai
import httpx
from loguru import logger

from src.config import settings
from src.core.exceptions import AIServiceException, TranscriptionException
from src.models.entities import Message, MessageRole, MessageType


class GeminiClient:
    """Google Gemini AI client wrapper"""

    def __init__(self):
        """Initialize Gemini client"""
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel(settings.gemini_model)
        self.http_client = httpx.AsyncClient(timeout=30.0)
        logger.info(f"Gemini client initialized with model: {settings.gemini_model}")

    async def generate_response(
        self,
        user_message: str,
        system_instructions: str,
        conversation_history: list[Message] = None,
        media_urls: list[str] = None
    ) -> tuple[str, int]:
        """
        Generate AI response with automatic retry on truncation (up to 3 attempts total)
        
        Args:
            user_message: Current user message
            system_instructions: AI personality instructions
            conversation_history: Previous messages for context
            media_urls: Optional image URLs for multimodal input
            
        Returns:
            Tuple of (response_text, token_count)
        """
        try:
            # Build conversation context
            contents = self._build_system_instructions(system_instructions)
            
            # Add conversation history
            if conversation_history:
                history_contents = await self._build_history_contents(conversation_history)
                contents.extend(history_contents)
            
            # Add current message
            current_message = await self._build_current_message(user_message, media_urls)
            contents.append(current_message)

            # Generate response with retry logic (up to 3 attempts total)
            max_attempts = 3
            best_response_text = ""
            best_token_count = 0
            
            for attempt in range(1, max_attempts + 1):
                logger.info(f"Generating response (attempt {attempt}/{max_attempts})")
                response_text, token_count, was_truncated = await self._generate_content(contents)
                
                # Keep the longest response (likely most complete) for truncated responses
                if len(response_text) > len(best_response_text):
                    best_response_text = response_text
                    best_token_count = token_count
                
                # If response was not truncated, return it immediately (don't use best_response_text)
                if not was_truncated:
                    logger.info(f"Response completed successfully on attempt {attempt}")
                    return response_text, int(token_count)
                
                # If this was the last attempt, return the best response we got
                if attempt == max_attempts:
                    logger.warning(
                        f"Response was truncated after {max_attempts} attempts. "
                        f"Returning best response ({len(best_response_text)} chars)"
                    )
                    return best_response_text, int(best_token_count)
                
                # Otherwise, retry
                logger.info(f"Response was truncated on attempt {attempt}, retrying...")
            
            # Should never reach here, but return best response if we do
            return best_response_text, int(best_token_count)

        except AIServiceException:
            raise
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise AIServiceException(f"Failed to generate AI response: {e!s}") from e

    def _build_system_instructions(self, system_instructions: str) -> list[dict]:
        """Build system instruction messages"""
        return [
            {
                "role": "user",
                "parts": [{"text": f"""System Instructions: {system_instructions}. Lastly, always answer in the same language as the user's message."""}]
            },
            {
                "role": "model",
                "parts": [{"text": "Understood. I will follow these instructions."}]
            }
        ]

    async def _build_history_contents(self, conversation_history: list[Message]) -> list[dict]:
        """Build conversation history contents"""
        contents = []
        
        for msg in conversation_history[-10:]:  # Last 10 messages for context
            role = "user" if msg.role == MessageRole.USER else "model"
            parts = []

            # Add text content
            if msg.content:
                parts.append({"text": msg.content})

            # Add images from history if available
            if msg.message_type in [MessageType.IMAGE, MessageType.MULTIMODAL]:
                await self._add_images_to_parts(msg.media_urls[:3], parts, warn_on_error=True)

            if parts:
                contents.append({"role": role, "parts": parts})
        
        return contents

    async def _build_current_message(self, user_message: str, media_urls: list[str] | None) -> dict:
        """Build current user message with optional images"""
        current_parts = []

        if user_message:
            current_parts.append({"text": user_message})

        # Add current images
        if media_urls:
            await self._add_images_to_parts(media_urls[:5], current_parts, warn_on_error=False)

        return {"role": "user", "parts": current_parts}

    async def _add_images_to_parts(
        self,
        image_urls: list[str],
        parts: list[dict],
        warn_on_error: bool = False
    ) -> None:
        """Add images to message parts"""
        for url in image_urls:
            try:
                image_data = await self._download_image(url)
                parts.append({"inline_data": image_data})
            except Exception as e:
                if warn_on_error:
                    logger.warning(f"Failed to load image from history: {e}")
                else:
                    logger.error(f"Failed to download image {url}: {e}")
                    raise AIServiceException(f"Failed to process image: {e}") from e

    async def _generate_content(self, contents: list[dict]) -> tuple[str, float, bool]:
        """
        Generate content using Gemini API
        
        Returns:
            Tuple of (response_text, token_count, was_truncated)
        """
        logger.info(f"Generating Gemini response with {len(contents)} messages")

        generation_config = genai.types.GenerationConfig(
            max_output_tokens=settings.gemini_max_tokens,
            temperature=settings.gemini_temperature
        )

        response = self.model.generate_content(
            contents,
            generation_config=generation_config
        )

        # Check if response was truncated due to token limit or safety filters
        finish_reason = None
        is_truncated = False
        safety_blocked = False
        
        if response.candidates and len(response.candidates) > 0:
            candidate = response.candidates[0]
            finish_reason = candidate.finish_reason
            finish_reason_str = str(finish_reason) if finish_reason else None
            
            # Check for safety filter blocks
            if hasattr(candidate, 'safety_ratings') and candidate.safety_ratings:
                blocked_categories = [
                    rating.category for rating in candidate.safety_ratings
                    if hasattr(rating, 'probability') and 'HIGH' in str(rating.probability).upper()
                ]
                if blocked_categories:
                    safety_blocked = True
                    logger.warning(
                        f"Response was BLOCKED by safety filters for categories: {blocked_categories}. "
                        f"The response may be incomplete or empty."
                    )
            
            # Check if response was truncated (finish_reason can be enum or string)
            # MAX_TOKENS indicates the response hit the token limit and was cut off
            if finish_reason_str and "MAX_TOKENS" in finish_reason_str:
                is_truncated = True
                logger.warning(
                    f"Response was TRUNCATED due to MAX_TOKENS limit ({settings.gemini_max_tokens}). "
                    f"The response may be incomplete. Consider increasing GEMINI_MAX_TOKENS."
                )
            elif finish_reason_str and finish_reason_str not in ("STOP", "FinishReason.STOP", "1"):
                # Other non-normal finish reasons (SAFETY, RECITATION, etc.)
                if "SAFETY" in finish_reason_str:
                    safety_blocked = True
                    is_truncated = True  # Consider safety blocks as truncation for retry purposes
                else:
                    # RECITATION or other finish reasons also indicate potential truncation
                    is_truncated = True
                logger.warning(
                    f"Response finished with reason: {finish_reason_str}. "
                    f"This may indicate an incomplete or blocked response."
                )

        # Extract response text - handle ValueError if blocked by safety filters
        try:
            response_text = response.text
        except ValueError as e:
            # response.text raises ValueError when blocked by safety filters
            safety_blocked = True
            is_truncated = True  # Consider safety blocks as truncation for retry purposes
            logger.error(
                f"Failed to extract response text (likely blocked by safety filters): {e}. "
                f"Attempting to extract text from parts manually."
            )
            
            # Try to extract text from parts manually
            response_text = ""
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    text_parts = []
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            text_parts.append(part.text)
                    response_text = "".join(text_parts)
                    
            if not response_text:
                logger.warning("No text content could be extracted from response (fully blocked by safety filters)")
                response_text = ""  # Return empty string if completely blocked

        # Estimate token count (rough estimate)
        token_count = len(response_text.split()) * 1.3  # Approximate

        log_msg = f"Generated response: {len(response_text)} chars, ~{int(token_count)} tokens"
        if is_truncated:
            log_msg += " [TRUNCATED]"
        if safety_blocked:
            log_msg += " [SAFETY_BLOCKED]"
        logger.info(log_msg)

        return response_text, token_count, is_truncated

    async def transcribe_audio(self, audio_url: str) -> str:
        """
        Transcribe audio file using Gemini
        
        Args:
            audio_url: URL to audio file
            
        Returns:
            Transcribed text
        """
        try:
            logger.info(f"Transcribing audio from {audio_url}")

            # Download audio file
            audio_data = await self._download_audio(audio_url)

            # Use Gemini to transcribe
            prompt = "Please transcribe this audio file accurately. Only return the transcription text without any additional commentary."

            response = self.model.generate_content([
                prompt,
                {"inline_data": audio_data}
            ])

            transcription = response.text.strip()
            logger.info(f"Audio transcribed: {len(transcription)} characters")
        except Exception as e:
            logger.error(f"Audio transcription error: {e}")
            raise TranscriptionException(f"Failed to transcribe audio: {e!s}") from e
        else:
            return transcription

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
        existing_memories: dict[str, str] = None
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


