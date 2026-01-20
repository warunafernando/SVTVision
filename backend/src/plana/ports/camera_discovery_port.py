"""Camera discovery port interface."""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any


class CameraDiscoveryPort(ABC):
    """Port interface for camera discovery."""
    
    @abstractmethod
    def discover_cameras(self) -> List[Dict[str, Any]]:
        """Discover all available cameras.
        
        Returns:
            List of camera dictionaries with basic info (id, name, device_path)
        """
        pass
    
    @abstractmethod
    def get_camera_details(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific camera.
        
        Args:
            camera_id: Stable camera ID
            
        Returns:
            Dictionary with full camera details or None if not found
        """
        pass
    
    @abstractmethod
    def get_camera_capabilities(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Get camera capabilities (formats, resolutions, FPS ranges).
        
        Args:
            camera_id: Stable camera ID
            
        Returns:
            Dictionary with capabilities or None if not found
        """
        pass
    
    @abstractmethod
    def get_camera_controls(self, camera_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get camera controls (exposure, gain, etc.).
        
        Args:
            camera_id: Stable camera ID
            
        Returns:
            List of control dictionaries or None if not found
        """
        pass
