"""
NSFW Image Detection Service using Replicate API
"""
import asyncio
from io import BytesIO

import replicate
from loguru import logger

from src.config import settings
from src.core.exceptions import BadRequestException


class NSFWDetectionService:
    """Service for detecting NSFW content in images using Replicate"""

    def __init__(self):
        """Initialize NSFW detection service"""
        if not settings.replicate_api_key:
            logger.warning("REPLICATE_API_KEY not set - NSFW detection will be disabled")
            self.enabled = False
            self.client = None
        else:
            self.client = replicate.Client(api_token=settings.replicate_api_key)
            self.enabled = True
            logger.info("NSFW detection service initialized")

    async def check_image(self, image_content: bytes) -> bool:
        """
        Check if an image contains NSFW content
        
        Args:
            image_content: Image file content as bytes
            
        Returns:
            True if image is NSFW, False if safe
            
        Raises:
            BadRequestException: If detection fails or API key is not configured
        """
        if not self.enabled:
            logger.warning("NSFW detection disabled - skipping check")
            return False

        try:
            # Run Replicate model in thread pool to avoid blocking
            # The model accepts image bytes directly or BytesIO
            # Create BytesIO and ensure it's at the start
            image_io = BytesIO(image_content)
            image_io.seek(0)
            
            output = await asyncio.to_thread(
                self.client.run,
                "falcons-ai/nsfw_image_detection",
                input={"image": image_io}
            )

            # Parse the response
            # The model returns 'nsfw' or 'normal' as a string
            if isinstance(output, str):
                is_nsfw = output.lower() == "nsfw"
                logger.info(f"NSFW detection result: {output}, is_nsfw={is_nsfw}")
                return is_nsfw
            elif isinstance(output, dict):
                # Handle dictionary response format if model returns probabilities
                nsfw_probability = output.get("nsfw", 0.0)
                # Consider image NSFW if probability > 0.5 (50%)
                is_nsfw = nsfw_probability > 0.5
                logger.info(
                    f"NSFW detection result: nsfw_probability={nsfw_probability:.2f}, "
                    f"is_nsfw={is_nsfw}"
                )
                return is_nsfw
            else:
                # Handle unexpected response formats
                logger.warning(f"Unexpected NSFW detection response format: {output}")
                # If we can't parse, err on the side of caution and block
                return True

        except Exception as e:
            logger.error(f"NSFW detection failed: {e}")
            # On API failure, we could either:
            # 1. Block the image (safer, but might reject valid images)
            # 2. Allow the image (less safe, but better UX)
            # Going with option 1 for safety
            raise BadRequestException(
                "Unable to verify image content. Please try again or contact support."
            ) from e


# Global NSFW detection service instance
nsfw_detection_service = NSFWDetectionService()

