"""Camera service for managing multiple cameras."""

import threading
import time
from typing import Dict, Optional, Any
from .camera_manager import CameraManager
from ..adapters.opencv_camera import OpenCVCameraAdapter
from ..adapters.mjpeg_encoder import MJPEGEncoderAdapter
from ..adapters.preprocess_adapter import PreprocessAdapter
from ..adapters.apriltag_detector_adapter import AprilTagDetectorAdapter

try:
    from ..adapters.gpu_preprocess_adapter import GpuPreprocessAdapter
    _GPU_PREPROCESS_AVAILABLE = True
except ImportError:
    GpuPreprocessAdapter = None
    _GPU_PREPROCESS_AVAILABLE = False
from ..domain.vision_pipeline import VisionPipeline
from ..domain.apriltag_timed_stages import (
    ApriltagTimedPreprocessStage,
    ApriltagTimedDetectStage,
    ApriltagTimedOverlayStage,
)
from ..domain.apriltag_pipeline_metrics_proxy import ApriltagPipelineMetricsProxy

APRILTAG_PIPELINE_LOG = "[AprilTag pipeline]"
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
                fps = fps or res.get("fps", 50.0)
                format = format or res.get("format", "YUYV")
            else:
                # Defaults (50 fps to match typical vision cameras; was 30)
                width = width or 640
                height = height or 480
                fps = fps or 50.0
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
                # Build default AprilTag pipeline (preprocess → detect → overlay). Use GPU preprocess when available.
                try:
                    preprocessor = GpuPreprocessAdapter(self.logger) if _GPU_PREPROCESS_AVAILABLE and GpuPreprocessAdapter else PreprocessAdapter(self.logger)
                    if _GPU_PREPROCESS_AVAILABLE and GpuPreprocessAdapter:
                        self.logger.info(f"{APRILTAG_PIPELINE_LOG} Using GpuPreprocessAdapter for {camera_id}")
                    # AprilTag: feed grayscale (not thresholded) into detector to avoid false positives.
                    try:
                        preprocessor.set_config({"output_type": "grayscale", "blur_kernel_size": 3})
                    except Exception:
                        pass
                    detector_backend = str(camera_config.get("detector_backend", "cpu")).lower()
                    tag_detector = None
                    if detector_backend == "cuda":
                        try:
                            from ..adapters.cuda_apriltag_detector_adapter import CudaAprilTagDetectorAdapter
                            tag_detector = CudaAprilTagDetectorAdapter(self.logger, family="tag36h11")
                            self.logger.info(f"{APRILTAG_PIPELINE_LOG} Using CUDA AprilTag detector for {camera_id}")
                        except Exception as e:
                            self.logger.warning(f"{APRILTAG_PIPELINE_LOG} CUDA detector unavailable, falling back to CPU for {camera_id}: {e}")
                            tag_detector = None
                    if tag_detector is None:
                        tag_detector = AprilTagDetectorAdapter(self.logger, family="tag36h11")
                    # AprilTag pipeline only: use timed stage wrappers (no changes to VisionPipeline core).
                    stages = [
                        ApriltagTimedPreprocessStage(preprocessor),
                        ApriltagTimedDetectStage(tag_detector),
                        ApriltagTimedOverlayStage(tag_detector),
                    ]
                    pipeline = VisionPipeline(preprocessor, tag_detector, self.logger, stages=stages)
                    # AprilTag pipeline only: expose detect breakdown alongside stage timings.
                    vision_pipeline = ApriltagPipelineMetricsProxy(pipeline, tag_detector)
                    self.logger.info(f"{APRILTAG_PIPELINE_LOG} Built default pipeline for camera {camera_id}")
                except Exception as e:
                    self.logger.error(f"{APRILTAG_PIPELINE_LOG} Failed to build pipeline for {camera_id}: {e}", exc_info=True)

        # Create manager with use_case and vision_pipeline
        manager = CameraManager(
            camera_adapter,
            encoder,
            self.logger,
            use_case=use_case,
            vision_pipeline=vision_pipeline
        )
        
        # Open camera.
        # Default behavior: for apriltag, try GREY (Y-only) first for performance.
        # Exception: if config explicitly requests MJPG (often required to hit high FPS due to USB bandwidth),
        # open MJPG directly.
        try:
            if use_case == 'apriltag':
                if str(format).upper() == "MJPG":
                    if not manager.open(device_path, width, height, fps, 'MJPG'):
                        self.logger.error(f"[CameraService] Camera {camera_id} open failed (device_path={device_path})")
                        return False
                    self.logger.info(f"[CameraService] Camera {camera_id} opened with MJPG (compressed for bandwidth)")
                elif manager.open(device_path, width, height, fps, 'GREY'):
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

    def get_apriltag_status(self) -> Dict[str, Any]:
        """Return whether AprilTag pipeline is running, which cameras have it attached, pipeline metrics (e.g. FPS), and target FPS (camera config)."""
        cameras_with_pipeline = []
        pipeline_metrics = None
        target_fps = None  # configured camera FPS (e.g. 50) so UI can show "pipeline FPS vs target"
        for camera_id, manager in self.camera_managers.items():
            if getattr(manager, "use_case", None) != "apriltag":
                continue
            if manager.is_open() and manager.vision_pipeline is not None:
                cameras_with_pipeline.append(camera_id)
                if pipeline_metrics is None:
                    pipeline_metrics = manager.vision_pipeline.get_metrics()
                if target_fps is None and getattr(manager, "fps", 0) > 0:
                    target_fps = manager.fps
        out = {"running": len(cameras_with_pipeline) > 0, "cameras": cameras_with_pipeline}
        if pipeline_metrics is not None:
            out["metrics"] = pipeline_metrics
        if target_fps is not None:
            out["target_fps"] = target_fps
        return out

    def start_apriltag_pipeline(self) -> Dict[str, Any]:
        """Attach default AprilTag pipeline to all open cameras that have use_case=apriltag in config."""
        started = []
        for camera_id, manager in self.camera_managers.items():
            if not manager.is_open():
                continue
            cfg = self.camera_config_service.get_camera_config(camera_id) or {}
            if cfg.get("use_case") != "apriltag":
                continue
            if manager.vision_pipeline is not None:
                continue
            try:
                preprocessor = GpuPreprocessAdapter(self.logger) if _GPU_PREPROCESS_AVAILABLE and GpuPreprocessAdapter else PreprocessAdapter(self.logger)
                try:
                    preprocessor.set_config({"output_type": "grayscale", "blur_kernel_size": 3})
                except Exception:
                    pass
                detector_backend = str(cfg.get("detector_backend", "cpu")).lower()
                tag_detector = None
                if detector_backend == "cuda":
                    try:
                        from ..adapters.cuda_apriltag_detector_adapter import CudaAprilTagDetectorAdapter
                        tag_detector = CudaAprilTagDetectorAdapter(self.logger, family="tag36h11")
                        self.logger.info(f"{APRILTAG_PIPELINE_LOG} Using CUDA AprilTag detector for {camera_id}")
                    except Exception as e:
                        self.logger.warning(f"{APRILTAG_PIPELINE_LOG} CUDA detector unavailable, falling back to CPU for {camera_id}: {e}")
                        tag_detector = None
                if tag_detector is None:
                    tag_detector = AprilTagDetectorAdapter(self.logger, family="tag36h11")
                stages = [
                    ApriltagTimedPreprocessStage(preprocessor),
                    ApriltagTimedDetectStage(tag_detector),
                    ApriltagTimedOverlayStage(tag_detector),
                ]
                pipeline = VisionPipeline(preprocessor, tag_detector, self.logger, stages=stages)
                manager.vision_pipeline = ApriltagPipelineMetricsProxy(pipeline, tag_detector)
                started.append(camera_id)
                self.logger.info(f"{APRILTAG_PIPELINE_LOG} Started pipeline for camera {camera_id}")
            except Exception as e:
                self.logger.error(f"{APRILTAG_PIPELINE_LOG} Failed to start for {camera_id}: {e}", exc_info=True)
        return {"ok": True, "started": started}

    def stop_apriltag_pipeline(self) -> Dict[str, Any]:
        """Detach AprilTag pipeline from all managers that have use_case=apriltag."""
        stopped = []
        for camera_id, manager in self.camera_managers.items():
            if getattr(manager, "use_case", None) != "apriltag":
                continue
            if manager.vision_pipeline is None:
                continue
            manager.vision_pipeline = None
            stopped.append(camera_id)
            self.logger.info(f"{APRILTAG_PIPELINE_LOG} Stopped pipeline for camera {camera_id}")
        return {"ok": True, "stopped": stopped}

    def get_apriltag_settings(self) -> Dict[str, Any]:
        """Return AprilTag detector settings (quad_decimate, nthreads) from first pipeline."""
        for manager in self.camera_managers.values():
            if getattr(manager, "use_case", None) != "apriltag" or manager.vision_pipeline is None:
                continue
            cfg = manager.vision_pipeline.get_tag_detector_config()
            if cfg:
                return cfg
        return {"quad_decimate": AprilTagDetectorAdapter.DEFAULT_QUAD_DECIMATE, "nthreads": AprilTagDetectorAdapter.DEFAULT_NTHREADS}

    def apply_apriltag_settings(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply quad_decimate, nthreads to all AprilTag pipelines. Returns {ok, applied}."""
        applied = []
        for camera_id, manager in self.camera_managers.items():
            if getattr(manager, "use_case", None) != "apriltag" or manager.vision_pipeline is None:
                continue
            if manager.vision_pipeline.update_tag_detector_config(config):
                applied.append(camera_id)
        return {"ok": True, "applied": applied}
    
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
        from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
        self.logger.info("[CameraService] Capture loop started - capture only, no processing")
        # Capture per camera continuously in parallel.
        # Important: do NOT "lock-step" (wait for all cameras each cycle) because the slowest camera
        # would throttle all others. Instead, resubmit a capture for each camera as soon as its read completes.
        executor = ThreadPoolExecutor(max_workers=4)
        try:
            futures = {}  # future -> (camera_id, manager)
            last_refresh = 0.0

            def refresh_active_cameras() -> None:
                nonlocal last_refresh
                now = time.time()
                if now - last_refresh < 0.25:
                    return
                last_refresh = now
                with self._capture_lock:
                    active = {
                        camera_id: manager
                        for camera_id, manager in self.camera_managers.items()
                        if manager.camera_port.is_open()
                    }
                # Submit initial capture for newly-active cameras.
                active_ids = set(active.keys())
                in_flight_ids = {cid for (_, (cid, _)) in futures.items()}
                for cid, mgr in active.items():
                    if cid not in in_flight_ids:
                        futures[executor.submit(mgr.camera_port.capture_frame_raw)] = (cid, mgr)
                # Best-effort: drop bookkeeping for cameras that disappeared.
                for fut, (cid, _) in list(futures.items()):
                    if cid not in active_ids and fut.done():
                        futures.pop(fut, None)

            while self._capture_running:
                refresh_active_cameras()
                if not futures:
                    time.sleep(0.05)
                    continue

                done, _ = wait(set(futures.keys()), timeout=0.02, return_when=FIRST_COMPLETED)
                if not done:
                    continue

                for fut in done:
                    cid, mgr = futures.pop(fut, (None, None))
                    if cid is None or mgr is None:
                        continue
                    if not self._capture_running or not mgr.camera_port.is_open():
                        continue
                    try:
                        raw_frame = fut.result()
                        if raw_frame is not None:
                            mgr.enqueue_raw_frame(raw_frame)
                        else:
                            with mgr.metrics_lock:
                                mgr.frames_dropped += 1
                    except Exception as e:
                        self.logger.error(f"[CameraService] Capture error for {cid}: {e}")
                        with mgr.metrics_lock:
                            mgr.frames_dropped += 1
                        time.sleep(0.001)
                    # Resubmit next capture for this camera immediately (continuous per-camera loop).
                    if self._capture_running and mgr.camera_port.is_open():
                        futures[executor.submit(mgr.camera_port.capture_frame_raw)] = (cid, mgr)
        finally:
            self.logger.info("[CameraService] Capture loop stopped")
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
    
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
        """Consumer thread: pull raw from each camera's queue; run pipeline or encode for stream (CUDA when available).
        For AprilTag/vision_pipeline: pull one frame per camera first, then process all in parallel so each pipeline
        can run at full rate (closer to camera FPS) instead of sequential (~half rate).
        """
        from ..adapters.gpu_frame_encoder import encode_frame_for_stream
        from concurrent.futures import ThreadPoolExecutor, as_completed
        self.logger.info("[CameraService] Consumer loop started (pipeline + stream encode, CUDA when available)")
        # Persistent executor: creating/destroying a pool per loop iteration is expensive and caps FPS.
        executor = ThreadPoolExecutor(max_workers=4)
        try:
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
                # Collect one raw frame per camera that has a pipeline (so we can process in parallel)
                pipeline_work = []
                for camera_id, manager in cameras:
                    if not self.vision_pipeline_running:
                        break
                    try:
                        raw_frame = manager.get_raw_frame(timeout=0.0)
                        if raw_frame is None:
                            continue
                        if manager.vision_pipeline and manager.use_case in ("vision_pipeline", "apriltag"):
                            pipeline_work.append((camera_id, manager, raw_frame))
                        else:
                            # stream_only: encode for stream (CUDA when available)
                            processed_any = True
                            frame_data = encode_frame_for_stream(
                                raw_frame,
                                use_case=manager.use_case or "stream_only",
                                quality=85,
                            )
                            if frame_data:
                                with manager.frame_queue_lock:
                                    manager.frame_queue.append(frame_data)
                                with manager.metrics_lock:
                                    manager.frames_captured += 1
                                    manager.last_frame_time = time.time()
                    except Exception as e:
                        self.logger.error(f"[CameraService] Consumer error for {camera_id}: {e}")
                # Run pipeline for all cameras in parallel
                if pipeline_work:
                    futures = {
                        executor.submit(manager._run_pipeline_on_frame, raw_frame): camera_id
                        for camera_id, manager, raw_frame in pipeline_work
                    }
                    for future in as_completed(futures):
                        try:
                            if future.result():
                                processed_any = True
                        except Exception as e:
                            camera_id = futures[future]
                            self.logger.error(f"[CameraService] Pipeline error for {camera_id}: {e}")
                if not processed_any:
                    time.sleep(0.002)
        finally:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            self.logger.info("[CameraService] Consumer loop stopped")