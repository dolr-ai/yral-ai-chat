"""
Google Gemini AI Client - True Async Implementation
"""
import base64
import json
import time
from typing import Any

import httpx
import tiktoken
from loguru import logger

from src.config import settings
from src.core.exceptions import AIServiceException, TranscriptionException
from src.models.entities import Message, MessageRole


class GeminiClient:
    """Google Gemini AI client wrapper"""

    def __init__(self):
        """Initialize Gemini client with true async REST API"""
        self.http_client = httpx.AsyncClient(timeout=60.0)
        self.api_base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.api_key = settings.gemini_api_key
        self.model_name = settings.gemini_model
        # Initialize tiktoken encoder for token estimation
        # Using cl100k_base encoding (used by GPT-4, good general-purpose estimate)
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"Failed to initialize tiktoken: {e}. Token estimation may be less accurate.")
            self.tokenizer = None
        logger.info(f"Gemini client initialized with model: {settings.gemini_model} (true async REST API)")

    async def generate_response(
        self,
        user_message: str,
        system_instructions: str,
        conversation_history: list[Message] | None = None,
        media_urls: list[str] | None = None
    ) -> tuple[str, int]:
        """
        Generate AI response - uses last 5 messages for context, dynamically reduces if input too large
        
        Args:
            user_message: Current user message
            system_instructions: AI personality instructions
            conversation_history: Previous messages for context (uses last 5, reduces if needed)
            media_urls: Optional image URLs for multimodal input
            
        Returns:
            Tuple of (response_text, token_count)
        """
        try:
            # Ensure user_message is a string
            user_message_str = str(user_message) if not isinstance(user_message, str) else user_message
            
            # Build current message first
            current_message = await self._build_current_message(user_message_str, media_urls)
            
            # Estimate tokens for system instructions and current message
            max_output_tokens = settings.gemini_max_tokens
            
            # CRITICAL: With maxOutputTokens=200, we need to balance input vs output carefully
            # Strategy: Reserve minimum 100 tokens for output, use rest for input (max 100 tokens for input)
            # This ensures we always have enough output space to prevent truncation
            min_output_reserved = min(100, int(max_output_tokens * 0.5))  # Reserve at least 50% for output
            max_input_tokens = max_output_tokens - min_output_reserved  # Use remaining for input (100 tokens when maxOutput=200)
            
            current_message_str = json.dumps(current_message, ensure_ascii=False)
            current_tokens = self._estimate_tokens(current_message_str)
            
            # Estimate system instructions first
            system_tokens_estimated = self._estimate_tokens(system_instructions) if system_instructions else 0
            
            # Calculate what we can afford for system instructions
            # Reserve: current message + overhead (30 tokens) + small buffer for history (10 tokens)
            reserved_base = current_tokens + 30 + 10
            available_for_system = max(0, max_input_tokens - reserved_base)
            
            # TRUNCATE system instructions if they exceed what we can afford
            original_system_instructions = system_instructions
            if system_instructions and system_tokens_estimated > available_for_system and available_for_system > 0:
                # Use binary search to find optimal truncation point
                low, high = 0, len(system_instructions)
                best_truncated = system_instructions[:available_for_system * 2] + "..."  # Initial guess
                best_tokens = self._estimate_tokens(best_truncated)
                
                for _ in range(15):  # Max 15 iterations for binary search
                    mid = (low + high) // 2
                    test_truncated = system_instructions[:mid] + "..."
                    test_tokens = self._estimate_tokens(test_truncated)
                    if test_tokens <= available_for_system:
                        if test_tokens > best_tokens:  # Keep the longest version that fits
                            best_truncated = test_truncated
                            best_tokens = test_tokens
                        low = mid + 1
                    else:
                        high = mid - 1
                    if low > high:
                        break
                
                system_instructions = best_truncated
                logger.warning(
                    f"TRUNCATED system instructions: {system_tokens_estimated} tokens -> "
                    f"{self._estimate_tokens(system_instructions)} tokens "
                    f"(budget: {available_for_system} tokens, original: {len(original_system_instructions)} chars, "
                    f"truncated: {len(system_instructions)} chars)"
                )
            elif system_instructions and available_for_system <= 0:
                # No room for system instructions at all - use minimal placeholder
                system_instructions = "You are a helpful assistant."
                logger.error(
                    f"System instructions too large ({system_tokens_estimated} tokens) - no budget available. "
                    f"Using minimal placeholder. Consider reducing system instructions or increasing maxOutputTokens."
                )
            
            system_tokens = self._estimate_tokens(system_instructions) if system_instructions else 0
            reserved_tokens = system_tokens + current_tokens + 30
            available_for_history = max(0, max_input_tokens - reserved_tokens)
            
            logger.info(
                f"Token budget: maxOutput={max_output_tokens}, maxInput={max_input_tokens}, "
                f"system={system_tokens}, current={current_tokens}, available_for_history={available_for_history}"
            )
            
            # Build conversation context - dynamically select messages based on token budget
            contents = []
            
            # Add conversation history (dynamically limited by token budget)
            if conversation_history and available_for_history > 10:  # Need at least 10 tokens for any history
                history_contents = await self._build_history_contents(
                    conversation_history,
                    max_tokens=available_for_history
                )
                contents.extend(history_contents)
                logger.info(f"Added {len(history_contents)} messages from history (budget: {available_for_history} tokens)")
            elif conversation_history:
                logger.warning(
                    f"No token budget for history (available={available_for_history}, reserved={reserved_tokens}, "
                    f"maxInput={max_input_tokens}). Using only current message to prevent truncation."
                )
            
            # Add current message
            contents.append(current_message)

            # Generate response with systemInstruction parameter (more token-efficient)
            response_text, token_count = await self._generate_content(contents, system_instructions)
            
            return response_text, int(token_count)

        except AIServiceException:
            raise
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise AIServiceException(f"Failed to generate AI response: {e!s}") from e

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count using tiktoken for more accurate counting
        
        Args:
            text: Text to estimate tokens for
            
        Returns:
            Estimated number of tokens
        """
        if not text:
            return 0
        
        if self.tokenizer:
            try:
                return len(self.tokenizer.encode(str(text)))
            except Exception as e:
                logger.warning(f"tiktoken encoding failed: {e}, falling back to character-based estimate")
        
        # Fallback: conservative character-based estimate (~3 chars per token)
        return max(1, len(str(text)) // 3)

    def _build_system_instructions(self, system_instructions: str) -> list[dict]:
        """Build system instruction messages"""
        # System instructions are already very long, so we add minimal wrapper text
        return [
            {
                "role": "user",
                "parts": [{"text": f"{system_instructions}\n\nAlways answer in the same language as the user's message."}]
            },
            {
                "role": "model",
                "parts": [{"text": "Understood."}]
            }
        ]

    async def _build_history_contents(
        self,
        conversation_history: list[Message],
        max_tokens: int | None = None
    ) -> list[dict]:
        """
        Build conversation history contents - uses last 5 messages, dynamically reduces if needed

        Args:
            conversation_history: List of previous messages
            max_tokens: Maximum tokens available for history (None = use last 5 messages)

        Returns:
            List of message dicts for API
        """
        contents = []
        
        # Start with last 5 messages as requested by user
        history_to_use = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
        
        # If we have a token budget, dynamically select messages that fit
        if max_tokens is not None and max_tokens > 0:
            selected_messages: list[Message] = []
            total_tokens = 0
            
            # Select messages from most recent, staying within token budget
            for msg in reversed(history_to_use):
                if msg.content:
                    text_content = str(msg.content) if not isinstance(msg.content, str) else msg.content
                    # Truncate to 100 chars per message to save tokens
                    if len(text_content) > 100:
                        text_content = text_content[:100] + "..."
                    
                    # Estimate tokens for this message
                    msg_dict = {"role": "user" if msg.role == MessageRole.USER else "model", "parts": [{"text": text_content}]}
                    msg_str = json.dumps(msg_dict, ensure_ascii=False)
                    msg_tokens = self._estimate_tokens(msg_str)
                    
                    if total_tokens + msg_tokens <= max_tokens:
                        selected_messages.insert(0, msg)  # Insert at beginning to maintain order
                        total_tokens += msg_tokens
                    else:
                        break  # Can't fit more messages
            
            history_to_use = selected_messages
            logger.debug(f"Selected {len(selected_messages)} messages from history (used {total_tokens}/{max_tokens} tokens)")
        else:
            # No token budget constraint - use last 5 messages with 100 char truncation
            logger.debug(f"No token budget constraint - using last {len(history_to_use)} messages")
        
        # Build contents from selected messages
        for msg in history_to_use:
            role = "user" if msg.role == MessageRole.USER else "model"
            parts = []

            # Add text content - ensure it's a string
            if msg.content:
                text_content = str(msg.content) if not isinstance(msg.content, str) else msg.content
                # Truncate long messages to 100 chars to save tokens
                if len(text_content) > 100:
                    text_content = text_content[:100] + "..."
                parts.append({"text": text_content})

            # Skip images from history to save tokens (they consume a lot of tokens)

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

    async def _generate_content(self, contents: list[dict], system_instructions: str | None = None) -> tuple[str, float]:
        """Generate content using Gemini API - True Async Implementation"""
        logger.info(f"Generating Gemini response with {len(contents)} messages")
        
        # Log estimated input tokens for debugging (using tiktoken)
        if self.tokenizer:
            try:
                # Estimate tokens for contents (serialize to JSON for estimation)
                contents_str = json.dumps(contents, ensure_ascii=False)
                system_instructions_str = system_instructions or ""
                estimated_input_tokens = self._estimate_tokens(contents_str) + self._estimate_tokens(system_instructions_str)
                logger.debug(f"Estimated input tokens: ~{estimated_input_tokens} (contents: {len(contents)} messages, system: {len(system_instructions_str)} chars)")
            except Exception as e:
                logger.debug(f"Could not estimate input tokens: {e}")

        # Build REST API request payload
        url = f"{self.api_base_url}/models/{self.model_name}:generateContent"
        
        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": settings.gemini_max_tokens,
                "temperature": settings.gemini_temperature
            }
        }
        
        # Use systemInstruction parameter if available (more token-efficient than including as message)
        # This reduces input token consumption significantly
        if system_instructions:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instructions}]
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
            
            # Check finish reason to detect truncation
            finish_reason = candidate.get("finishReason")
            
            parts = candidate["content"]["parts"]
            if not parts or "text" not in parts[0]:
                raise AIServiceException("No text in Gemini API response")
            
            # Combine all text parts in case of multi-part response
            response_text = ""
            for part in parts:
                if "text" in part:
                    response_text += part["text"]
            
            # Get token count from response if available
            usage_metadata = result.get("usageMetadata", {})
            token_count = usage_metadata.get("totalTokenCount", 0)
            prompt_token_count = usage_metadata.get("promptTokenCount", 0)
            candidates_token_count = usage_metadata.get("candidatesTokenCount", 0)
            
            # Calculate output tokens (candidatesTokenCount if available, otherwise estimate)
            output_token_count = candidates_token_count
            if not output_token_count and token_count and prompt_token_count:
                output_token_count = token_count - prompt_token_count
            
            # Debug logging for truncated responses
            if finish_reason == "MAX_TOKENS":
                # Log detailed info about token usage
                logger.warning(
                    f"Response truncated (MAX_TOKENS): {len(response_text)} chars, "
                    f"output_tokens={output_token_count}, prompt_tokens={prompt_token_count}, "
                    f"total_tokens={token_count}, maxOutputTokens={settings.gemini_max_tokens}, "
                    f"num_parts={len(parts)}, contents_messages={len(contents)}, "
                    f"response='{response_text}'"
                )
                # If prompt is consuming most tokens, suggest reducing input size
                if prompt_token_count > settings.gemini_max_tokens * 0.8:
                    logger.error(
                        f"INPUT tokens ({prompt_token_count}) consuming >80% of budget. "
                        f"Consider reducing conversation history or system instructions length."
                    )
            elif finish_reason and finish_reason != "STOP":
                logger.warning(f"Response finished with reason: {finish_reason} (expected STOP)")
            
            # Fallback estimation if not provided by API
            if token_count == 0:
                # Use tiktoken for more accurate estimation
                token_count = self._estimate_tokens(response_text)

            logger.info(f"Generated response: {len(response_text)} chars, ~{int(token_count)} tokens (true async), finish_reason={finish_reason}")

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
            
            transcription_text = parts[0].get("text", "")
            if not isinstance(transcription_text, str):
                raise TranscriptionException("Invalid transcription text type from Gemini API")
            
            transcription = transcription_text.strip()
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

            response = await self.http_client.post(
                url,
                json=payload,
                headers={
                    "x-goog-api-key": self.api_key,
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )
            response.raise_for_status()

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


