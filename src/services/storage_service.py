"""
S3-compatible storage service for media uploads (Storj)
"""
import asyncio
from pathlib import Path
from uuid import uuid4

import aioboto3
import aiohttp
import sentry_sdk
from botocore.config import Config
from loguru import logger

from src.config import settings
from src.core.exceptions import BadRequestException


class StorageService:
    """Async S3-compatible storage service for media uploads (Storj)"""

    def __init__(self):
        self._session = aioboto3.Session()
        self.bucket = settings.aws_s3_bucket

    async def get_s3_client(self):
        """Get an async S3 client context manager"""
        return self._session.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.aws_region,
            config=Config(signature_version="s3v4")
        )

    async def save_file(
        self,
        file_content: bytes,
        filename: str,
        user_id: str
    ) -> tuple[str, str, int]:
        """Save file to S3 and return (storage_key, mime_type, file_size)"""
        with sentry_sdk.start_span(op="storage.upload", name="Save File to S3") as span:
            file_ext = Path(filename).suffix.lower()
            unique_filename = f"{uuid4()}{file_ext}"
            s3_key = f"{user_id}/{unique_filename}"

            file_size = len(file_content)
            mime_type = self._get_mime_type(file_ext)
            span.set_data("file.mime_type", mime_type)
            span.set_data("file.size", file_size)
            
            async with await self.get_s3_client() as s3:
                upload_url = await s3.generate_presigned_url(
                    "put_object",
                    Params={
                        "Bucket": self.bucket,
                        "Key": s3_key,
                        "ContentType": mime_type,
                        "ContentLength": file_size,
                    },
                    ExpiresIn=300
                )

            async with (
                aiohttp.ClientSession() as session,
                session.put(
                    upload_url,
                    data=file_content,
                    headers={
                        "Content-Type": mime_type,
                        "Content-Length": str(file_size)
                    }
                ) as response
            ):
                if response.status not in [200, 201]:
                    text = await response.text()
                    logger.error(f"S3 Upload failed status={response.status}: {text}")
                    raise RuntimeError(f"S3 Upload failed: {response.status} {text}")

            logger.info(f"File uploaded to storage: {s3_key} ({file_size} bytes)")
            return s3_key, mime_type, file_size

    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int | None = None,
        s3_client: any = None
    ) -> str:
        """
        Generate presigned URL for S3 object access.
        Returns external URLs (http/https) as-is without modification.
        """
        if not key:
            raise ValueError("Storage key is required to generate a presigned URL")

        # External URLs don't need presigning
        if key.startswith(("http://", "https://")):
            return key

        with sentry_sdk.start_span(op="storage.presign", name="Generate Single Presigned URL"):
            expiration = expires_in or settings.s3_url_expires_seconds

            # Reuse existing client if provided (for batch operations)
            if s3_client:
                return await s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": key},
                    ExpiresIn=expiration,
                )

            # Otherwise create a new client
            async with await self.get_s3_client() as s3:
                return await s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": key},
                    ExpiresIn=expiration,
                )

    async def generate_presigned_urls_batch(self, keys: list[str]) -> dict[str, str]:
        """Generate presigned URLs for multiple keys in parallel"""
        if not keys:
            return {}
            
        # Filter for S3 keys only (skip external URLs)
        unique_keys = [
            k for k in {k for k in keys if k}
            if not k.startswith(("http://", "https://"))
        ]
        
        if not unique_keys:
            return {}
            
        with sentry_sdk.start_span(op="storage.s3", name="Generate Presigned URLs") as span:
            span.set_data("storage.count", len(unique_keys))
            # Generate all URLs in parallel using a single client session
            async with await self.get_s3_client() as s3:
                tasks = [self.generate_presigned_url(key, s3_client=s3) for key in unique_keys]
                urls = await asyncio.gather(*tasks)
        
        return {k: u for k, u in zip(unique_keys, urls, strict=False) if u}

    def extract_key_from_url(self, url_or_key: str) -> str:
        """
        Extract S3 key from URL or return key as-is.
        Handles backward compatibility with old public URLs.
        """
        if not url_or_key or not url_or_key.startswith(("http://", "https://")):
            return url_or_key

        public_base = settings.s3_public_url_base.rstrip("/")
        if url_or_key.startswith(public_base):
            return url_or_key[len(public_base):].lstrip("/")

        logger.debug(f"External URL detected: {url_or_key}")
        return url_or_key

    def _get_mime_type(self, file_ext: str) -> str:
        """Map file extension to MIME type"""
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
        """Validate image file extension and size"""
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
        """Validate audio file extension and size"""
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
