"""
S3 storage service for media uploads
"""
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.config import Config
from loguru import logger

from src.config import settings
from src.core.exceptions import BadRequestException


class StorageService:
    """Service for handling file uploads to S3"""

    def __init__(self):
        """Initialize S3 storage service"""
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.aws_region,
            config=Config(signature_version="s3v4")
        )
        self.bucket = settings.aws_s3_bucket
        logger.info(f"S3 Storage service initialized: bucket={self.bucket}, endpoint={settings.s3_endpoint_url}")

    async def save_file(
        self,
        file_content: bytes,
        filename: str,
        user_id: str
    ) -> tuple[str, str, int]:
        """
        Save uploaded file to S3
        
        Args:
            file_content: File binary content
            filename: Original filename
            user_id: User ID for organizing files
            
        Returns:
            Tuple of (file_url, mime_type, file_size)
        """
        # Generate unique filename
        file_ext = Path(filename).suffix.lower()
        unique_filename = f"{uuid4()}{file_ext}"
        s3_key = f"{user_id}/{unique_filename}"

        # Get file size
        file_size = len(file_content)

        # Determine mime type
        mime_type = self._get_mime_type(file_ext)

        # Upload to S3 with public-read ACL
        self.s3_client.put_object(
            Bucket=self.bucket,
            Key=s3_key,
            Body=file_content,
            ContentType=mime_type,
            ACL="public-read"  # Make the object publicly accessible
        )

        # Generate public URL
        file_url = f"{settings.s3_public_url_base}/{s3_key}"

        logger.info(f"File uploaded to S3: {s3_key} ({file_size} bytes)")

        return file_url, mime_type, file_size

    def _get_mime_type(self, file_ext: str) -> str:
        """Get MIME type from file extension"""
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".wav": "audio/wav",
            ".ogg": "audio/ogg",
        }
        return mime_types.get(file_ext, "application/octet-stream")

    @staticmethod
    def validate_image(filename: str, file_size: int):
        """Validate image file"""
        allowed_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
        file_ext = Path(filename).suffix.lower()

        if file_ext not in allowed_extensions:
            raise BadRequestException(
                f"Unsupported image format. Allowed: {', '.join(allowed_extensions)}"
            )

        if file_size > settings.max_image_size_bytes:
            raise BadRequestException(
                f"Image too large. Max size: {settings.max_image_size_mb}MB"
            )

    @staticmethod
    def validate_audio(filename: str, file_size: int):
        """Validate audio file"""
        allowed_extensions = {".mp3", ".m4a", ".wav", ".ogg"}
        file_ext = Path(filename).suffix.lower()

        if file_ext not in allowed_extensions:
            raise BadRequestException(
                f"Unsupported audio format. Allowed: {', '.join(allowed_extensions)}"
            )

        if file_size > settings.max_audio_size_bytes:
            raise BadRequestException(
                f"Audio too large. Max size: {settings.max_audio_size_mb}MB"
            )

    async def get_audio_duration(self, s3_key: str) -> int:
        """
        Get audio file duration in seconds
        Note: This is a placeholder. In production, use a library like mutagen or ffprobe
        For S3 storage, you would need to download the file temporarily or use a streaming approach
        """
        # TODO: Implement actual audio duration detection
        # For now, return 0 and let the client provide duration
        return 0


# Global storage service instance
storage_service = StorageService()


