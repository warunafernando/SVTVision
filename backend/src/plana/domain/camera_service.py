"""Camera service for managing multiple cameras."""

import threading
import time
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
        
        # Single capture thread for all cameras
        self.capture_thread: Optional[threading.Thread] = None
        self.capture_running = False
        self.capture_thread_lock = threading.Lock()
        
        self.logger.info("CameraService initialized with single-threaded capture")
    
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
        
        # Get use_case from config (default to 'apriltag')
        camera_config = self.camera_config_service.get_camera_config(camera_id) or {}
        use_case = camera_config.get('use_case', 'apriltag')
        
        # Create manager with use_case
        manager = CameraManager(camera_adapter, encoder, self.logger, use_case=use_case)
        
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
        
        # Start single capture thread if not already running
        self._ensure_capture_thread_running()
        
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
        
        # Stop capture thread if no cameras remain
        with self.capture_thread_lock:
            if len(self.camera_managers) == 0:
                self._stop_capture_thread()
        
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
    
    def _ensure_capture_thread_running(self) -> None:
        """Ensure the single capture thread is running."""
        with self.capture_thread_lock:
            if not self.capture_running and len(self.camera_managers) > 0:
                self.capture_running = True
                self.capture_thread = threading.Thread(target=self._single_capture_loop, daemon=True)
                self.capture_thread.start()
                self.logger.info("Single capture thread started for all cameras")
    
    def _stop_capture_thread(self) -> None:
        """Stop the single capture thread."""
        if self.capture_running:
            self.capture_running = False
            if self.capture_thread:
                self.capture_thread.join(timeout=2.0)
                self.capture_thread = None
            self.logger.info("Single capture thread stopped")
    
    def _single_capture_loop(self) -> None:
        """Single capture loop that iterates over all open cameras.
        
        This is the only capture thread - it loops through all cameras
        and captures frames for each one into their respective queues.
        """
        self.logger.info("Single capture loop started - processing all cameras")
        
        iteration_count = 0
        
        while self.capture_running:
            iteration_start = time.time()
            iteration_count += 1
            
            # Get list of camera managers (copy to avoid locking issues)
            with self.capture_thread_lock:
                cameras_to_process = list(self.camera_managers.items())
            
            # If no cameras, sleep briefly and continue
            if not cameras_to_process:
                time.sleep(0.1)
                continue
            
            # Process each camera
            for camera_id, manager in cameras_to_process:
                if not self.capture_running:
                    break
                
                # Capture frame for this camera
                try:
                    manager.capture_frame_to_queue()
                except Exception as e:
                    self.logger.error(f"Error capturing frame for camera {camera_id}: {e}")
            
            # Adaptive sleep: aim for ~30 iterations per second when cameras are present
            # This allows multiple captures per second for each camera
            elapsed = time.time() - iteration_start
            sleep_time = max(0.0, (1.0 / 30.0) - elapsed)  # Target ~30 iterations/sec
            
            if sleep_time > 0:
                time.sleep(sleep_time)
            
            # Log status every 1000 iterations (~33 seconds at 30 iter/sec)
            if iteration_count % 1000 == 0:
                active_cameras = sum(1 for _, m in cameras_to_process if m.is_open())
                self.logger.info(f"Capture loop: {iteration_count} iterations, {active_cameras} active cameras")
        
        self.logger.info("Single capture loop stopped")
