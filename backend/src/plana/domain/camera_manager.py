"""Camera manager for lifecycle and frame capture management."""

import queue
import threading
import time
import cv2
import numpy as np
from collections import deque
from typing import Optional, Dict, Any
from ..ports.camera_port import CameraPort
from ..ports.stream_encoder_port import StreamEncoderPort
from ..services.logging_service import LoggingService
from .vision_pipeline import VisionPipeline


class CameraManager:
    """Manages camera lifecycle and frame capture."""
    
    def __init__(
        self,
        camera_port: CameraPort,
        encoder: StreamEncoderPort,
        logger: LoggingService,
        use_case: str = 'stream_only',
        vision_pipeline: Optional[VisionPipeline] = None
    ):
        self.camera_port = camera_port
        self.encoder = encoder
        self.logger = logger
        self.use_case = use_case  # stream_only or vision_pipeline
        self.vision_pipeline = vision_pipeline  # Vision pipeline for processing stages
        
        self.device_path: Optional[str] = None
        self.width: int = 0
        self.height: int = 0
        self.fps: float = 0.0
        self.format: str = ''
        
        # Bounded frame queue for processed/JPEG frames (streaming UI)
        self.frame_queue: deque = deque(maxlen=10)
        self.frame_queue_lock = threading.Lock()
        
        # Per-camera queue of 1: latest raw frame only. Camera manager thread puts; camera source (pipeline) gets.
        self.raw_frame_queue: queue.Queue = queue.Queue(maxsize=1)
        
        # Metrics
        self.frames_captured = 0
        self.frames_dropped = 0
        self.last_frame_time = 0.0
        self.metrics_lock = threading.Lock()
        
        self.logger.info("[CameraManager] Initialized")
    
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
            self.logger.warning("[CameraManager] Camera already open")
            return False
        
        if not self.camera_port.open(device_path, width, height, fps, format):
            return False
        
        # Store settings
        self.device_path = device_path
        self.width = width
        self.height = height
        self.fps = fps
        self.format = format
        
        # Clear queues
        with self.frame_queue_lock:
            self.frame_queue.clear()
        while True:
            try:
                self.raw_frame_queue.get_nowait()
            except queue.Empty:
                break
        # Reset metrics
        with self.metrics_lock:
            self.frames_captured = 0
            self.frames_dropped = 0
            self.last_frame_time = 0.0
        
        # Note: Capture is now handled by a single thread in CameraService
        # No need to start individual capture threads here
        
        self.logger.info(f"[CameraManager] Camera opened: {device_path}")
        return True
    
    def close(self) -> None:
        """Close camera."""
        # Close camera
        if self.camera_port.is_open():
            self.camera_port.close()
        
        # Clear queues
        with self.frame_queue_lock:
            self.frame_queue.clear()
        while True:
            try:
                self.raw_frame_queue.get_nowait()
            except queue.Empty:
                break
        self.device_path = None
        self.logger.info("[CameraManager] Camera closed")
    
    def is_open(self) -> bool:
        """Check if camera is open."""
        return self.camera_port.is_open()
    
    def get_latest_frame(self, stage: str = "raw") -> Optional[bytes]:
        """Get latest frame from queue for a specific stage.
        
        Args:
            stage: Stage name ("raw", "preprocess", "detect_overlay")
        
        Returns:
            Latest frame as JPEG bytes, or None if not available
        """
        # If vision pipeline is available, get from pipeline
        if self.vision_pipeline and stage != "raw":
            stage_frame = self.vision_pipeline.get_latest_frame(stage)
            if stage_frame:
                return stage_frame.get_jpeg_bytes()
            return None
        
        # For raw stage, get from frame queue
        if stage == "raw":
            with self.frame_queue_lock:
                if self.frame_queue:
                    return self.frame_queue[-1]
        return None
    
    def get_latest_detections(self) -> list:
        """Get latest detections from vision pipeline."""
        if self.vision_pipeline:
            return self.vision_pipeline.get_latest_detections()
        return []
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get capture metrics."""
        with self.metrics_lock:
            current_time = time.time()
            age_ms = (current_time - self.last_frame_time) * 1000 if self.last_frame_time > 0 else 0.0
            
            # Calculate FPS more accurately using frame age
            fps = 0.0
            if self.last_frame_time > 0 and age_ms < 2000:  # If frame is less than 2 seconds old
                # Calculate FPS from frame age (inverse of frame interval)
                if age_ms > 0:
                    calculated_fps = 1000.0 / age_ms
                    # Clamp to reasonable range (not higher than configured FPS, not negative)
                    fps = min(max(calculated_fps, 0.0), self.fps if self.fps > 0 else 100.0)
                else:
                    fps = self.fps if self.fps > 0 else 0.0
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
    
    def enqueue_raw_frame(self, raw_frame: np.ndarray) -> bool:
        """Put latest raw frame into queue of 1. Called by camera manager (capture) thread.
        If queue full, replace with new frame so camera source always gets latest.
        """
        try:
            try:
                self.raw_frame_queue.put_nowait(raw_frame)
            except queue.Full:
                try:
                    self.raw_frame_queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    self.raw_frame_queue.put_nowait(raw_frame)
                except queue.Full:
                    with self.metrics_lock:
                        self.frames_dropped += 1
                    return False
            with self.metrics_lock:
                self.frames_captured += 1
                self.last_frame_time = time.time()
            return True
        except Exception as e:
            self.logger.error(f"[CameraManager] Error enqueueing raw frame: {e}")
            with self.metrics_lock:
                self.frames_dropped += 1
            return False

    def get_raw_frame(self, timeout: Optional[float] = None) -> Optional[np.ndarray]:
        """Get next raw frame from queue. Called by camera source (pipeline); blocks until frame or timeout."""
        try:
            return self.raw_frame_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def process_vision_pipeline(self) -> bool:
        """Process one frame from camera queue through vision pipeline.
        Camera source pulls frame from this camera's queue (of 1); non-blocking get.
        Returns True if a frame was processed, False if queue was empty.
        """
        if not self.vision_pipeline or self.use_case not in ('apriltag', 'vision_pipeline'):
            return False
        raw_frame = self.get_raw_frame(timeout=0.0)
        if raw_frame is None:
            return False
        
        try:
            # Convert raw frame to grayscale for AprilTag cameras
            if len(raw_frame.shape) == 3:
                raw_frame_gray = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2GRAY)
                # Convert to 3-channel for consistency (BGR format but grayscale)
                raw_frame_gray_bgr = cv2.cvtColor(raw_frame_gray, cv2.COLOR_GRAY2BGR)
            else:
                raw_frame_gray_bgr = raw_frame
            
            # Process frame through vision pipeline (pass grayscale version)
            pipeline_result = self.vision_pipeline.process_frame(raw_frame_gray_bgr)
            
            # Store raw frame JPEG in processed frame queue
            if pipeline_result.get("raw"):
                raw_jpeg = pipeline_result["raw"].get_jpeg_bytes()
                with self.frame_queue_lock:
                    was_full = len(self.frame_queue) >= self.frame_queue.maxlen
                    old_frame_count = len(self.frame_queue)
                    self.frame_queue.append(raw_jpeg)
                    
                    if was_full and len(self.frame_queue) == old_frame_count:
                        with self.metrics_lock:
                            self.frames_dropped += 1
            
            return True
        
        except Exception as e:
            self.logger.error(f"[CameraManager] Error processing vision pipeline: {e}")
            with self.metrics_lock:
                self.frames_dropped += 1
            return False
    
    def _process_captured_frame(self, raw_frame: np.ndarray) -> bool:
        """Process a captured raw frame through pipeline and add to queue.
        
        This is separated from capture to reduce blocking between cameras.
        """
        try:
            # If vision pipeline (from Run Pipeline), process with color frame
            if self.vision_pipeline and self.use_case == 'vision_pipeline':
                pipeline_result = self.vision_pipeline.process_frame(raw_frame)
                
                # Store raw frame JPEG (color)
                if pipeline_result.get("raw"):
                    raw_jpeg = pipeline_result["raw"].get_jpeg_bytes()
                    with self.frame_queue_lock:
                        was_full = len(self.frame_queue) >= self.frame_queue.maxlen
                        old_frame_count = len(self.frame_queue)
                        self.frame_queue.append(raw_jpeg)
                        
                        if was_full and len(self.frame_queue) == old_frame_count:
                            with self.metrics_lock:
                                self.frames_dropped += 1
                
                with self.metrics_lock:
                    self.frames_captured += 1
                    self.last_frame_time = time.time()
                
                return True
            else:
                # Stream-only: convert to JPEG and store (color)
                frame_data = self.camera_port.capture_frame(grayscale=False)
                
                if frame_data:
                    with self.frame_queue_lock:
                        was_full = len(self.frame_queue) >= self.frame_queue.maxlen
                        old_frame_count = len(self.frame_queue)
                        self.frame_queue.append(frame_data)
                        
                        if was_full and len(self.frame_queue) == old_frame_count:
                            with self.metrics_lock:
                                self.frames_dropped += 1
                    
                    with self.metrics_lock:
                        self.frames_captured += 1
                        self.last_frame_time = time.time()
                    
                    return True
                else:
                    with self.metrics_lock:
                        self.frames_dropped += 1
                    return False
        
        except Exception as e:
            self.logger.error(f"[CameraManager] Error processing frame: {e}")
            with self.metrics_lock:
                self.frames_dropped += 1
            return False
    
    def capture_frame_to_queue(self) -> bool:
        """Capture a single frame and add it to the queue.
        
        This is called by the single capture thread in CameraService.
        Returns True if frame was captured successfully, False otherwise.
        
        Pipeline flow:
        1. Capture raw frame (numpy array)
        2. If vision pipeline exists (use_case is 'vision_pipeline'):
           - Process through pipeline and store result frames
        3. Otherwise (stream_only):
           - Convert to JPEG and store in raw queue (legacy behavior)
        """
        if not self.camera_port.is_open():
            return False
        
        try:
            # Capture raw frame as numpy array
            raw_frame = self.camera_port.capture_frame_raw()
            
            if raw_frame is None:
                with self.metrics_lock:
                    self.frames_dropped += 1
                return False
            
            # If vision pipeline (from Run Pipeline), process with color frame
            if self.vision_pipeline and self.use_case == 'vision_pipeline':
                pipeline_result = self.vision_pipeline.process_frame(raw_frame)
                
                # Store raw frame JPEG (color)
                if pipeline_result.get("raw"):
                    raw_jpeg = pipeline_result["raw"].get_jpeg_bytes()
                    with self.frame_queue_lock:
                        was_full = len(self.frame_queue) >= self.frame_queue.maxlen
                        old_frame_count = len(self.frame_queue)
                        self.frame_queue.append(raw_jpeg)
                        
                        if was_full and len(self.frame_queue) == old_frame_count:
                            with self.metrics_lock:
                                self.frames_dropped += 1
                
                with self.metrics_lock:
                    self.frames_captured += 1
                    self.last_frame_time = time.time()
                
                return True
            else:
                # Stream-only: convert to JPEG and store (color)
                frame_data = self.camera_port.capture_frame(grayscale=False)
                
                if frame_data:
                    with self.frame_queue_lock:
                        was_full = len(self.frame_queue) >= self.frame_queue.maxlen
                        old_frame_count = len(self.frame_queue)
                        self.frame_queue.append(frame_data)
                        
                        if was_full and len(self.frame_queue) == old_frame_count:
                            with self.metrics_lock:
                                self.frames_dropped += 1
                    
                    with self.metrics_lock:
                        self.frames_captured += 1
                        self.last_frame_time = time.time()
                    
                    return True
                else:
                    with self.metrics_lock:
                        self.frames_dropped += 1
                    return False
        
        except Exception as e:
            self.logger.error(f"[CameraManager] Error capturing frame: {e}")
            with self.metrics_lock:
                self.frames_dropped += 1
            return False
