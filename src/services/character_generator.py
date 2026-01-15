"""
Character Generator Service
"""
import json
import re

from loguru import logger

from src.core.exceptions import AIServiceException
from src.models.responses import GeneratedMetadataResponse, SystemPromptResponse
from src.services.gemini_client import GeminiClient
from src.services.replicate_client import ReplicateClient


class CharacterGeneratorService:
    """Service for generating AI characters using LLMs and Image Gen"""

    def __init__(self, gemini_client: GeminiClient, replicate_client: ReplicateClient):
        self.gemini_client = gemini_client
        self.replicate_client = replicate_client

    async def generate_system_instructions(self, prompt: str) -> SystemPromptResponse:
        """
        Generate system instructions from a character concept prompt
        """
        system_prompt = (
            "You are an expert AI character designer. "
            "Your task is to create detailed, immersive system instructions for an AI persona based on a short description. "
            "The output should be the raw system instructions that would be passed to an LLM to roleplay this character. "
            "Do not include any preamble or explanation, just the system instructions."
        )
        
        user_prompt = f"Create system instructions for a character described as: '{prompt}'"

        try:
            # Call Gemini
            response_text, _ = await self.gemini_client.generate_response(
                user_message=user_prompt,
                system_instructions=system_prompt,
                max_tokens=2048
            )
            return SystemPromptResponse(system_instructions=response_text.strip())
        except Exception as e:
            logger.error(f"Failed to generate system instructions: {e}")
            raise AIServiceException("Failed to generate system instructions") from e

    async def validate_and_generate_metadata(self, system_instructions: str) -> GeneratedMetadataResponse:
        """
        Validate system instructions and generate metadata + avatar
        """
        
        # 1. Validate and Generate Metadata using Gemini
        validation_prompt = (
            "You are an AI Character Validator and Metadata Generator. "
            "Analyze the provided system instructions. "
            "1. Determine if the character concept is VALID based on two criteria: "
            "   a) It must be coherent and not nonsensical. "
            "   b) It must be strictly NON-NSFW (no sexually explicit content, no erotica). "
            "2. If invalid (nonsensical OR NSFW), set 'is_valid' to false and provide a reason. "
            "3. If valid, refine the system instructions if needed to be more effective. "
            "4. Generate metadata: name, display_name, bio, initial_greeting, suggested_messages, personality_traits, category. "
            "5. Create a specific, detailed image generation prompt for the character's avatar. "
            "Output ONLY JSON in the following format: "
            "{"
            "  'is_valid': bool,"
            "  'reason': str (if invalid),"
            "  'system_instructions': str (refined),"
            "  'name': str (slug, lowercase, underscores),"
            "  'display_name': str,"
            "  'bio': str,"
            "  'initial_greeting': str,"
            "  'suggested_messages': [str],"
            "  'personality_traits': {str: str},"
            "  'category': str,"
            "  'image_prompt': str"
            "}"
        )
        
        try:
            # Step 1: Validate and generate metadata using LLM
            response_text, _ = await self.gemini_client.generate_response(
                user_message=f"System Instructions to analyze:\n\n{system_instructions}",
                system_instructions=validation_prompt,
                max_tokens=4096  # High limit for metadata generation
            )
            
            # Extract JSON
            data = self._extract_json(response_text)
            
            if not data.get("is_valid", False):
                return GeneratedMetadataResponse(
                    is_valid=False,
                    reason=data.get("reason", "Invalid character concept")
                )
                
            # 2. Generate Avatar using Replicate
            image_prompt = data.get("image_prompt", "")
            avatar_url = None
            if image_prompt:
                try:
                    # Enhance prompt for better results
                    enhanced_prompt = f"{image_prompt}, high quality, detailed, centered portrait"
                    avatar_url = await self.replicate_client.generate_image(enhanced_prompt)
                except Exception as e:
                    logger.error(f"Failed to generate avatar: {e}")
                    # We continue without avatar if it fails
            
            return GeneratedMetadataResponse(
                is_valid=True,
                name=data.get("name"),
                display_name=data.get("display_name"),
                bio=data.get("bio"),
                initial_greeting=data.get("initial_greeting"),
                suggested_messages=data.get("suggested_messages"),
                personality_traits=data.get("personality_traits"),
                category=data.get("category"),
                avatar_url=avatar_url
            )
            
        except Exception as e:
            logger.error(f"Failed to validate and generate metadata: {e}")
            raise AIServiceException("Failed to process character metadata") from e

    def _extract_json(self, text: str) -> dict:
        """Helper to extract JSON from text"""
        try:
            # Try direct parse
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON block
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
            # Try cleanup
            clean_text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(clean_text)
