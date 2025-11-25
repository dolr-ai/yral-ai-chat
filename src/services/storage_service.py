"""
File storage service for media uploads
"""
import os
import aiofiles
from pathlib import Path
from typing import Tuple
from uuid import uuid4
from datetime import datetime
from loguru import logger
from src.config import settings
from src.core.exceptions import BadRequestException


class StorageService:
    """Service for handling file uploads and storage"""
    
    def __init__(self):
        """Initialize storage service"""
        self.upload_dir = Path(settings.media_upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Storage service initialized: {self.upload_dir}")
    
    async def save_file(
        self,
        file_content: bytes,
        filename: str,
        user_id: str
    ) -> Tuple[str, str, int]:
        """
        Save uploaded file
        
        Args:
            file_content: File binary content
            filename: Original filename
            user_id: User ID for organizing files
            
        Returns:
            Tuple of (file_url, mime_type, file_size)
        """
        # Create user directory
        user_dir = self.upload_dir / user_id
        user_dir.mkdir(exist_ok=True)
        
        # Generate unique filename
        file_ext = Path(filename).suffix.lower()
        unique_filename = f"{uuid4()}{file_ext}"
        file_path = user_dir / unique_filename
        
        # Get file size
        file_size = len(file_content)
        
        # Determine mime type
        mime_type = self._get_mime_type(file_ext)
        
        # Save file
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_content)
        
        # Generate URL
        file_url = f"{settings.media_base_url}/{user_id}/{unique_filename}"
        
        logger.info(f"File saved: {file_path} ({file_size} bytes)")
        
        return file_url, mime_type, file_size
    
    def _get_mime_type(self, file_ext: str) -> str:
        """Get MIME type from file extension"""
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.mp3': 'audio/mpeg',
            '.m4a': 'audio/mp4',
            '.wav': 'audio/wav',
            '.ogg': 'audio/ogg',
        }
        return mime_types.get(file_ext, 'application/octet-stream')
    
    @staticmethod
    def validate_image(filename: str, file_size: int):
        """Validate image file"""
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
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
        allowed_extensions = {'.mp3', '.m4a', '.wav', '.ogg'}
        file_ext = Path(filename).suffix.lower()
        
        if file_ext not in allowed_extensions:
            raise BadRequestException(
                f"Unsupported audio format. Allowed: {', '.join(allowed_extensions)}"
            )
        
        if file_size > settings.max_audio_size_bytes:
            raise BadRequestException(
                f"Audio too large. Max size: {settings.max_audio_size_mb}MB"
            )
    
    async def get_audio_duration(self, file_path: Path) -> int:
        """
        Get audio file duration in seconds
        Note: This is a placeholder. In production, use a library like mutagen or ffprobe
        """
        # TODO: Implement actual audio duration detection
        # For now, return 0 and let the client provide duration
        return 0


# Global storage service instance
storage_service = StorageService()


