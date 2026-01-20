"""MJPEG encoder adapter for streaming."""

from typing import Optional
from ..ports.stream_encoder_port import StreamEncoderPort
from ..services.logging_service import LoggingService


class MJPEGEncoderAdapter(StreamEncoderPort):
    """MJPEG encoder adapter (frames already JPEG encoded from camera)."""
    
    def __init__(self, logger: LoggingService):
        self.logger = logger
    
    def encode_frame(self, frame_data: bytes, format: str) -> Optional[bytes]:
        """Encode a frame for streaming.
        
        For MJPEG streaming, frames from OpenCV are already JPEG encoded,
        so we just pass them through.
        """
        # Frames are already JPEG encoded from camera adapter
        return frame_data
    
    def get_mime_type(self) -> str:
        """Get MIME type for the encoded stream."""
        return "image/jpeg"
