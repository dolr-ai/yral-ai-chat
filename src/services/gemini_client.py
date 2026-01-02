"""
Google Gemini AI Client
"""
import json
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
        Generate AI response
        
        Args:
            user_message: Current user message
            system_instructions: AI personality instructions
            conversation_history: Previous messages for context
            media_urls: Optional image URLs for multimodal input
            
        Returns:
            Tuple of (response_text, token_count)
        """
        try:
            # Ensure user_message is a string
            user_message_str = str(user_message) if not isinstance(user_message, str) else user_message
            
            # Build conversation context
            contents = self._build_system_instructions(system_instructions)
            
            # Add conversation history
            if conversation_history:
                history_contents = await self._build_history_contents(conversation_history)
                contents.extend(history_contents)
            
            # Add current message
            current_message = await self._build_current_message(user_message_str, media_urls)
            contents.append(current_message)

            # Generate response
            response_text, token_count = await self._generate_content(contents)
            
            return response_text, int(token_count)

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

            # Add text content - ensure it's a string
            if msg.content:
                text_content = str(msg.content) if not isinstance(msg.content, str) else msg.content
                parts.append({"text": text_content})

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
            # Ensure user_message is a string
            text_content = str(user_message) if not isinstance(user_message, str) else user_message
            current_parts.append({"text": text_content})

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

    async def _generate_content(self, contents: list[dict]) -> tuple[str, float]:
        """Generate content using Gemini API"""
        logger.info(f"Generating Gemini response with {len(contents)} messages")

        generation_config = genai.types.GenerationConfig(
            max_output_tokens=settings.gemini_max_tokens,
            temperature=settings.gemini_temperature
        )

        response = self.model.generate_content(
            contents,
            generation_config=generation_config
        )

        # Extract response text
        response_text = response.text
        
        # Check finish reason
        if response.candidates and response.candidates[0].finish_reason != 1:  # 1 = STOP
            logger.warning(f"Response finished with reason: {response.candidates[0].finish_reason} (not STOP)")

        # Estimate token count (rough estimate)
        token_count = len(response_text.split()) * 1.3  # Approximate

        logger.info(f"Generated response: {len(response_text)} chars, ~{int(token_count)} tokens")

        return response_text, token_count

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
                    if char == "{":
                        if brace_count == 0:
                            start_idx = i
                        brace_count += 1
                    elif char == "}":
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


