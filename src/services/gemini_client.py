"""
Google Gemini AI Client
"""
import json
import time
from collections.abc import Callable
from typing import TypeVar

import httpx
import tiktoken
from google import genai
from google.genai import types
from loguru import logger
from tenacity import (
    after_log,
    before_sleep_log,
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import settings
from src.core.exceptions import AIServiceException, TranscriptionException
from src.models.entities import Message, MessageRole, MessageType
from src.models.internal import GeminiHealth

T = TypeVar("T")


def _is_retryable_http_error(exception: Exception) -> bool:
    """Check if an exception is a retryable HTTP error"""
    if isinstance(exception, httpx.HTTPStatusError):
        status_code = exception.response.status_code
        return status_code == 429 or (500 <= status_code < 600)
    
    if isinstance(exception, httpx.RequestError | httpx.TimeoutException | httpx.ConnectError):
        return True
    
    # google-genai library may raise exceptions with status_code attributes
    if hasattr(exception, "status_code"):
        status_code = exception.status_code
        return status_code == 429 or (500 <= status_code < 600)
    
    error_str = str(exception).lower()
    retryable_patterns = [
        "rate limit",
        "too many requests",
        "service unavailable",
        "internal server error",
        "bad gateway",
        "gateway timeout",
        "timeout",
        "connection",
        "network",
    ]
    return any(pattern in error_str for pattern in retryable_patterns)


def _gemini_retry_decorator[T](func: Callable[..., T]) -> Callable[..., T]:
    """Retry decorator for Gemini API calls with exponential backoff"""
    return retry(  # type: ignore[return-value]
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception_type(ConnectionError | TimeoutError | httpx.RequestError)
        | retry_if_exception(_is_retryable_http_error),
        before_sleep=before_sleep_log(logger, "WARNING"),
        after=after_log(logger, "INFO"),
        reraise=True,
    )(func)


class GeminiClient:
    """Google Gemini AI client wrapper"""

    def __init__(self):
        """Initialize Gemini client with API key and tokenizer"""
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model_name = settings.gemini_model
        self.http_client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
            }
        )
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"Failed to initialize tiktoken, falling back to approximate counting: {e}")
            self.tokenizer = None
        logger.info(f"Gemini client initialized with model: {settings.gemini_model}")

    async def generate_response(
        self,
        user_message: str,
        system_instructions: str,
        conversation_history: list[Message] | None = None,
        media_urls: list[str] | None = None
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
            user_message_str = str(user_message) if not isinstance(user_message, str) else user_message
            
            contents = self._build_system_instructions(system_instructions)
            
            if conversation_history:
                history_contents = await self._build_history_contents(conversation_history)
                contents.extend(history_contents)
            
            current_message = await self._build_current_message(user_message_str, media_urls)
            contents.append(current_message)

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

            if msg.content:
                text_content = str(msg.content) if not isinstance(msg.content, str) else msg.content
                parts.append({"text": text_content})

            if msg.message_type in [MessageType.IMAGE, MessageType.MULTIMODAL]:
                await self._add_images_to_parts(msg.media_urls[:3], parts, warn_on_error=True)

            if parts:
                contents.append({"role": role, "parts": parts})
        
        return contents

    async def _build_current_message(self, user_message: str, media_urls: list[str] | None) -> dict:
        """Build current user message with optional images"""
        current_parts = []

        if user_message:
            text_content = str(user_message) if not isinstance(user_message, str) else user_message
            current_parts.append({"text": text_content})

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

    @_gemini_retry_decorator
    async def _generate_content(self, contents: list[dict]) -> tuple[str, int]:
        """Generate content using Gemini API with retry logic"""
        logger.info(f"Generating Gemini response with {len(contents)} messages")

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=types.GenerateContentConfig(
            max_output_tokens=settings.gemini_max_tokens,
            temperature=settings.gemini_temperature
        )
        )

        response_text = response.text
        
        if response.candidates and response.candidates[0].finish_reason != 1:
            logger.warning(f"Response finished with reason: {response.candidates[0].finish_reason} (not STOP)")

        # Use tiktoken for accurate token counting
        if self.tokenizer:
            token_count = len(self.tokenizer.encode(response_text))
        else:
            token_count = int(len(response_text.split()) * 1.3)
            logger.warning("Using approximate token counting (tiktoken not available)")

        logger.info(f"Generated response: {len(response_text)} chars, {token_count} tokens")

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

            audio_data = await self._download_audio(audio_url)

            transcription = await self._transcribe_audio_with_retry(audio_data)
            logger.info(f"Audio transcribed: {len(transcription)} characters")
            return transcription
        except Exception as e:
            logger.error(f"Audio transcription error: {e}")
            raise TranscriptionException(f"Failed to transcribe audio: {e!s}") from e

    @_gemini_retry_decorator
    async def _transcribe_audio_with_retry(self, audio_data: dict[str, object]) -> str:
        """Transcribe audio with retry logic"""
        prompt = "Please transcribe this audio file accurately. Only return the transcription text without any additional commentary."

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=[
                prompt,
                {"inline_data": audio_data}
            ]
        )

        return response.text.strip()

    async def _download_image(self, url: str) -> dict[str, object]:
        """Download and encode image for Gemini"""
        try:
            logger.info(f"Downloading image from URL: {url}")
            response = await self.http_client.get(url)
            if response.status_code != 200:
                logger.error(
                    f"Failed to download image from {url}. Status: {response.status_code}. "
                    f"Request headers: {dict(response.request.headers)}. "
                    f"Response headers: {dict(response.headers)}"
                )
            response.raise_for_status()

            image_data = response.content
            mime_type = response.headers.get("content-type", "image/jpeg")
            logger.info(f"Successfully downloaded image ({len(image_data)} bytes, type: {mime_type})")
        except Exception as e:
            logger.error(f"Error in _download_image for {url}: {str(e)}")
            raise
        else:
            return {
                "mime_type": mime_type,
                "data": image_data
            }

    async def _download_audio(self, url: str) -> dict[str, object]:
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

    @_gemini_retry_decorator
    async def _extract_memories_with_retry(self, prompt: str) -> str:
        """Extract memories with retry logic"""
        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=prompt
        )
        return response.text.strip()

    def _extract_json_from_response(self, response_text: str) -> dict:
        """Extract JSON object from response text, handling nested braces"""
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
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
                            return json.loads(json_str)
                        except json.JSONDecodeError:
                            continue
            return {}

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

            response_text = await self._extract_memories_with_retry(prompt)
            
            extracted = self._extract_json_from_response(response_text)
            
            if extracted and isinstance(extracted, dict):
                existing_memories.update(extracted)
                logger.info(f"Extracted {len(extracted)} new/updated memories")
            else:
                logger.debug("No new memories extracted from conversation")
                
            return existing_memories
            
        except Exception as e:
            logger.error(f"Memory extraction failed: {e}")
            return existing_memories or {}

    async def health_check(self) -> GeminiHealth:
        """Check Gemini API health"""
        try:
            start = time.time()

            await self._health_check_with_retry()

            latency_ms = int((time.time() - start) * 1000)
        except Exception as e:
            logger.error(f"Gemini health check failed: {e}")
            return GeminiHealth(
                status="down",
                error=str(e),
                latency_ms=None
            )
        else:
            return GeminiHealth(
                status="up",
                latency_ms=latency_ms,
                error=None
            )

    @_gemini_retry_decorator
    async def _health_check_with_retry(self) -> None:
        """Health check with retry logic"""
        await self.client.aio.models.generate_content(
            model=self.model_name,
            contents="Hi"
        )

    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()

