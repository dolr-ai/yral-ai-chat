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
            "Your task is to create a concise, immersive system instruction paragraph for an AI persona based on a short description. "
            "The output MUST be a single paragraph of maximum 500 characters focusing on the character's role, background, and personality. "
            "Do not include any preamble or explanation, just the raw system instructions paragraph."
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
            "2. IMPORTANT: If the concept violates safety guidelines, you MUST set 'is_valid' to false and provide a reason."
            "3. If valid, generate metadata: name (MUST be 3-12 characters, lowercase, alphanumeric only - no spaces, underscores, or special characters), display_name, description (should be a 1 liner), initial_greeting, suggested_messages, personality_traits, category. "
            "4. IMPORTANT: Use the language specified in the system instructions for 'initial_greeting' and 'suggested_messages'. If no specific language is mentioned, default to Hinglish (Hindi mixed with English text in English letters). "
            "5. If valid, refine the system instructions if needed to be more effective and store them in 'system_instructions'. "
            "6. Create a specific, detailed image generation prompt for the character's avatar and store it in 'image_prompt'. The style of the image should be realistic. "

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

            # Pre-parse check for safety refusals in raw text
            refusal_patterns = [
                "i cannot create",
                "i'm sorry, but i cannot",
                "safety guidelines",
                "harmful and unethical",
                "harmless and helpful",
                "sexually suggestive",
                "falls outside of my safety",
                "cannot assist you with this request",
            ]
            response_text_lower = response.text.lower()
            if any(pattern in response_text_lower for pattern in refusal_patterns):
                logger.warning("Detected safety refusal in LLM response text")
                return GeneratedMetadataResponse(
                    is_valid=False,
                    reason="Content violates safety guidelines and was refused by the AI."
                )

            # Parse using Pydantic
            validation = CharacterValidation.model_validate_json(response.text)

            if not validation.is_valid:
                return GeneratedMetadataResponse(is_valid=False, reason=validation.reason or "Invalid character concept")

            # Check for safety refusals even if LLM said is_valid=True
            if validation.is_valid:
                refusal_patterns = [
                    "i cannot create",
                    "i'm sorry, but i cannot",
                    "safety guidelines",
                    "harmful and unethical",
                    "harmless and helpful",
                    "sexually suggestive",
                    "falls outside of my safety",
                    "cannot assist you with this request",
                ]
                combined_text = f"{validation.description or ''}".lower()
                if any(pattern in combined_text for pattern in refusal_patterns):
                    logger.warning(f"Detected safety refusal in LLM response for character: {validation.name}")
                    return GeneratedMetadataResponse(
                        is_valid=False,
                        reason="Content violates safety guidelines and was refused by the AI."
                    )

            # 2. Generate Avatar using Replicate
            image_prompt = validation.image_prompt
            avatar_url = None
            if image_prompt and validation.is_valid:
                try:
                    # Enhance prompt for better results
                    enhanced_prompt = f"{image_prompt}, high quality, detailed, centered portrait"
                    avatar_url = await self.replicate_client.generate_image(
                        enhanced_prompt,
                        aspect_ratio="1:1"
                    )
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

    @validate_call
    async def generate_initial_greeting(
        self,
        display_name: str,
        system_instructions: str,
    ) -> tuple[str, list[str]]:
        """
        Generate an initial greeting and suggested messages for the character.

        Returns:
            A tuple of (initial_greeting, suggested_messages)
        """
        prompt = (
            f"Based on the following character description, create an initial greeting and "
            f"3-4 suggested starter messages for the user. The greeting should be in the character's voice. "
            f"The output MUST be in JSON format with 'initial_greeting' (string) and 'suggested_messages' (list of strings) keys.\n\n"
            f"Character: {display_name}\n\n"
            f"Description:\n{system_instructions}\n\n"
            f"Respond only with raw JSON."
        )

        try:
            params = LLMGenerateParams(
                user_message=prompt,
                system_instructions="You are a creative character writer. Use the tone and language consistent with the character's system instructions. If no specific language/tone is mentioned, default to Hinglish.",
                response_mime_type="application/json",
            )
            response = await self.gemini_client.generate_response(params)
            import json
            data = json.loads(response.text)
            return data.get("initial_greeting", f"Hi! I'm {display_name}. Nice to meet you!"), data.get("suggested_messages", [])
        except Exception as e:
            logger.error(f"Failed to generate initial greeting: {e}")
            return f"Hi! I'm {display_name}. How can I help you today?", []

    @validate_call
    async def generate_starter_video_prompt(
        self,
        display_name: str,
        system_instructions: str,
    ) -> str:
        """
        Generate a starter video prompt for the character.

        Args:
            display_name: Character's display name
            system_instructions: Character's full system instructions

        Returns:
            A concise video prompt describing an intro scene
        """
        prompt = (
            f"Based on the following character description, create a concise starter video prompt "
            f"(1-2 sentences) for an intro video. The prompt should describe a short scene where "
            f"the character introduces themselves or demonstrates their expertise. "
            f"Include specific actions, dialogue snippets, or gestures.\n\n"
            f"Character: {display_name}\n\n"
            f"Description:\n{system_instructions}\n\n"
            f"Output only the video prompt, nothing else."
        )

        try:
            params = LLMGenerateParams(
                user_message=prompt,
                system_instructions="You are a creative video prompt generator. Create concise, vivid prompts.",
            )
            response = await self.gemini_client.generate_response(params)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Failed to generate starter video prompt: {e}")
            # Return a fallback prompt
            return f"{display_name} introduces themselves with a warm greeting and shares what they do."
