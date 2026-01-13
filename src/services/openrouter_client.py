"""
OpenRouter AI Client - OpenAI-compatible API wrapper for OpenRouter
Used for NSFW content handling via alternative LLM providers
"""
import base64
import time
from collections.abc import Callable
from typing import TypeVar

import httpx
from loguru import logger
from tenacity import (
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


def _is_retryable_http_error(exception: BaseException) -> bool:  # type: ignore[name-defined]
    """Check if an exception is a retryable HTTP error"""
    if isinstance(exception, httpx.HTTPStatusError):
        status_code = exception.response.status_code
        return status_code == 429 or (500 <= status_code < 600)

    if isinstance(exception, httpx.RequestError | httpx.TimeoutException | httpx.ConnectError):
        return True

    if hasattr(exception, "status_code"):
        status_code = getattr(exception, "status_code", None)
        if isinstance(status_code, int):
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


def _openrouter_retry_decorator[T](func: Callable[..., T]) -> Callable[..., T]:
    """Retry decorator for OpenRouter API calls with exponential backoff"""
    return retry(  # type: ignore[return-value]
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, httpx.RequestError))
        | retry_if_exception(_is_retryable_http_error),
        reraise=True,
    )(func)


class OpenRouterClient(BaseAIClient):
    """OpenRouter AI client wrapper - OpenAI-compatible API"""

    def __init__(self):
        """Initialize OpenRouter client"""
        super().__init__(provider_name="OpenRouter")
        if not settings.openrouter_api_key:
            logger.warning("OpenRouter API key not configured - NSFW bots will not work")
        
        self.api_key = settings.openrouter_api_key
        self.model_name = settings.openrouter_model
        self.max_tokens = settings.openrouter_max_tokens
        self.temperature = settings.openrouter_temperature
        self.api_base = "https://openrouter.ai/api/v1"
        
        # Override BaseAIClient's http_client if needed or just update headers
        self.http_client.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://yral.com",
            "X-Title": "Yral AI Chat",
        })
        self.http_client.timeout = settings.openrouter_timeout
        
        logger.info(f"OpenRouter client initialized with model: {self.model_name}")

    async def generate_response(
        self,
        user_message: str,
        system_instructions: str,
        conversation_history: list[Message] | None = None,
        media_urls: list[str] | None = None
    ) -> tuple[str, int]:
        """
        Generate AI response using OpenRouter
        
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
            
            # Build messages for OpenAI-compatible API
            messages = await self._build_messages(
                user_message_str, system_instructions, conversation_history, media_urls
            )
            
            response_text, token_count = await self._generate_content(messages)
            return response_text, int(token_count)

        except AIServiceException:
            raise
        except Exception as e:
            logger.error(f"OpenRouter API error: {e}")
            raise AIServiceException(f"Failed to generate AI response: {e!s}") from e

    async def _build_image_content(self, image_url: str) -> dict | None:
        """Build image content dict for OpenAI-compatible API"""
        try:
            # Download image and convert to base64
            response = await self.http_client.get(image_url)
            response.raise_for_status()
            
            image_data = response.content
            mime_type = response.headers.get("content-type", "image/jpeg")
            
            # Convert to base64
            base64_image = base64.standard_b64encode(image_data).decode("utf-8")
            
            return {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{base64_image}"
                }
            }
        except Exception as e:
            logger.error(f"Failed to process image: {e}")
            raise

    @_openrouter_retry_decorator
    async def _generate_content(self, messages: list[dict]) -> tuple[str, int]:
        """Generate content using OpenRouter API with retry logic"""
        logger.info(f"Generating OpenRouter response with {len(messages)} messages")

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        response = await self.http_client.post(
            f"{self.api_base}/chat/completions",
            json=payload
        )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenRouter API error: {e.response.status_code} - {e.response.text}")
            raise

        data = response.json()
        response_text = data["choices"][0]["message"]["content"].strip()

        # Token counting
        if self.tokenizer:
            token_count = len(self.tokenizer.encode(response_text))
        else:
            # Estimate: ~1.3 words per token
            token_count = int(len(response_text.split()) * 1.3)
            logger.warning("Using approximate token counting for OpenRouter (tiktoken not available)")

        logger.info(f"Generated response: {len(response_text)} chars, {token_count} tokens")

        return response_text, token_count

    async def transcribe_audio(self, audio_url: str) -> str:
        """
        Transcribe audio file using OpenRouter
        
        Args:
            audio_url: URL to audio file
            
        Returns:
            Transcribed text
        """
        try:
            logger.info(f"Transcribing audio from {audio_url} using OpenRouter")

            audio_data = await self._download_audio(audio_url)
            transcription = await self._transcribe_audio_with_retry(audio_data)
            logger.info(f"Audio transcribed: {len(transcription)} characters")
            return transcription
        except Exception as e:
            logger.error(f"Audio transcription error: {e}")
            raise TranscriptionException(f"Failed to transcribe audio: {e!s}") from e

    @_openrouter_retry_decorator
    async def _transcribe_audio_with_retry(self, audio_data: dict[str, object]) -> str:
        """Transcribe audio with retry logic"""
        prompt = "Please transcribe this audio file accurately. Only return the transcription text without any additional commentary."

        # Ensure data is bytes
        audio_bytes = audio_data["data"] if isinstance(audio_data["data"], bytes) else bytes(audio_data["data"])  # type: ignore[arg-type]
        base64_audio = base64.standard_b64encode(audio_bytes).decode("utf-8")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{audio_data['mime_type']};base64,{base64_audio}"
                        }
                    }
                ]
            }
        ]

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": 512,
        }

        response = await self.http_client.post(
            f"{self.api_base}/chat/completions",
            json=payload
        )

        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()


    async def health_check(self) -> AIProviderHealth:
        """Check OpenRouter API health"""
        try:
            start = time.time()
            await self._health_check_with_retry()
            latency_ms = int((time.time() - start) * 1000)
        except Exception as e:
            logger.error(f"OpenRouter health check failed: {e}")
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

    @_openrouter_retry_decorator
    async def _health_check_with_retry(self) -> None:
        """Health check with retry logic"""
        messages = [{"role": "user", "content": "Hi"}]
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": 10,
        }

        response = await self.http_client.post(
            f"{self.api_base}/chat/completions",
            json=payload
        )
        response.raise_for_status()

    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()

    async def _build_messages(
        self,
        user_message: str,
        system_instructions: str,
        conversation_history: list[Message] | None,
        media_urls: list[str] | None
    ) -> list[dict]:
        """Build messages list for OpenRouter/OpenAI API"""
        messages = []
        
        # Add system instructions
        messages.append({
            "role": "system",
            "content": f"{system_instructions}. Lastly, always answer in the same language as the user's message."
        })
        
        # Add conversation history
        if conversation_history:
            # consistency with Gemini: ensure we start with user message if possible
            # by dropping valid initial assistant greeting if it's the first message
            start_index = 0
            if conversation_history[-10:] and conversation_history[-10:][0].role == MessageRole.ASSISTANT:
                start_index = 1

            for msg in conversation_history[-10:][start_index:]:  # Last 10 messages for context
                role = "user" if msg.role == MessageRole.USER else "assistant"
                content = msg.content or ""
                
                # Build content with potential images
                if msg.message_type in [MessageType.IMAGE, MessageType.MULTIMODAL] and msg.media_urls:
                    content_list = [{"type": "text", "text": content}] if content else []
                    for image_url in msg.media_urls[:3]:
                        try:
                            image_content = await self._build_image_content(image_url)
                            if image_content:
                                content_list.append(image_content)
                        except Exception as e:
                            logger.warning(f"Failed to load image from history: {e}")
                    if content_list:
                        messages.append({"role": role, "content": content_list})
                else:
                    messages.append({"role": role, "content": content})
        
        # Add current message with optional images
        current_content = [{"type": "text", "text": user_message}]
        if media_urls:
            for image_url in media_urls[:5]:
                try:
                    image_content = await self._build_image_content(image_url)
                    if image_content:
                        current_content.append(image_content)
                except Exception as e:
                    logger.error(f"Failed to download image {image_url}: {e}")
                    raise AIServiceException(f"Failed to process image: {e}") from e
        
        messages.append({"role": "user", "content": current_content if len(current_content) > 1 else user_message})
        
        return messages
