"""Camera service for managing multiple cameras."""

from typing import Dict, Optional, Any
from .camera_manager import CameraManager
from ..adapters.opencv_camera import OpenCVCameraAdapter
from ..adapters.mjpeg_encoder import MJPEGEncoderAdapter
from ..services.logging_service import LoggingService
from ..services.camera_config_service import CameraConfigService


class CameraService:
    """Service for managing multiple camera instances."""
    
    def __init__(
        self,
        logger: LoggingService,
        camera_config_service: CameraConfigService
    ):
        self.logger = logger
        self.camera_config_service = camera_config_service
        self.camera_managers: Dict[str, CameraManager] = {}
    
    def open_camera(
        self,
        camera_id: str,
        device_path: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[float] = None,
        format: Optional[str] = None
    ) -> bool:
        """Open a camera.
        
        If width/height/fps/format are not provided, loads from saved config.
        """
        # Check if already open
        if camera_id in self.camera_managers:
            manager = self.camera_managers[camera_id]
            if manager.is_open():
                self.logger.warning(f"Camera {camera_id} already open")
                return True
        
        # Get settings from config if not provided
        if width is None or height is None or fps is None or format is None:
            config = self.camera_config_service.get_camera_config(camera_id)
            if config and "resolution" in config:
                res = config["resolution"]
                width = width or res.get("width", 640)
                height = height or res.get("height", 480)
                fps = fps or res.get("fps", 30.0)
                format = format or res.get("format", "YUYV")
            else:
                # Defaults
                width = width or 640
                height = height or 480
                fps = fps or 30.0
                format = format or "YUYV"
        
        # Create camera adapter and encoder
        camera_adapter = OpenCVCameraAdapter(self.logger)
        encoder = MJPEGEncoderAdapter(self.logger)
        
        # Create manager
        manager = CameraManager(camera_adapter, encoder, self.logger)
        
        # Open camera
        if not manager.open(device_path, width, height, fps, format):
            return False
        
        # Store manager
        self.camera_managers[camera_id] = manager
        
        # Verify settings after opening
        verification = manager.verify_settings(width, height, fps, format)
        if not verification.get("verified"):
            self.logger.warning(
                f"Camera {camera_id} opened but settings mismatch: "
                f"expected {width}x{height}@{fps}fps, got {verification.get('actual', {})}"
            )
        
        self.logger.info(f"Camera {camera_id} opened successfully")
        return True
    
    def close_camera(self, camera_id: str) -> bool:
        """Close a camera."""
        if camera_id not in self.camera_managers:
            self.logger.warning(f"Camera {camera_id} not found")
            return False
        
        manager = self.camera_managers[camera_id]
        manager.close()
        del self.camera_managers[camera_id]
        
        self.logger.info(f"Camera {camera_id} closed")
        return True
    
    def is_camera_open(self, camera_id: str) -> bool:
        """Check if camera is open."""
        if camera_id not in self.camera_managers:
            return False
        return self.camera_managers[camera_id].is_open()
    
    def get_camera_manager(self, camera_id: str) -> Optional[CameraManager]:
        """Get camera manager for a camera."""
        return self.camera_managers.get(camera_id)
    
    def get_all_camera_managers(self) -> Dict[str, CameraManager]:
        """Get all camera managers."""
        return self.camera_managers.copy()
    
    def apply_camera_settings(
        self,
        camera_id: str,
        width: int,
        height: int,
        fps: float,
        format: str
    ) -> bool:
        """Apply settings to an open camera."""
        if camera_id not in self.camera_managers:
            return False
        
        manager = self.camera_managers[camera_id]
        return manager.apply_settings(width, height, fps, format)
    
    def verify_camera_settings(
        self,
        camera_id: str,
        width: int,
        height: int,
        fps: float,
        format: str
    ) -> Dict[str, Any]:
        """Verify camera settings."""
        if camera_id not in self.camera_managers:
            return {
                "verified": False,
                "reason": "Camera not open"
            }
        
        manager = self.camera_managers[camera_id]
        return manager.verify_settings(width, height, fps, format)
    
    def apply_control_settings(
        self,
        camera_id: str,
        exposure: Optional[int] = None,
        gain: Optional[float] = None,
        saturation: Optional[float] = None
    ) -> bool:
        """Apply control settings (exposure, gain, saturation) immediately to an open camera."""
        if camera_id not in self.camera_managers:
            return False
        
        manager = self.camera_managers[camera_id]
        return manager.apply_control_settings(exposure, gain, saturation)
