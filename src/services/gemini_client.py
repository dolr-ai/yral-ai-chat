"""
Google Gemini AI Client
"""
import asyncio
import time
from collections.abc import Callable
from typing import TypeVar

import httpx
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
from src.models.internal import AIProviderHealth
from src.services.base_ai_client import BaseAIClient

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
        "internal error",
        "bad gateway",
        "gateway timeout",
        "timeout",
        "connection",
        "network",
        "overloaded",
        "unavailable",
    ]
    return any(pattern in error_str for pattern in retryable_patterns)


def _gemini_retry_decorator[T](func: Callable[..., T]) -> Callable[..., T]:
    """Retry decorator for Gemini API calls with exponential backoff"""
    return retry(  # type: ignore[return-value]
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type(ConnectionError | TimeoutError | httpx.RequestError)
        | retry_if_exception(_is_retryable_http_error),
        before_sleep=before_sleep_log(logger, "WARNING"),
        after=after_log(logger, "INFO"),
        reraise=True,
    )(func)


class GeminiClient(BaseAIClient):
    """Google Gemini AI client wrapper"""

    def __init__(self):
        """Initialize Gemini client with API key and tokenizer"""
        super().__init__(provider_name="Gemini")
        self.client = genai.Client(api_key=settings.gemini_api_key)
        self.model_name = settings.gemini_model
        logger.debug(f"Gemini client initialized with model: {settings.gemini_model}")

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
            
            # Build conversation history
            contents = []
            if conversation_history:
                history_contents = await self._build_history_contents(conversation_history)
                contents.extend(history_contents)

            # Ensure we don't start with a 'model' role (Gemini requires user first or alternating)
            # If history starts with model (e.g. initial greeting), remove it so we start with user
            if contents and contents[0].get("role") == "model":
                contents.pop(0)
            
            current_message = await self._build_current_message(user_message_str, media_urls)
            contents.append(current_message)

            response_text, token_count = await self._generate_content(contents, system_instructions)
            
            return response_text, int(token_count)

        except AIServiceException:
            raise
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise AIServiceException(f"Failed to generate AI response: {e!s}") from e

    async def _build_history_contents(self, conversation_history: list[Message]) -> list[dict]:
        """Build conversation history contents with parallel image downloading"""

        # 1. Collect all URLs to download
        messages_to_process = conversation_history[-10:]
        all_urls = []
        for msg in messages_to_process:
            if msg.message_type in [MessageType.IMAGE, MessageType.MULTIMODAL] and msg.media_urls:
                all_urls.extend(msg.media_urls[:3])  # Limit 3 images per history message

        # 2. Download all in parallel
        url_blob_map = {}
        if all_urls:
            # unique urls only to save bandwidth
            unique_urls = list(set(all_urls))
            
            async def _download_and_map(url: str):
                try:
                    data = await self._download_image(url)
                    return url, data
                except Exception as e:
                    logger.warning(f"Failed to load image from history {url}: {e}")
                    return url, None

            tasks = [_download_and_map(url) for url in unique_urls]
            results = await asyncio.gather(*tasks)
            
            for url, data in results:
                if data:
                    url_blob_map[url] = data

        # 3. Build contents using downloaded blobs
        contents = []
        for msg in messages_to_process:
            role = "user" if msg.role == MessageRole.USER else "model"
            parts = []

            if msg.content:
                text_content = str(msg.content) if not isinstance(msg.content, str) else msg.content
                parts.append({"text": text_content})

            if msg.message_type in [MessageType.IMAGE, MessageType.MULTIMODAL] and msg.media_urls:
                for url in msg.media_urls[:3]:
                    if url in url_blob_map:
                        parts.append({"inline_data": url_blob_map[url]})

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
        """Add images to message parts (downloading in parallel)"""

        async def _process_url(url: str) -> dict | None:
            try:
                image_data = await self._download_image(url)
                return {"inline_data": image_data}
            except Exception as e:
                if warn_on_error:
                    logger.warning(f"Failed to load image from history: {e}")
                    return None
                logger.error(f"Failed to download image {url}: {e}")
                raise AIServiceException(f"Failed to process image: {e}") from e

        # Download all images in parallel
        tasks = [_process_url(url) for url in image_urls]
        results = await asyncio.gather(*tasks)
        
        # Add successful results to parts
        for result in results:
            if result:
                parts.append(result)

    @_gemini_retry_decorator
    async def _generate_content(self, contents: list[dict], system_instructions: str | None = None) -> tuple[str, int]:
        """Generate content using Gemini API with retry logic"""
        logger.info(f"Generating Gemini response with {len(contents)} messages")

        config_args = {
            "max_output_tokens": settings.gemini_max_tokens,
            "temperature": settings.gemini_temperature
        }
        
        if system_instructions:
            # Append language instruction to system prompt as it was in the manual prompt
            full_instructions = f"{system_instructions}"
            config_args["system_instruction"] = full_instructions

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=types.GenerateContentConfig(**config_args)
        )

        response_text = response.text
        
        if response.candidates and response.candidates[0].finish_reason != types.FinishReason.STOP:
            logger.warning(f"Response finished with reason: {response.candidates[0].finish_reason} (expected STOP)")



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

    @_gemini_retry_decorator
    async def _extract_memories_with_retry(self, prompt: str) -> str:
        """Extract memories with retry logic"""
        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=prompt
        )
        return response.text.strip()

    async def health_check(self) -> AIProviderHealth:
        """Check Gemini API health"""
        try:
            start = time.time()

            await self._health_check_with_retry()

            latency_ms = int((time.time() - start) * 1000)
        except Exception as e:
            logger.error(f"Gemini health check failed: {e}")
            return AIProviderHealth(
                status="down",
                error=str(e),
                latency_ms=None
            )
        else:
            return AIProviderHealth(
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

