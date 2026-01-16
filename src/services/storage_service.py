"""
S3-compatible storage service for media uploads (Storj)
"""
import asyncio
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.config import Config
from loguru import logger

from src.config import settings
from src.core.exceptions import BadRequestException


class StorageService:
    """Service for handling file uploads to S3-compatible storage (Storj)"""

    def __init__(self):
        """Initialize S3-compatible storage service (lazy initialization)"""
        self._s3_client = None
        self.bucket = settings.aws_s3_bucket

    @property
    def s3_client(self):
        """Lazy initialization of S3-compatible client to avoid startup failures"""
        if self._s3_client is None:
            try:
                self._s3_client = boto3.client(
                    "s3",
                    aws_access_key_id=settings.aws_access_key_id,
                    aws_secret_access_key=settings.aws_secret_access_key,
                    endpoint_url=settings.s3_endpoint_url,
                    region_name=settings.aws_region,
                    config=Config(signature_version="s3v4")
                )
                logger.info(f"Storage service initialized: bucket={self.bucket}, endpoint={settings.s3_endpoint_url}")
            except Exception as e:
                logger.error(f"Failed to initialize S3 client: {e}")
                raise
        return self._s3_client

    async def save_file(
        self,
        file_content: bytes,
        filename: str,
        user_id: str
    ) -> tuple[str, str, int]:
        """
        Save uploaded file to S3-compatible storage
        
        Args:
            file_content: File binary content
            filename: Original filename
            user_id: User ID for organizing files
            
        Returns:
            Tuple of (storage_key, mime_type, file_size)
        """
        file_ext = Path(filename).suffix.lower()
        unique_filename = f"{uuid4()}{file_ext}"
        s3_key = f"{user_id}/{unique_filename}"

        file_size = len(file_content)
        mime_type = self._get_mime_type(file_ext)

        def _upload():
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=s3_key,
                Body=file_content,
                ContentType=mime_type,
            )

        await asyncio.to_thread(_upload)

        logger.info(f"File uploaded to storage: {s3_key} ({file_size} bytes)")

        return s3_key, mime_type, file_size

    def generate_presigned_url(self, key: str, expires_in: int | None = None) -> str:
        """
        Generate a presigned URL for accessing an object.
        If the key is already an external URL (http/https), it's returned as-is.

        Args:
            key: Storage object key or external URL
            expires_in: Expiration time in seconds (defaults to settings.s3_url_expires_seconds)

        Returns:
            A time-limited presigned URL for the object, or the original URL if external
        """
        if not key:
            raise ValueError("Storage key is required to generate a presigned URL")

        # Skip external URLs (http/https) - they don't need presigning
        if key.startswith(("http://", "https://")):
            return key

        expiration = expires_in or settings.s3_url_expires_seconds

        return self.s3_client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
            },
            ExpiresIn=expiration,
        )

    async def generate_presigned_urls_batch(self, keys: list[str]) -> dict[str, str]:
        if not keys:
            return {}
            
        # Filter for unique keys and skip external URLs (http/https)
        # External URLs don't need presigning
        unique_keys = [
            k for k in {k for k in keys if k}
            if not k.startswith(("http://", "https://"))
        ]
        
        if not unique_keys:
            return {}
            
        # Generate URLs in parallel
        tasks = [asyncio.to_thread(self.generate_presigned_url, key) for key in unique_keys]
        urls = await asyncio.gather(*tasks)
        
        return {k: u for k, u in zip(unique_keys, urls, strict=False) if u}

    def extract_key_from_url(self, url_or_key: str) -> str:
        """
        Extract storage key from either a storage key or an old public URL.
        For backward compatibility with existing data that may contain full public URLs.

        Args:
            url_or_key: Either a storage key (e.g., "user123/uuid.jpg") or a full public URL

        Returns:
            The storage key
        """
        if not url_or_key:
            return url_or_key

        if not url_or_key.startswith(("http://", "https://")):
            return url_or_key

        public_base = settings.s3_public_url_base.rstrip("/")
        if url_or_key.startswith(public_base):
            return url_or_key[len(public_base):].lstrip("/")

        logger.debug(f"External URL or non-S3 link detected: {url_or_key}")
        return url_or_key

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
        Get audio file duration in seconds.
        TODO: Implement using mutagen or ffprobe (requires downloading file from storage)
        """
        return 0

