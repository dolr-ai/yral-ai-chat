"""
Base AI Client
Shared logic for AI provider clients
"""
import asyncio
import json
import time
from abc import ABC, abstractmethod
from typing import Any, TypeVar

import httpx
import tiktoken
from loguru import logger

from src.config import settings
from src.core.exceptions import AIServiceException
from src.models.entities import Message
from src.models.internal import AIProviderHealth

T = TypeVar("T")


class BaseAIClient(ABC):
    """Base class for AI provider clients"""

    def __init__(self, provider_name: str):
        """Initialize base AI client"""
        self.provider_name = provider_name
        self.http_client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
            }
        )
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"Failed to initialize tiktoken for {self.provider_name}, falling back to approximate counting: {e}")
            self.tokenizer = None

    @abstractmethod
    async def generate_response(
        self,
        user_message: str,
        system_instructions: str,
        conversation_history: list[Message] | None = None,
        media_urls: list[str] | None = None
    ) -> tuple[str, int]:
        """Generate AI response"""

    @abstractmethod
    async def health_check(self) -> AIProviderHealth:
        """Check API health"""

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

    async def _download_image(self, url: str) -> dict[str, Any]:
        """Download and encode image with timeout"""
        timeout = settings.media_download_timeout
        t0 = time.time()
        try:
            logger.debug(f"Downloading image from URL: {url[:100]}...")
            response = await asyncio.wait_for(
                self.http_client.get(url),
                timeout=timeout
            )
            response.raise_for_status()

            image_data = response.content
            mime_type = response.headers.get("content-type", "image/jpeg")
            elapsed = time.time() - t0
            if elapsed > 2:
                logger.warning(f"Slow image download ({elapsed:.1f}s): {url[:100]}")
            return {
                "mime_type": mime_type,
                "data": image_data
            }
        except TimeoutError:
            elapsed = time.time() - t0
            logger.error(f"Image download timeout ({elapsed:.1f}s): {url[:100]}")
            raise AIServiceException(f"Image download timed out after {timeout}s") from None
        except Exception as e:
            elapsed = time.time() - t0
            logger.error(f"Failed to download image ({elapsed:.1f}s) from {url[:100]}: {e}")
            raise AIServiceException(f"Failed to process image: {e}") from e

    async def _download_images_batch(
        self,
        urls: list[str],
        warn_on_error: bool = False
    ) -> list[dict[str, Any] | None]:
        """
        Download multiple images in parallel.
        Returns list of image data dicts (or None for failed downloads if warn_on_error=True).
        """
        if not urls:
            return []

        async def download_one(url: str) -> dict[str, Any] | None:
            try:
                return await self._download_image(url)
            except Exception as e:
                if warn_on_error:
                    logger.warning(f"Failed to load image from history: {e}")
                    return None
                raise

        t0 = time.time()
        results = await asyncio.gather(*[download_one(u) for u in urls], return_exceptions=False)
        elapsed = time.time() - t0
        success_count = sum(1 for r in results if r is not None)
        logger.info(f"Downloaded {success_count}/{len(urls)} images in {elapsed:.1f}s (parallel)")

        return results

    async def _download_audio(self, url: str) -> dict[str, Any]:
        """Download and encode audio with timeout"""
        timeout = settings.media_download_timeout
        t0 = time.time()
        try:
            response = await asyncio.wait_for(
                self.http_client.get(url),
                timeout=timeout
            )
            response.raise_for_status()

            audio_data = response.content
            mime_type = response.headers.get("content-type", "audio/mpeg")
            elapsed = time.time() - t0
            if elapsed > 2:
                logger.warning(f"Slow audio download ({elapsed:.1f}s): {url[:100]}")
            return {
                "mime_type": mime_type,
                "data": audio_data
            }
        except TimeoutError:
            elapsed = time.time() - t0
            logger.error(f"Audio download timeout ({elapsed:.1f}s): {url[:100]}")
            raise AIServiceException(f"Audio download timed out after {timeout}s") from None
        except Exception as e:
            elapsed = time.time() - t0
            logger.error(f"Failed to download audio ({elapsed:.1f}s) {url[:100]}: {e}")
            raise AIServiceException(f"Failed to process audio: {e}") from e

    async def extract_memories(
        self,
        user_message: str,
        assistant_response: str,
        existing_memories: dict[str, str] | None = None
    ) -> dict[str, str]:
        """Extract memories from conversation using the provider's generate_response"""
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

            # We use the provider's generate_response to extract memories
            response_text, _ = await self.generate_response(
                user_message=prompt,
                system_instructions="You are a factual information extractor. Output ONLY raw JSON."
            )
            
            extracted = self._extract_json_from_response(response_text)
            
            if extracted and isinstance(extracted, dict):
                existing_memories.update(extracted)
                logger.info(f"[{self.provider_name}] Extracted {len(extracted)} new/updated memories")
            
            return existing_memories
            
        except Exception as e:
            logger.error(f"[{self.provider_name}] Memory extraction failed: {e}")
            return existing_memories or {}

    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()
