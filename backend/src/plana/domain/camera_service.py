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
        
        # Dedicated camera-manager thread: captures from all open cameras and puts latest frame
        # into each camera's queue (of 1). Camera source (pipeline) pulls from these queues.
        self.camera_manager_thread: Optional[threading.Thread] = None
        self.camera_manager_running = False
        self.camera_manager_lock = threading.Lock()
        
        # Vision pipeline thread: pulls frames from camera queues (camera source) and runs pipelines
        self.vision_pipeline_thread: Optional[threading.Thread] = None
        self.vision_pipeline_running = False
        self.vision_pipeline_thread_lock = threading.Lock()
        
        self.logger.info("[CameraService] Initialized: camera-manager thread (queues of 1), vision pipeline thread (camera source pulls)")
    
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
        """
        # Phase 2: pipeline attach is done by VisionPipelineManager; we only open cameras here.
        if camera_id in self.camera_managers and self.camera_managers[camera_id].is_open():
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
        camera_config = self.camera_config_service.get_camera_config(camera_id) or {}
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
        
        # Start dedicated camera-manager thread if not already running
        self._ensure_camera_manager_thread_running()
        
        # Start vision pipeline thread if not already running
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
        
        # Stop camera-manager thread if no cameras remain
        with self.camera_manager_lock:
            if len(self.camera_managers) == 0:
                self._stop_camera_manager_thread()
        
        # Stop vision pipeline thread if no cameras with pipelines remain
        cameras_with_pipelines = sum(1 for m in self.camera_managers.values() 
                                     if hasattr(m, 'vision_pipeline') and m.vision_pipeline)
        if cameras_with_pipelines == 0:
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
    
    def _ensure_camera_manager_thread_running(self) -> None:
        """Ensure the dedicated camera-manager thread is running (feeds queues of 1 for all cameras)."""
        with self.camera_manager_lock:
            if not self.camera_manager_running and len(self.camera_managers) > 0:
                self.camera_manager_running = True
                self.camera_manager_thread = threading.Thread(target=self._camera_manager_loop, daemon=True)
                self.camera_manager_thread.start()
                self.logger.info("[CameraService] Camera-manager thread started (queues of 1 for all cameras)")
    
    def _stop_camera_manager_thread(self) -> None:
        """Stop the dedicated camera-manager thread."""
        if self.camera_manager_running:
            self.camera_manager_running = False
            if self.camera_manager_thread:
                self.camera_manager_thread.join(timeout=2.0)
                self.camera_manager_thread = None
            self.logger.info("[CameraService] Camera-manager thread stopped")
    
    def _camera_manager_loop(self) -> None:
        """Dedicated camera-manager thread: capture from all open cameras and put latest frame
        into each camera's queue (of 1). Camera source (pipeline) connects to these queues and gets frames.
        """
        self.logger.info("[CameraService] Camera-manager loop started - feeding queues of 1 for all cameras")
        iteration_count = 0
        while self.camera_manager_running:
            iteration_start = time.time()
            iteration_count += 1
            with self.camera_manager_lock:
                cameras_to_process = list(self.camera_managers.items())
            if not cameras_to_process:
                time.sleep(0.1)
                continue
            for camera_id, manager in cameras_to_process:
                if not self.camera_manager_running:
                    break
                
                # Capture raw frame quickly and enqueue for vision processing
                try:
                    if manager.camera_port.is_open():
                        raw_frame = manager.camera_port.capture_frame_raw()
                        if raw_frame is not None:
                            # Phase 1: apriltag = Y-only. Convert to grayscale before enqueue/encode.
                            import cv2
                            if manager.use_case == 'apriltag' and len(raw_frame.shape) == 3:
                                gray = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2GRAY)
                                raw_frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
                            # If camera has vision pipeline (apriltag or custom), enqueue for processing
                            if manager.vision_pipeline and manager.use_case in ('apriltag', 'vision_pipeline'):
                                manager.enqueue_raw_frame(raw_frame)
                            else:
                                # No vision pipeline - convert to JPEG directly
                                grayscale = (manager.use_case == 'apriltag')
                                if grayscale and len(raw_frame.shape) == 3:
                                    gray_frame = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2GRAY)
                                    frame_to_encode = cv2.cvtColor(gray_frame, cv2.COLOR_GRAY2BGR)
                                else:
                                    frame_to_encode = raw_frame
                                
                                _, jpeg_bytes = cv2.imencode('.jpg', frame_to_encode, [cv2.IMWRITE_JPEG_QUALITY, 85])
                                if jpeg_bytes is not None:
                                    frame_data = jpeg_bytes.tobytes()
                                    with manager.frame_queue_lock:
                                        manager.frame_queue.append(frame_data)
                                    with manager.metrics_lock:
                                        manager.frames_captured += 1
                                        manager.last_frame_time = time.time()
                                else:
                                    with manager.metrics_lock:
                                        manager.frames_dropped += 1
                        else:
                            with manager.metrics_lock:
                                manager.frames_dropped += 1
                except Exception as e:
                    self.logger.error(f"Error capturing frame for camera {camera_id}: {e}")
                    with manager.metrics_lock:
                        manager.frames_dropped += 1
            
            elapsed = time.time() - iteration_start
            max_fps = 30.0
            for _camera_id, manager in cameras_to_process:
                if manager.is_open():
                    camera_fps = manager.fps if hasattr(manager, 'fps') else 30.0
                    if camera_fps > max_fps:
                        max_fps = camera_fps
            # Each iteration serves one frame per camera; so we need (max_fps * N) iterations/sec for N cameras
            num_cameras = max(1, len(cameras_to_process))
            target_iterations_per_sec = max_fps * 1.2 * num_cameras
            sleep_time = max(0.0, (1.0 / target_iterations_per_sec) - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
            if iteration_count % 1000 == 0:
                active_cameras = sum(1 for _, m in cameras_to_process if m.is_open())
                self.logger.info(f"[CameraService] Camera-manager loop: {iteration_count} iterations, {active_cameras} cameras")
        self.logger.info("[CameraService] Camera-manager loop stopped")
    
    def _ensure_vision_pipeline_thread_running(self) -> None:
        """Ensure the vision pipeline processing thread is running."""
        with self.vision_pipeline_thread_lock:
            if not self.vision_pipeline_running:
                # Check if any cameras have vision pipelines
                has_pipelines = any(
                    hasattr(m, 'vision_pipeline') and m.vision_pipeline
                    for m in self.camera_managers.values()
                )
                if has_pipelines:
                    self.vision_pipeline_running = True
                    self.vision_pipeline_thread = threading.Thread(
                        target=self._vision_pipeline_loop, daemon=True
                    )
                    self.vision_pipeline_thread.start()
                    self.logger.info("[CameraService] Vision pipeline processing thread started")
    
    def _stop_vision_pipeline_thread(self) -> None:
        """Stop the vision pipeline processing thread."""
        if self.vision_pipeline_running:
            self.vision_pipeline_running = False
            if self.vision_pipeline_thread:
                self.vision_pipeline_thread.join(timeout=2.0)
                self.vision_pipeline_thread = None
            self.logger.info("Vision pipeline processing thread stopped")
    
    def _vision_pipeline_loop(self) -> None:
        """Vision pipeline processing thread (camera source).
        Pulls frames from each camera's queue (of 1) and runs the attached vision pipeline.
        """
        self.logger.info("[CameraService] Vision pipeline processing loop started")
        
        while self.vision_pipeline_running:
            processed_any = False
            
            # Get list of camera managers with vision pipelines
            with self.vision_pipeline_thread_lock:
                if not self.vision_pipeline_running:
                    break
                cameras_to_process = [
                    (camera_id, manager)
                    for camera_id, manager in self.camera_managers.items()
                    if manager.is_open() and 
                       hasattr(manager, 'vision_pipeline') and 
                       manager.vision_pipeline and 
                       manager.use_case == 'vision_pipeline'
                ]
            
            # If no cameras with pipelines, wait a bit
            if not cameras_to_process:
                time.sleep(0.1)
                continue
            
            # Process one frame from each camera's raw queue
            for camera_id, manager in cameras_to_process:
                if not self.vision_pipeline_running:
                    break
                
                try:
                    if manager.process_vision_pipeline():
                        processed_any = True
                except Exception as e:
                    self.logger.error(f"[CameraService] Error processing vision pipeline for camera {camera_id}: {e}")
            
            # Small sleep if we didn't process anything (all queues empty)
            if not processed_any:
                time.sleep(0.01)  # 10ms sleep when queues are empty
        
        self.logger.info("[CameraService] Vision pipeline processing loop stopped")