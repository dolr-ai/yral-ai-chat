import asyncio

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
    async def generate_image(self, prompt: str, aspect_ratio: str = "1:1") -> str | None:
        """
        Generate image from prompt using standard flux-dev model.
        """
        if not self.client:
            logger.error("Replicate client not initialized")
            return None


        def _run():
            return self.client.run(
                self.model,
                input={
                    "prompt": prompt,
                    "go_fast": True,
                    "megapixels": "1",
                    "aspect_ratio": aspect_ratio,
                    "output_format": "jpg",
                    "output_quality": 80,
                },
            )

        try:
            logger.info(f"Generating image with prompt: {prompt[:50]}...")
            loop = asyncio.get_event_loop()
            output = await loop.run_in_executor(None, _run)

            if isinstance(output, list) and output:
                image_url = str(output[0])
                logger.info(f"Image generated successfully: {image_url}")
                return image_url
            
            if output:
                image_url = str(output)
                logger.info(f"Image generated successfully (direct format): {image_url}")
                return image_url

            logger.error(f"Unexpected or empty output from Replicate: {type(output)}")
            return None

        except Exception as e:
            logger.error(f"Replicate image generation failed: {e}")
            return None

    @validate_call
    async def generate_image_via_image(self, prompt: str, input_image: str, aspect_ratio: str = "9:16") -> str | None:
        """
        Generate image using a reference image (flux-kontext-dev).
        """
        if not self.client:
            logger.error("Replicate client not initialized")
            return None


        def _run():
            return self.client.run(
                "black-forest-labs/flux-kontext-dev",
                input={
                    "prompt": prompt,
                    "go_fast": True,
                    "guidance": 2.5,
                    "megapixels": "1",
                    "num_inference_steps": 30,
                    "aspect_ratio": aspect_ratio,
                    "output_format": "jpg",
                    "output_quality": 80,
                    "input_image": input_image,
                },
            )

        try:
            logger.info(f"Generating image via context with prompt: {prompt[:50]}...")
            loop = asyncio.get_event_loop()
            output = await loop.run_in_executor(None, _run)

            if isinstance(output, list) and output:
                image_url = str(output[0])
                logger.info(f"Image generated via context successfully: {image_url}")
                return image_url
            
            if output:
                image_url = str(output)
                logger.info(f"Image generated via context successfully (direct format): {image_url}")
                return image_url

            logger.error(f"Unexpected or empty output from Replicate: {type(output)}")
            return None

        except Exception as e:
            logger.error(f"Replicate image-via-image generation failed: {e}")
            return None
