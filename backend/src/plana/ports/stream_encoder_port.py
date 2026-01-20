"""Stream encoder port interface for encoding video frames."""

from abc import ABC, abstractmethod
from typing import Optional


class StreamEncoderPort(ABC):
    """Port interface for encoding video frames for streaming."""
    
    @abstractmethod
    def encode_frame(self, frame_data: bytes, format: str) -> Optional[bytes]:
        """Encode a frame for streaming.
        
        Args:
            frame_data: Raw frame data
            format: Input format (e.g., 'YUYV', 'MJPG')
        
        Returns:
            Encoded frame data (JPEG bytes) ready for streaming, or None if encoding failed
        """
        pass
    
    @abstractmethod
    def get_mime_type(self) -> str:
        """Get MIME type for the encoded stream.
        
        Returns:
            MIME type string (e.g., 'image/jpeg')
        """
        pass
