"""Camera manager for lifecycle and frame capture management."""

import threading
import time
from collections import deque
from typing import Optional, Dict, Any
from ..ports.camera_port import CameraPort
from ..ports.stream_encoder_port import StreamEncoderPort
from ..services.logging_service import LoggingService


class CameraManager:
    """Manages camera lifecycle and frame capture."""
    
    def __init__(
        self,
        camera_port: CameraPort,
        encoder: StreamEncoderPort,
        logger: LoggingService
    ):
        self.camera_port = camera_port
        self.encoder = encoder
        self.logger = logger
        
        self.device_path: Optional[str] = None
        self.width: int = 0
        self.height: int = 0
        self.fps: float = 0.0
        self.format: str = ''
        
        # Bounded frame queue (size=10, drop-oldest)
        # Increased from 3 to 10 to reduce drops at high FPS (50fps)
        self.frame_queue: deque = deque(maxlen=10)
        self.frame_queue_lock = threading.Lock()
        
        # Frame capture thread
        self.capture_thread: Optional[threading.Thread] = None
        self.capture_running = False
        
        # Metrics
        self.frames_captured = 0
        self.frames_dropped = 0
        self.last_frame_time = 0.0
        self.metrics_lock = threading.Lock()
        
        self.logger.info("CameraManager initialized")
    
    def open(
        self,
        device_path: str,
        width: int,
        height: int,
        fps: float,
        format: str
    ) -> bool:
        """Open camera and start capture thread."""
        if self.camera_port.is_open():
            self.logger.warning("Camera already open")
            return False
        
        if not self.camera_port.open(device_path, width, height, fps, format):
            return False
        
        # Store settings
        self.device_path = device_path
        self.width = width
        self.height = height
        self.fps = fps
        self.format = format
        
        # Clear queue
        with self.frame_queue_lock:
            self.frame_queue.clear()
        
        # Reset metrics
        with self.metrics_lock:
            self.frames_captured = 0
            self.frames_dropped = 0
            self.last_frame_time = 0.0
        
        # Start capture thread
        self.capture_running = True
        self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.capture_thread.start()
        
        self.logger.info(f"Camera opened: {device_path}")
        return True
    
    def close(self) -> None:
        """Close camera and stop capture thread."""
        # Stop capture thread
        self.capture_running = False
        if self.capture_thread:
            self.capture_thread.join(timeout=2.0)
            self.capture_thread = None
        
        # Close camera
        if self.camera_port.is_open():
            self.camera_port.close()
        
        # Clear queue
        with self.frame_queue_lock:
            self.frame_queue.clear()
        
        self.device_path = None
        self.logger.info("Camera closed")
    
    def is_open(self) -> bool:
        """Check if camera is open."""
        return self.camera_port.is_open()
    
    def get_latest_frame(self) -> Optional[bytes]:
        """Get latest frame from queue."""
        with self.frame_queue_lock:
            if self.frame_queue:
                return self.frame_queue[-1]
        return None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get capture metrics."""
        with self.metrics_lock:
            current_time = time.time()
            age_ms = (current_time - self.last_frame_time) * 1000 if self.last_frame_time > 0 else 0.0
            
            # Calculate FPS based on frame age
            fps = 0.0
            if self.last_frame_time > 0 and age_ms < 2000:  # If frame is less than 2 seconds old
                # Estimate FPS from frame age
                if age_ms > 0:
                    fps = min(1000.0 / age_ms, self.fps)  # Convert age to approximate FPS
                else:
                    fps = self.fps
            else:
                fps = 0.0
            
            return {
                "frames_captured": self.frames_captured,
                "frames_drops": self.frames_dropped,
                "frames_dropped": self.frames_dropped,  # Both for compatibility
                "fps": round(fps, 1),
                "drops": self.frames_dropped,
                "last_frame_age": int(age_ms),
                "device_path": self.device_path,
                "settings": self.camera_port.get_actual_settings() if self.is_open() else {}
            }
    
    def apply_settings(self, width: int, height: int, fps: float, format: str) -> bool:
        """Apply camera settings and verify.
        
        Returns:
            True if settings applied successfully
        """
        if not self.is_open():
            return False
        
        success = self.camera_port.apply_settings(width, height, fps, format)
        
        if success:
            # Update stored settings
            self.width = width
            self.height = height
            self.fps = fps
            self.format = format
            
            # Update FPS interval for capture loop
            # The loop will pick up the new fps value on next iteration
        
        return success
    
    def verify_settings(self, expected_width: int, expected_height: int, expected_fps: float, expected_format: str) -> Dict[str, Any]:
        """Verify camera settings match expected values.
        
        Returns:
            Dict with verification results
        """
        if not self.is_open():
            return {
                "verified": False,
                "reason": "Camera not open"
            }
        
        actual = self.camera_port.get_actual_settings()
        
        width_match = actual.get("width") == expected_width
        height_match = actual.get("height") == expected_height
        fps_match = abs(actual.get("fps", 0) - expected_fps) < 1.0  # Allow 1 fps tolerance
        format_match = actual.get("format") == expected_format
        
        all_match = width_match and height_match and fps_match and format_match
        
        return {
            "verified": all_match,
            "expected": {
                "width": expected_width,
                "height": expected_height,
                "fps": expected_fps,
                "format": expected_format
            },
            "actual": actual,
            "mismatches": {
                "width": not width_match,
                "height": not height_match,
                "fps": not fps_match,
                "format": not format_match
            }
        }
    
    def apply_control_settings(self, exposure: Optional[int] = None, gain: Optional[float] = None, saturation: Optional[float] = None) -> bool:
        """Apply camera control settings immediately.
        
        Args:
            exposure: Exposure value (1-100)
            gain: Gain value (0-10)
            saturation: Saturation value (0-2)
        
        Returns:
            True if settings applied successfully
        """
        if not self.is_open():
            return False
        
        return self.camera_port.apply_control_settings(exposure, gain, saturation)
    
    def _capture_loop(self) -> None:
        """Frame capture loop running in separate thread."""
        frame_interval = 1.0 / self.fps if self.fps > 0 else 0.033  # Default 30fps
        loop_count = 0
        
        self.logger.info(f"Capture loop started for {self.device_path} at {self.fps} fps")
        
        while self.capture_running and self.camera_port.is_open():
            start_time = time.time()
            loop_count += 1
            
            # Capture frame
            frame_data = self.camera_port.capture_frame()
            
            if frame_data:
                # Frame is already JPEG encoded from OpenCV, just use it directly
                with self.frame_queue_lock:
                    # Check if queue is full (will drop oldest automatically)
                    was_full = len(self.frame_queue) >= self.frame_queue.maxlen
                    old_frame_count = len(self.frame_queue)
                    self.frame_queue.append(frame_data)
                    
                    # Only count as drop if we're pushing out an old frame when queue was already full
                    if was_full and len(self.frame_queue) == old_frame_count:
                        with self.metrics_lock:
                            self.frames_dropped += 1
                
                with self.metrics_lock:
                    self.frames_captured += 1
                    self.last_frame_time = time.time()
                    
                    # Log every 100 frames for debugging
                    if self.frames_captured % 100 == 0:
                        self.logger.info(f"Capture: {self.frames_captured} frames, drops: {self.frames_dropped}, queue: {len(self.frame_queue)}")
            else:
                # Frame capture failed
                with self.metrics_lock:
                    self.frames_dropped += 1
                    if loop_count % 100 == 0:
                        self.logger.warning(f"Frame capture failed (loop #{loop_count}, drops: {self.frames_dropped})")
            
            # Sleep to maintain target FPS
            elapsed = time.time() - start_time
            sleep_time = max(0, frame_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        self.logger.info(f"Capture loop stopped for {self.device_path}")
