"""Camera service for managing multiple cameras."""

import threading
import time
from typing import Dict, Optional, Any
from .camera_manager import CameraManager
from ..adapters.opencv_camera import OpenCVCameraAdapter
from ..adapters.mjpeg_encoder import MJPEGEncoderAdapter
from ..adapters.preprocess_adapter import PreprocessAdapter
from ..adapters.apriltag_detector_adapter import AprilTagDetectorAdapter
from ..domain.vision_pipeline import VisionPipeline
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
        
        # Single capture-only thread: only capture_frame_raw() and enqueue_raw_frame() for all cameras.
        self._capture_thread: Optional[threading.Thread] = None
        self._capture_running = False
        self._capture_lock = threading.Lock()
        
        # Consumer thread: pulls raw from queues, runs pipeline or encodes to JPEG for stream.
        self.vision_pipeline_thread: Optional[threading.Thread] = None
        self.vision_pipeline_running = False
        self.vision_pipeline_thread_lock = threading.Lock()
        
        self.logger.info("[CameraService] Initialized: single capture-only thread, consumer thread (pipeline/encode)")
    
    def open_camera(
        self,
        camera_id: str,
        device_path: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[float] = None,
        format: Optional[str] = None,
        vision_pipeline: Optional[Any] = None,
        stream_only: bool = False,
    ) -> bool:
        """Open a camera.
        
        If width/height/fps/format are not provided, loads from saved config.
        If stream_only is True, opens without vision pipeline (stream only).
        If camera is already open but config use_case changed (e.g. to apriltag), close and reopen so Y-plane/grayscale applies.
        """
        camera_config = self.camera_config_service.get_camera_config(camera_id) or {}
        if camera_id in self.camera_managers and self.camera_managers[camera_id].is_open():
            manager = self.camera_managers[camera_id]
            config_use_case = camera_config.get('use_case', 'stream_only')
            if not stream_only and vision_pipeline is None and getattr(manager, 'use_case', None) != config_use_case:
                self.logger.info(f"[CameraService] Camera {camera_id} use_case changed to {config_use_case}, reopening for Y-plane/grayscale")
                self.close_camera(camera_id)
            else:
                self.logger.warning(f"[CameraService] Camera {camera_id} already open")
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
        
        # use_case: from config when not stream_only (saved apriltag → grayscale); stream_only or vision_pipeline override
        if vision_pipeline is not None:
            use_case = 'vision_pipeline'
            self.logger.info(f"[CameraService] Using custom vision pipeline for camera {camera_id}")
        else:
            use_case = 'stream_only' if stream_only else camera_config.get('use_case', 'stream_only')
            vision_pipeline = None
            if use_case == 'apriltag':
                self.logger.info(f"[CameraService] Camera {camera_id} use_case=apriltag from config (Y-only/grayscale)")

        # Create manager with use_case and vision_pipeline
        manager = CameraManager(
            camera_adapter,
            encoder,
            self.logger,
            use_case=use_case,
            vision_pipeline=vision_pipeline
        )
        
        # Open camera. Phase 1: apriltag = try GREY (Y-only) first; fallback to config format.
        try:
            if use_case == 'apriltag':
                if manager.open(device_path, width, height, fps, 'GREY'):
                    actual = manager.camera_port.get_actual_settings() if manager.is_open() else {}
                    if (actual.get('width') or 0) > 0 and (actual.get('height') or 0) > 0:
                        format = 'GREY'
                        self.logger.info(f"[CameraService] Camera {camera_id} opened with GREY (Y-only)")
                    else:
                        manager.close()
                        if not manager.open(device_path, width, height, fps, format):
                            self.logger.error(f"[CameraService] Camera {camera_id} open failed (device_path={device_path})")
                            return False
                        self.logger.info(f"[CameraService] Camera {camera_id} GREY produced no resolution, using {format}")
                else:
                    if manager.camera_port.is_open():
                        manager.close()
                    if not manager.open(device_path, width, height, fps, format):
                        self.logger.error(f"[CameraService] Camera {camera_id} open failed (device_path={device_path})")
                        return False
                    self.logger.info(f"[CameraService] Camera {camera_id} GREY not supported, using {format}")
            else:
                if not manager.open(device_path, width, height, fps, format):
                    self.logger.error(f"[CameraService] Camera {camera_id} open failed (device_path={device_path})")
                    return False
        except Exception as e:
            self.logger.error(f"[CameraService] Camera {camera_id} open error: {e}", exc_info=True)
            return False
        
        # Store manager
        self.camera_managers[camera_id] = manager
        self.logger.info(
            f"[CameraService] open_camera: stored manager for {camera_id} camera_managers keys={list(self.camera_managers.keys())} "
            f"use_case={getattr(manager, 'use_case', '?')} vision_pipeline={manager.vision_pipeline is not None}"
        )

        # Verify settings after opening
        verification = manager.verify_settings(width, height, fps, format)
        if not verification.get("verified"):
            self.logger.warning(
                f"[CameraService] Camera {camera_id} opened but settings mismatch: "
                f"expected {width}x{height}@{fps}fps, got {verification.get('actual', {})}"
            )
        
        # Start single capture-only thread if not already running
        self._ensure_capture_thread_running()
        # Start consumer thread (pipeline + encode for stream_only)
        self._ensure_vision_pipeline_thread_running()
        
        self.logger.info(f"[CameraService] Camera {camera_id} opened successfully")
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
        with self._capture_lock:
            if len(self.camera_managers) == 0:
                self._stop_capture_thread()
        # Stop consumer thread if no cameras remain
        if len(self.camera_managers) == 0:
            self._stop_vision_pipeline_thread()
        
        self.logger.info(f"[CameraService] Camera {camera_id} closed")
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
        """Start the single capture-only thread (only capture + enqueue raw; no conversion, no encode)."""
        with self._capture_lock:
            if not self._capture_running and len(self.camera_managers) > 0:
                self._capture_running = True
                self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
                self._capture_thread.start()
                self.logger.info("[CameraService] Single capture-only thread started (all cameras)")
    
    def _stop_capture_thread(self) -> None:
        """Stop the single capture-only thread."""
        if self._capture_running:
            self._capture_running = False
            if self._capture_thread:
                self._capture_thread.join(timeout=2.0)
                self._capture_thread = None
            self.logger.info("[CameraService] Capture-only thread stopped")
    
    def _capture_loop(self) -> None:
        """Single thread: only capture and enqueue raw for all cameras. No conversion, no encode."""
        self.logger.info("[CameraService] Capture loop started - capture only, no processing")
        while self._capture_running:
            with self._capture_lock:
                cameras = list(self.camera_managers.items())
            if not cameras:
                time.sleep(0.1)
                continue
            for camera_id, manager in cameras:
                if not self._capture_running:
                    break
                if not manager.camera_port.is_open():
                    continue
                try:
                    raw_frame = manager.camera_port.capture_frame_raw()
                    if raw_frame is not None:
                        manager.enqueue_raw_frame(raw_frame)
                    else:
                        with manager.metrics_lock:
                            manager.frames_dropped += 1
                except Exception as e:
                    self.logger.error(f"[CameraService] Capture error for {camera_id}: {e}")
                    with manager.metrics_lock:
                        manager.frames_dropped += 1
        self.logger.info("[CameraService] Capture loop stopped")
    
    def _ensure_vision_pipeline_thread_running(self) -> None:
        """Ensure the consumer thread is running (pipeline + encode for stream_only)."""
        with self.vision_pipeline_thread_lock:
            if not self.vision_pipeline_running and len(self.camera_managers) > 0:
                self.vision_pipeline_running = True
                self.vision_pipeline_thread = threading.Thread(
                    target=self._vision_pipeline_loop, daemon=True
                )
                self.vision_pipeline_thread.start()
                self.logger.info("[CameraService] Consumer thread started (pipeline + encode)")
    
    def _stop_vision_pipeline_thread(self) -> None:
        """Stop the vision pipeline processing thread."""
        if self.vision_pipeline_running:
            self.vision_pipeline_running = False
            if self.vision_pipeline_thread:
                self.vision_pipeline_thread.join(timeout=2.0)
                self.vision_pipeline_thread = None
            self.logger.info("Vision pipeline processing thread stopped")
    
    def _vision_pipeline_loop(self) -> None:
        """Consumer thread: pull raw from each camera's queue; run pipeline or encode to JPEG for stream."""
        import cv2
        from ..adapters.gpu_frame_encoder import encode_frame_to_jpeg
        self.logger.info("[CameraService] Consumer loop started (pipeline + encode for all cameras)")
        while self.vision_pipeline_running:
            processed_any = False
            with self.vision_pipeline_thread_lock:
                if not self.vision_pipeline_running:
                    break
                cameras = [
                    (camera_id, manager)
                    for camera_id, manager in self.camera_managers.items()
                    if manager.is_open()
                ]
            if not cameras:
                time.sleep(0.1)
                continue
            for camera_id, manager in cameras:
                if not self.vision_pipeline_running:
                    break
                try:
                    if manager.vision_pipeline and manager.use_case == "vision_pipeline":
                        if manager.process_vision_pipeline():
                            processed_any = True
                    else:
                        # stream_only or apriltag: get raw, convert if apriltag, encode to JPEG
                        raw_frame = manager.get_raw_frame(timeout=0.0)
                        if raw_frame is not None:
                            processed_any = True
                            if manager.use_case == "apriltag" and len(raw_frame.shape) == 3:
                                gray = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2GRAY)
                                frame_to_encode = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                            else:
                                frame_to_encode = raw_frame
                            frame_data = encode_frame_to_jpeg(frame_to_encode, quality=85)
                            if frame_data:
                                with manager.frame_queue_lock:
                                    manager.frame_queue.append(frame_data)
                                with manager.metrics_lock:
                                    manager.frames_captured += 1
                                    manager.last_frame_time = time.time()
                except Exception as e:
                    self.logger.error(f"[CameraService] Consumer error for {camera_id}: {e}")
            if not processed_any:
                time.sleep(0.01)
        self.logger.info("[CameraService] Consumer loop stopped")