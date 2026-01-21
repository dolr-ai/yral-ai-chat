"""
Character Generator Service
"""


from loguru import logger
from pydantic import validate_call

from src.core.exceptions import AIServiceException
from src.models.internal import CharacterValidation, LLMGenerateParams
from src.models.responses import GeneratedMetadataResponse, SystemPromptResponse
from src.services.gemini_client import GeminiClient
from src.services.replicate_client import ReplicateClient


class CharacterGeneratorService:
    """Service for generating AI characters using LLMs and Image Gen"""

    def __init__(self, gemini_client: GeminiClient, replicate_client: ReplicateClient):
        self.gemini_client = gemini_client
        self.replicate_client = replicate_client

    @validate_call
    async def generate_system_instructions(self, prompt: str) -> SystemPromptResponse:
        """
        Generate system instructions from a character concept prompt
        """
        system_prompt = (
            "You are an expert AI character designer. "
            "Your task is to create detailed, immersive system instructions for an AI persona based on a short description. "
            "The output MUST follow this exact structure:\n\n"
            "1. Role Definition: Start with 'You are [Name], [Role]...'\n"
            "2. Responsibilities: A section 'Your role is to:' followed by a numbered list of tasks.\n"
            "3. Response Style: A section titled '**RESPONSE STYLE:**' detailing tone, conciseness, and formatting (e.g., maximum lines, no self-corrections).The default response style should be casual and friendly within 1-2 lines so that it can fit in a mobile screen.\n"
            "4. Language & Context: A section titled '**LANGUAGE & CONTEXT:**' specifying that the AI should use the user's language/mix (Hinglish, etc.) and Indian cultural context. The default language should be Hinglish (Simple and Modern Hindi written in English Script along with English words).\n"
            "5. Goal: A closing paragraph summarizing the character's purpose.\n\n"
            "Do not include any preamble or explanation, just the raw system instructions."
        )

        user_prompt = f"Create system instructions for a character described as: '{prompt}'"

        try:
            # Call Gemini
            response = await self.gemini_client.generate_response(
                LLMGenerateParams(
                    user_message=user_prompt,
                    system_instructions=system_prompt,
                    max_tokens=2048,
                )
            )
            return SystemPromptResponse(system_instructions=response.text.strip())
        except Exception as e:
            logger.error(f"Failed to generate system instructions: {e}")
            raise AIServiceException("Failed to generate system instructions") from e

    @validate_call
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
            "3. If valid, refine the system instructions if needed to be more effective and store them in 'system_instructions'. "
            "4. Generate metadata: name, display_name, description (should be a 1 liner), initial_greeting (In Hinglish), suggested_messages (In Hinglish), personality_traits, category. "
            "5. Create a specific, detailed image generation prompt for the character's avatar and store it in 'image_prompt'. The style of the image should be realistic"
        )

        try:
            # Step 1: Validate and generate metadata using LLM
            response = await self.gemini_client.generate_response(
                LLMGenerateParams(
                    user_message=f"System Instructions to analyze:\n\n{system_instructions}",
                    system_instructions=validation_prompt,
                    max_tokens=4096,
                    response_mime_type="application/json",
                    response_schema=CharacterValidation.model_json_schema(),
                )
            )

            # Parse using Pydantic
            validation = CharacterValidation.model_validate_json(response.text)

            if not validation.is_valid:
                return GeneratedMetadataResponse(is_valid=False, reason=validation.reason or "Invalid character concept")

            # 2. Generate Avatar using Replicate
            image_prompt = validation.image_prompt
            avatar_url = None
            if image_prompt:
                try:
                    # Enhance prompt for better results
                    enhanced_prompt = f"{image_prompt}, high quality, detailed, centered portrait"
                    avatar_url = await self.replicate_client.generate_image(enhanced_prompt)
                except Exception as e:
                    logger.error(f"Failed to generate avatar: {e}")

            # Convert personality_traits from list of PersonalityTrait objects to dict
            personality_traits_dict = {}
            if validation.personality_traits:
                personality_traits_dict = {
                    str(t.trait): t.value for t in validation.personality_traits if t.trait
                }

            return GeneratedMetadataResponse(
                is_valid=True,
                name=validation.name,
                display_name=validation.display_name,
                description=validation.description,
                initial_greeting=validation.initial_greeting,
                suggested_messages=validation.suggested_messages,
                personality_traits=personality_traits_dict,
                category=validation.category,
                avatar_url=avatar_url,
            )
        except Exception as e:
            if isinstance(e, AIServiceException):
                raise
            logger.error(f"Failed to process character metadata: {e}")
            raise AIServiceException(f"Failed to process character metadata: {e!s}") from e
