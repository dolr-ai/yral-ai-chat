"""
Google Gemini AI Client - True Async Implementation
"""
import asyncio
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
    """Google Gemini AI client wrapper"""

    def __init__(self):
        """Initialize Gemini client with true async REST API"""
        self.http_client = httpx.AsyncClient(timeout=60.0)
        self.api_base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.api_key = settings.gemini_api_key
        self.model_name = settings.gemini_model
        logger.info(f"Gemini client initialized with model: {settings.gemini_model} (true async REST API)")

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
            # Build conversation context
            contents = self._build_system_instructions(system_instructions)
            
            # Add conversation history
            if conversation_history:
                history_contents = await self._build_history_contents(conversation_history)
                contents.extend(history_contents)
            
            # Add current message
            current_message = await self._build_current_message(user_message, media_urls)
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
                # REST API expects inline_data with base64 encoded data
                parts.append({
                    "inline_data": {
                        "mime_type": image_data["mime_type"],
                        "data": image_data["data"]  # Already base64 encoded
                    }
                })
            except Exception as e:
                if warn_on_error:
                    logger.warning(f"Failed to load image from history: {e}")
                else:
                    logger.error(f"Failed to download image {url}: {e}")
                    raise AIServiceException(f"Failed to process image: {e}") from e

    async def _generate_content(self, contents: list[dict]) -> tuple[str, float]:
        """Generate content using Gemini API - True Async Implementation"""
        logger.info(f"Generating Gemini response with {len(contents)} messages")

        # Build REST API request payload
        url = f"{self.api_base_url}/models/{self.model_name}:generateContent"
        
        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": settings.gemini_max_tokens,
                "temperature": settings.gemini_temperature
            }
        }

        try:
            # True async HTTP request - no thread pool needed!
            response = await self.http_client.post(
                url,
                json=payload,
                headers={
                    "x-goog-api-key": self.api_key,
                    "Content-Type": "application/json"
                },
                timeout=60.0
            )
            response.raise_for_status()
            
            result = response.json()
            
            # Extract response text from API response
            if "candidates" not in result or not result["candidates"]:
                raise AIServiceException("No candidates in Gemini API response")
            
            candidate = result["candidates"][0]
            if "content" not in candidate or "parts" not in candidate["content"]:
                raise AIServiceException("Invalid response structure from Gemini API")
            
            parts = candidate["content"]["parts"]
            if not parts or "text" not in parts[0]:
                raise AIServiceException("No text in Gemini API response")
            
            response_text = parts[0]["text"]
            
            # Get token count from response if available
            usage_metadata = result.get("usageMetadata", {})
            token_count = usage_metadata.get("totalTokenCount", 0)
            
            # Fallback estimation if not provided
            if token_count == 0:
                token_count = len(response_text.split()) * 1.3

            logger.info(f"Generated response: {len(response_text)} chars, ~{int(token_count)} tokens (true async)")

            return response_text, float(token_count)
            
        except httpx.HTTPStatusError as e:
            error_detail = "Unknown error"
            try:
                error_data = e.response.json()
                error_detail = error_data.get("error", {}).get("message", str(e))
            except:
                error_detail = str(e)
            logger.error(f"Gemini API HTTP error: {error_detail}")
            raise AIServiceException(f"Gemini API error: {error_detail}") from e
        except httpx.RequestError as e:
            logger.error(f"Gemini API request error: {e}")
            raise AIServiceException(f"Failed to connect to Gemini API: {e}") from e
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise AIServiceException(f"Failed to generate AI response: {e!s}") from e

    async def transcribe_audio(self, audio_url: str) -> str:
        """
        Transcribe audio file using Gemini - True Async Implementation
        
        Args:
            audio_url: URL to audio file
            
        Returns:
            Transcribed text
        """
        try:
            logger.info(f"Transcribing audio from {audio_url}")

            # Download audio file
            audio_data = await self._download_audio(audio_url)

            # Build contents for transcription
            contents = [
                {
                    "role": "user",
                    "parts": [
                        {"text": "Please transcribe this audio file accurately. Only return the transcription text without any additional commentary."},
                        {
                            "inline_data": {
                                "mime_type": audio_data["mime_type"],
                                "data": audio_data["data"]  # Already base64 encoded
                            }
                        }
                    ]
                }
            ]

            # Use true async REST API call
            url = f"{self.api_base_url}/models/{self.model_name}:generateContent"
            payload = {
                "contents": contents,
                "generationConfig": {
                    "maxOutputTokens": settings.gemini_max_tokens,
                    "temperature": 0.1  # Lower temperature for transcription
                }
            }

            response = await self.http_client.post(
                url,
                json=payload,
                headers={
                    "x-goog-api-key": self.api_key,
                    "Content-Type": "application/json"
                },
                timeout=120.0  # Longer timeout for audio
            )
            response.raise_for_status()
            
            result = response.json()
            
            # Extract transcription text
            if "candidates" not in result or not result["candidates"]:
                raise TranscriptionException("No candidates in Gemini API response")
            
            candidate = result["candidates"][0]
            parts = candidate.get("content", {}).get("parts", [])
            if not parts or "text" not in parts[0]:
                raise TranscriptionException("No text in Gemini API response")
            
            transcription = parts[0]["text"].strip()
            logger.info(f"Audio transcribed: {len(transcription)} characters (true async)")
            
            return transcription
            
        except httpx.HTTPStatusError as e:
            error_detail = "Unknown error"
            try:
                error_data = e.response.json()
                error_detail = error_data.get("error", {}).get("message", str(e))
            except:
                error_detail = str(e)
            logger.error(f"Audio transcription HTTP error: {error_detail}")
            raise TranscriptionException(f"Failed to transcribe audio: {error_detail}") from e
        except Exception as e:
            logger.error(f"Audio transcription error: {e}")
            raise TranscriptionException(f"Failed to transcribe audio: {e!s}") from e

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
            # Encode to base64 for REST API
            return {
                "mime_type": mime_type,
                "data": base64.b64encode(image_data).decode("utf-8")
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
            # Encode to base64 for REST API
            return {
                "mime_type": mime_type,
                "data": base64.b64encode(audio_data).decode("utf-8")
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

            # Use true async REST API call
            contents = [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ]
            
            url = f"{self.api_base_url}/models/{self.model_name}:generateContent"
            payload = {
                "contents": contents,
                "generationConfig": {
                    "maxOutputTokens": settings.gemini_max_tokens,
                    "temperature": settings.gemini_temperature
                }
            }

            response = await self.http_client.post(
                url,
                json=payload,
                headers={
                    "x-goog-api-key": self.api_key,
                    "Content-Type": "application/json"
                },
                timeout=60.0
            )
            response.raise_for_status()
            
            result = response.json()
            
            # Extract response text
            if "candidates" not in result or not result["candidates"]:
                logger.warning("No candidates in Gemini API response for memory extraction")
                return existing_memories or {}
            
            candidate = result["candidates"][0]
            parts = candidate.get("content", {}).get("parts", [])
            if not parts or "text" not in parts[0]:
                logger.warning("No text in Gemini API response for memory extraction")
                return existing_memories or {}
            
            response_text = parts[0]["text"].strip()
            
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
        """Check Gemini API health - True Async Implementation"""
        try:
            start = time.time()

            # Simple test request using true async REST API
            contents = [
                {
                    "role": "user",
                    "parts": [{"text": "Hi"}]
                }
            ]
            
            url = f"{self.api_base_url}/models/{self.model_name}:generateContent"
            payload = {
                "contents": contents,
                "generationConfig": {
                    "maxOutputTokens": 10,
                    "temperature": 0.1
                }
            }

            await self.http_client.post(
                url,
                json=payload,
                headers={
                    "x-goog-api-key": self.api_key,
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )

            latency_ms = int((time.time() - start) * 1000)
            
            return {
                "status": "up",
                "latency_ms": latency_ms
            }
        except Exception as e:
            logger.error(f"Gemini health check failed: {e}")
            return {
                "status": "down",
                "error": str(e)
            }

    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()


# Global Gemini client instance
gemini_client = GeminiClient()


