"""Camera port interface for camera capture operations."""

from abc import ABC, abstractmethod
from typing import Optional, Tuple, Any


class CameraPort(ABC):
    """Port interface for camera capture operations."""
    
    @abstractmethod
    def open(self, device_path: str, width: int, height: int, fps: float, format: str) -> bool:
        """Open camera device.
        
        Args:
            device_path: Path to camera device (e.g., /dev/video0)
            width: Frame width
            height: Frame height
            fps: Frames per second
            format: Pixel format (e.g., 'YUYV', 'MJPG')
        
        Returns:
            True if opened successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close camera device."""
        pass
    
    @abstractmethod
    def is_open(self) -> bool:
        """Check if camera is open.
        
        Returns:
            True if camera is open, False otherwise
        """
        pass
    
    @abstractmethod
    def capture_frame(self) -> Optional[bytes]:
        """Capture a single frame.
        
        Returns:
            Frame data as bytes (JPEG encoded), or None if capture failed
        """
        pass
    
    @abstractmethod
    def get_actual_settings(self) -> dict:
        """Get actual camera settings.
        
        Returns:
            Dict with actual width, height, fps, format
        """
        pass
    
    @abstractmethod
    def apply_settings(self, width: int, height: int, fps: float, format: str) -> bool:
        """Apply camera settings.
        
        Args:
            width: Frame width
            height: Frame height
            fps: Frames per second
            format: Pixel format
        
        Returns:
            True if settings applied successfully
        """
        pass
    
    @abstractmethod
    def apply_control_settings(self, exposure: Optional[int] = None, gain: Optional[float] = None, saturation: Optional[float] = None) -> bool:
        """Apply camera control settings (exposure, gain, saturation).
        
        Args:
            exposure: Exposure value (1-100)
            gain: Gain value (0-10)
            saturation: Saturation value (0-2)
        
        Returns:
            True if settings applied successfully
        """
        pass
