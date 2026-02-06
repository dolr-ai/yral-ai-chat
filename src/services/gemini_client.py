"""
Google Gemini AI Client
"""
import asyncio
import mimetypes
import time
from collections.abc import Callable

import httpx
from google import genai
from google.genai import types
from loguru import logger
from pydantic import validate_call
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
from src.models.internal import AIProviderHealth, AIResponse, LLMGenerateParams
from src.services.base_ai_client import BaseAIClient


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

    @validate_call
    async def generate_response(self, params: LLMGenerateParams) -> AIResponse:
        """
        Generate AI response

        Args:
            params: LLM generation parameters
        """
        try:
            timings: dict[str, float] = {}
            user_message_str = str(params.user_message) if not isinstance(params.user_message, str) else params.user_message

            # Build contents for Gemini API (Native Google GenAI SDK)
            t0 = time.time()
            contents = await self._build_contents(
                user_message_str,
                params.conversation_history,  # type: ignore[arg-type]
                params.media_urls
            )
            timings["build_contents"] = time.time() - t0

            t0 = time.time()
            response_text, token_count = await self._generate_content(
                contents,
                params.system_instructions,
                params.max_tokens,
                response_mime_type=params.response_mime_type,
                response_schema=params.response_schema
            )
            timings["gemini_api_call"] = time.time() - t0

            timing_str = ", ".join(f"{k}={v*1000:.0f}ms" for k, v in timings.items())
            total_time = sum(timings.values())
            if total_time > 5:
                logger.warning(f"SLOW Gemini generate_response: {timing_str}")
            else:
                logger.debug(f"Gemini generate_response timings: {timing_str}")

            return AIResponse(text=response_text, token_count=int(token_count))

        except AIServiceException:
            raise
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise AIServiceException(f"Failed to generate AI response: {e!s}") from e

    def _get_mime_type_from_url(self, url: str) -> str:
        """Infer MIME type from URL using mimetypes library"""
        url_path = url.split("?")[0]  # Remove query params
        mime_type, _ = mimetypes.guess_type(url_path)
        return mime_type or "image/jpeg"

    def _get_media_part(self, url: str) -> dict:
        """Helper to create a media part with file_uri"""
        return {
            "file_data": {
                "file_uri": url,
                "mime_type": self._get_mime_type_from_url(url)
            }
        }

    async def _build_contents(
        self, user_message: str, conversation_history: list[Message] | None, media_urls: list[str] | None
    ) -> list[dict]:
        """Build full contents for Gemini API"""
        contents = []

        # 1. Build conversation history
        if conversation_history:
            contents.extend(self._build_history_contents(conversation_history))

        # 2. Ensure we don't start with a 'model' role (Gemini requirement)
        if contents and contents[0].get("role") == "model":
            contents.pop(0)

        # 3. Add current message
        current_parts = self._build_current_parts(user_message, media_urls)
        contents.append({"role": "user", "parts": current_parts})
        return contents

    def _build_history_contents(self, history: list[Message]) -> list[dict]:
        """Build contents from conversation history"""
        history_contents = []
        for msg in history[-10:]:  # Last 10 messages for context
            role = "user" if msg.role == MessageRole.USER else "model"
            parts = []

            if msg.content:
                text_content = str(msg.content) if not isinstance(msg.content, str) else msg.content
                parts.append({"text": text_content})

            if msg.message_type in [MessageType.IMAGE, MessageType.MULTIMODAL] and msg.media_urls:
                for url in msg.media_urls[:3]:
                    if url and url.startswith(("http://", "https://")):
                        parts.append(self._get_media_part(url))

            if parts:
                history_contents.append({"role": role, "parts": parts})
        return history_contents

    def _build_current_parts(self, user_message: str, media_urls: list[str] | None) -> list[dict]:
        """Build parts for the current message"""
        parts = []
        if user_message:
            text_content = str(user_message) if not isinstance(user_message, str) else user_message
            parts.append({"text": text_content})

        if media_urls:
            for url in media_urls[:5]:
                if url and url.startswith(("http://", "https://")):
                    parts.append(self._get_media_part(url))
        return parts

    @_gemini_retry_decorator
    async def _generate_content(
        self,
        contents: list[dict],
        system_instructions: str | None = None,
        max_tokens: int | None = None,
        response_mime_type: str | None = None,
        response_schema: dict[str, object] | None = None,
    ) -> tuple[str, int]:
        """Generate content using Gemini API with retry logic"""
        logger.info(f"Generating Gemini response with {len(contents)} messages")

        config_args = {
            "max_output_tokens": max_tokens or settings.gemini_max_tokens,
            "temperature": settings.gemini_temperature,
        }

        if response_mime_type:
            config_args["response_mime_type"] = response_mime_type
        if response_schema:
            config_args["response_schema"] = self._prepare_schema(response_schema, root_schema=response_schema)
        if system_instructions:
            # Append language instruction to system prompt as it was in the manual prompt
            full_instructions = f"{system_instructions}"
            config_args["system_instruction"] = full_instructions

        try:
            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(**config_args)
                ),
                timeout=settings.gemini_timeout
            )
        except TimeoutError:
            logger.error(f"Gemini API call timed out after {settings.gemini_timeout} seconds")
            raise AIServiceException("Gemini API call timed out") from None

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

    def _prepare_schema(self, schema: dict[str, object], root_schema: dict[str, object] | None = None) -> dict[str, object]:
        """
        Recursively fix Pydantic JSON schema to be compatible with Google GenAI SDK.
        - Resolves and inlines '$ref'
        - Handles 'anyOf' with 'null' type by setting 'nullable=True'
        - Removes 'additionalProperties' to satisfy strict API requirements
        - Removes 'title' and other metadata fields
        """
        if not isinstance(schema, dict):
            return schema

        # 1. Resolve $ref
        if "$ref" in schema:
            return self._resolve_ref(schema, root_schema)

        # 2. Handle anyOf for nullable fields
        if "anyOf" in schema:
            return self._handle_any_of(schema, root_schema)

        # 3. Process fields
        new_schema = {}
        for k, v in schema.items():
            if k in ["title", "definitions", "$defs", "additionalProperties", "additional_properties"]:
                continue

            if isinstance(v, dict):
                new_schema[k] = self._prepare_schema(v, root_schema)
            elif isinstance(v, list):
                new_schema[k] = [
                    self._prepare_schema(item, root_schema) if isinstance(item, dict) else item
                    for item in v
                ]
            else:
                new_schema[k] = v

        return new_schema

    def _resolve_ref(self, schema: dict[str, object], root_schema: dict[str, object] | None) -> dict[str, object]:
        """Resolve $ref by inlining from root_schema"""
        ref_path = str(schema["$ref"])
        if ref_path.startswith("#/$defs/") and root_schema and "$defs" in root_schema:
            def_name = ref_path.split("/")[-1]
            defs = root_schema.get("$defs", {})
            if isinstance(defs, dict) and def_name in defs:
                resolved = defs[def_name]
                if isinstance(resolved, dict):
                    return self._prepare_schema(resolved, root_schema)
        return schema

    def _handle_any_of(self, schema: dict[str, object], root_schema: dict[str, object] | None) -> dict[str, object]:
        """Handle anyOf for nullable fields or return first option"""
        any_of = schema["anyOf"]
        if isinstance(any_of, list):
            # Filter out null type and set nullable
            non_null_types = [t for t in any_of if isinstance(t, dict) and t.get("type") != "null"]
            if len(non_null_types) < len(any_of):
                target_schema = non_null_types[0].copy() if non_null_types else {"type": "string"}
                target_schema["nullable"] = True
                return self._prepare_schema(target_schema, root_schema)
            return self._prepare_schema(any_of[0].copy(), root_schema)
        return schema

    async def transcribe_audio(self, audio_url: str) -> str:
        """
        Transcribe audio file using Gemini

        Args:
            audio_url: URL to audio file

        Returns:
            Transcribed text
        """
        try:
            logger.info(f"Transcribing audio from {audio_url} using Gemini link")

            prompt = "Please transcribe this audio file accurately. Only return the transcription text without any additional commentary."

            response = await self._transcribe_audio_with_link(audio_url, prompt)

            transcription = response.text.strip()
            logger.info(f"Audio transcribed: {len(transcription)} characters")
            return transcription
        except Exception as e:
            logger.error(f"Audio transcription error: {e}")
            raise TranscriptionException(f"Failed to transcribe audio: {e!s}") from e

    @_gemini_retry_decorator
    async def _transcribe_audio_with_link(self, audio_url: str, prompt: str) -> types.GenerateContentResponse:
        """Transcribe audio with retry logic using direct link"""
        return await self.client.aio.models.generate_content(
            model=self.model_name, contents=[prompt, self._get_media_part(audio_url)]
        )

    @_gemini_retry_decorator
    async def _extract_memories_with_retry(self, prompt: str) -> str:
        """Extract memories with retry logic"""
        response = await self.client.aio.models.generate_content(model=self.model_name, contents=prompt)
        return response.text.strip()

    async def health_check(self) -> AIProviderHealth:
        """Check Gemini API health"""
        try:
            start = time.time()

            await self._health_check_with_retry()

            latency_ms = int((time.time() - start) * 1000)
        except Exception as e:
            logger.error(f"Gemini health check failed: {e}")
            return AIProviderHealth(status="down", error=str(e), latency_ms=None)
        else:
            return AIProviderHealth(status="up", latency_ms=latency_ms, error=None)

    @_gemini_retry_decorator
    async def _health_check_with_retry(self) -> None:
        """Health check with retry logic"""
        await self.client.aio.models.generate_content(model=self.model_name, contents="Hi")

    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()
