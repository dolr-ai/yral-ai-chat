"""
Google Gemini AI Client
"""
import google.generativeai as genai
from typing import List, Optional, Dict, Any
import base64
import httpx
from loguru import logger
from src.config import settings
from src.models.entities import Message, MessageRole, MessageType
from src.core.exceptions import AIServiceException, TranscriptionException


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
        conversation_history: List[Message] = None,
        media_urls: List[str] = None
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
            contents = []
            
            # Add system instructions as first message
            contents.append({
                "role": "user",
                "parts": [{"text": f"System Instructions: {system_instructions}"}]
            })
            contents.append({
                "role": "model",
                "parts": [{"text": "Understood. I will follow these instructions."}]
            })
            
            # Add conversation history
            if conversation_history:
                for msg in conversation_history[-10:]:  # Last 10 messages for context
                    role = "user" if msg.role == MessageRole.USER else "model"
                    
                    parts = []
                    
                    # Add text content
                    if msg.content:
                        parts.append({"text": msg.content})
                    
                    # Add images from history if available
                    if msg.message_type in [MessageType.IMAGE, MessageType.MULTIMODAL]:
                        for url in msg.media_urls[:3]:  # Max 3 images from history
                            try:
                                image_data = await self._download_image(url)
                                parts.append({"inline_data": image_data})
                            except Exception as e:
                                logger.warning(f"Failed to load image from history: {e}")
                    
                    if parts:
                        contents.append({"role": role, "parts": parts})
            
            # Add current user message with optional images
            current_parts = []
            
            if user_message:
                current_parts.append({"text": user_message})
            
            # Add current images
            if media_urls:
                for url in media_urls[:5]:  # Max 5 images in current message
                    try:
                        image_data = await self._download_image(url)
                        current_parts.append({"inline_data": image_data})
                    except Exception as e:
                        logger.error(f"Failed to download image {url}: {e}")
                        raise AIServiceException(f"Failed to process image: {e}")
            
            contents.append({"role": "user", "parts": current_parts})
            
            # Generate response
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
            
            # Estimate token count (rough estimate)
            token_count = len(response_text.split()) * 1.3  # Approximate
            
            logger.info(f"Generated response: {len(response_text)} chars, ~{int(token_count)} tokens")
            
            return response_text, int(token_count)
            
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise AIServiceException(f"Failed to generate AI response: {str(e)}")
    
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
            
            return transcription
            
        except Exception as e:
            logger.error(f"Audio transcription error: {e}")
            raise TranscriptionException(f"Failed to transcribe audio: {str(e)}")
    
    async def _download_image(self, url: str) -> Dict[str, Any]:
        """Download and encode image for Gemini"""
        try:
            response = await self.http_client.get(url)
            response.raise_for_status()
            
            image_data = response.content
            mime_type = response.headers.get('content-type', 'image/jpeg')
            
            return {
                "mime_type": mime_type,
                "data": image_data
            }
        except Exception as e:
            logger.error(f"Failed to download image {url}: {e}")
            raise
    
    async def _download_audio(self, url: str) -> Dict[str, Any]:
        """Download and encode audio for Gemini"""
        try:
            response = await self.http_client.get(url)
            response.raise_for_status()
            
            audio_data = response.content
            mime_type = response.headers.get('content-type', 'audio/mpeg')
            
            return {
                "mime_type": mime_type,
                "data": audio_data
            }
        except Exception as e:
            logger.error(f"Failed to download audio {url}: {e}")
            raise
    
    async def health_check(self) -> dict:
        """Check Gemini API health"""
        try:
            import time
            start = time.time()
            
            # Simple test request
            response = self.model.generate_content("Hi")
            
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


