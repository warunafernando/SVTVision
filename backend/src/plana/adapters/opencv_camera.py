"""OpenCV-based camera adapter implementing CameraPort."""

import cv2
import numpy as np
from typing import Optional
from ..ports.camera_port import CameraPort
from ..services.logging_service import LoggingService


class OpenCVCameraAdapter(CameraPort):
    """OpenCV-based camera adapter."""
    
    def __init__(self, logger: LoggingService):
        self.logger = logger
        self.cap: Optional[cv2.VideoCapture] = None
        self.device_path: Optional[str] = None
        self.width: int = 0
        self.height: int = 0
        self.fps: float = 0.0
        self.format: str = ''
    
    def open(self, device_path: str, width: int, height: int, fps: float, format: str) -> bool:
        """Open camera device."""
        try:
            # Extract device index from /dev/videoX
            if device_path.startswith('/dev/video'):
                device_index = int(device_path.replace('/dev/video', ''))
            else:
                self.logger.error(f"[Camera] Invalid device path: {device_path}")
                return False
            
            self.cap = cv2.VideoCapture(device_index)
            if not self.cap.isOpened():
                self.logger.error(
                    f"[Camera] Failed to open camera {device_path}. "
                    "Check: 1) User in 'video' group (run: groups). 2) No other app using the device. 3) Device exists (ls -la /dev/video0)."
                )
                return False
            
            # Set camera properties
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.cap.set(cv2.CAP_PROP_FPS, fps)
            
            # Set format. Phase 1: GREY = Y-only (grayscale) for apriltag use_case.
            if format == 'MJPG':
                self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            elif format == 'YUYV':
                self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'YUYV'))
            elif format == 'GREY':
                self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'GREY'))
            
            # Verify actual settings
            actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
            
            self.device_path = device_path
            self.width = actual_width
            self.height = actual_height
            self.fps = actual_fps
            self.format = format
            
            self.logger.info(
                f"[Camera] Opened camera {device_path}: "
                f"{actual_width}x{actual_height} @ {actual_fps:.2f}fps ({format})"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"[Camera] Error opening camera {device_path}: {e}")
            if self.cap:
                self.cap.release()
                self.cap = None
            return False
    
    def close(self) -> None:
        """Close camera device."""
        if self.cap:
            self.cap.release()
            self.cap = None
            self.device_path = None
            self.logger.info("[Camera] Closed camera")
    
    def is_open(self) -> bool:
        """Check if camera is open."""
        return self.cap is not None and self.cap.isOpened()
    
    def capture_frame(self, grayscale: bool = False) -> Optional[bytes]:
        """Capture a single frame and return as JPEG bytes.
        
        Args:
            grayscale: If True, convert frame to grayscale before encoding
        """
        if not self.is_open():
            return None
        
        try:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                return None
            
            # Convert to grayscale if requested
            if grayscale:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                # Convert grayscale to BGR format for JPEG encoding (same result but ensures 3 channels)
                frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            
            # Encode as JPEG (GPU when available)
            from .gpu_frame_encoder import encode_frame_to_jpeg
            jpeg_bytes = encode_frame_to_jpeg(frame, quality=85)
            if not jpeg_bytes:
                return None
            return jpeg_bytes
            
        except Exception as e:
            self.logger.debug(f"[Camera] Error capturing frame: {e}")
            return None
    
    def capture_frame_raw(self) -> Optional[np.ndarray]:
        """Capture a single raw frame as numpy array.
        
        Returns:
            Raw frame data as numpy array (BGR format), or None if capture failed
        """
        if not self.is_open():
            return None
        
        try:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                return None
            return frame
            
        except Exception as e:
            self.logger.debug(f"[Camera] Error capturing raw frame: {e}")
            return None
    
    def get_actual_settings(self) -> dict:
        """Get actual camera settings."""
        if not self.is_open():
            return {
                "width": 0,
                "height": 0,
                "fps": 0.0,
                "format": ""
            }
        
        return {
            "width": int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps": self.cap.get(cv2.CAP_PROP_FPS),
            "format": self.format
        }
    
    def apply_settings(self, width: int, height: int, fps: float, format: str) -> bool:
        """Apply camera settings to an already-open camera."""
        if not self.is_open():
            return False
        
        try:
            # Set camera properties
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.cap.set(cv2.CAP_PROP_FPS, fps)
            
            # Set format
            if format == 'MJPG':
                self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            elif format == 'YUYV':
                self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'YUYV'))
            elif format == 'GREY':
                self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'GREY'))
            
            # Update stored values
            actual_settings = self.get_actual_settings()
            self.width = actual_settings["width"]
            self.height = actual_settings["height"]
            self.fps = actual_settings["fps"]
            self.format = format
            
            self.logger.info(
                f"Applied settings: {actual_settings['width']}x{actual_settings['height']} @ "
                f"{actual_settings['fps']:.2f}fps ({format})"
            )
            return True
            
        except Exception as e:
            self.logger.error(f"[Camera] Error applying settings: {e}")
            return False
    
    def apply_control_settings(self, exposure: Optional[int] = None, gain: Optional[float] = None, saturation: Optional[float] = None) -> bool:
        """Apply camera control settings (exposure, gain, saturation)."""
        if not self.is_open():
            return False
        
        try:
            if exposure is not None:
                # OpenCV exposure values: negative = auto, positive = manual
                # Typical range: -13 (auto) to -1 (very low) or positive values
                # Convert from 1-100 scale to OpenCV scale
                # Lower values = more exposure (brighter), higher = less exposure (darker)
                # For manual mode, we typically use negative values where -13 is auto and -1 is very low exposure
                # Let's map 1-100 to -13 to -1
                cv_exposure = -13 + (exposure - 1) * 12 / 99  # Map 1->-13, 100->-1
                self.cap.set(cv2.CAP_PROP_EXPOSURE, cv_exposure)
                self.logger.debug(f"Set exposure to {exposure} (cv2 value: {cv_exposure})")
            
            if gain is not None:
                # OpenCV gain is typically 0-100 or similar
                # Map 0-10 to 0-100
                cv_gain = gain * 10
                self.cap.set(cv2.CAP_PROP_GAIN, cv_gain)
                self.logger.debug(f"[Camera] Set gain to {gain} (cv2 value: {cv_gain})")
            
            if saturation is not None:
                # OpenCV saturation is typically 0-255
                # Map 0-2 to 0-255
                cv_saturation = saturation * 127.5
                self.cap.set(cv2.CAP_PROP_SATURATION, cv_saturation)
                self.logger.debug(f"[Camera] Set saturation to {saturation} (cv2 value: {cv_saturation})")
            
            return True
            
        except Exception as e:
            self.logger.error(f"[Camera] Error applying control settings: {e}")
            return False
