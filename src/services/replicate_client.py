"""
Replicate API Client
"""

import replicate
from loguru import logger
from pydantic import validate_call

from src.config import settings


class ReplicateClient:
    """Replicate API client wrapper for image generation"""

    def __init__(self):
        """Initialize Replicate client"""
        if settings.replicate_api_token:
            self.client = replicate.Client(api_token=settings.replicate_api_token)
            self.model = settings.replicate_model
            logger.info(f"Replicate client initialized with model: {self.model}")
        else:
            logger.warning("REPLICATE_API_TOKEN is not set. Image generation will not work.")
            self.client = None

    @validate_call
    async def generate_image(self, prompt: str) -> str | None:
        """
        Generate image from prompt

        Args:
            prompt: Image generation prompt

        Returns:
            URL of generated image or None if failed
        """
        if not self.client:
            logger.error("Replicate client not initialized")
            return None

        try:
            logger.info(f"Generating image with prompt: {prompt[:50]}...")

            # Run the model
            # Note: synchronous call, might want to wrap in run_in_executor if blocking too long,
            # but replicate client might handle async or be fast enough for now.
            # Ideally we'd use their async client if available or threadpool.
            # Replicate python client methods are sync mostly.

            output = self.client.run(
                self.model,
                input={
                    "prompt": prompt,
                    "go_fast": True,
                    "megapixels": "1",
                    "num_outputs": 1,
                    "aspect_ratio": "1:1",
                    "output_format": "jpg",
                    "output_quality": 80,
                },
            )

            # Output is usually a list of strings (URLs) or a file object depending on model
            if isinstance(output, list) and output:
                image_url = str(output[0])
                logger.info(f"Image generated successfully: {image_url}")
                return image_url

            logger.error(f"Unexpected output format from Replicate: {type(output)}")
            return None

        except Exception as e:
            logger.error(f"Replicate image generation failed: {e}")
            return None
