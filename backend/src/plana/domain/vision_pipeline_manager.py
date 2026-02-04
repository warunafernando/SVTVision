"""Vision Pipeline Manager: manages pipeline instances (start/stop/list)."""

import hashlib
import os
import threading
import time
from typing import Dict, Any, List, Optional, Tuple

from .camera_service import CameraService
from .camera_discovery import CameraDiscovery
from .algorithm_store import AlgorithmStore
from .pipeline_instance import PipelineInstance
from .runtime_compiler import compile_graph, GraphValidationError
from .pipeline_builder import build_pipeline_with_taps
from .stream_tap import StreamTap, StreamTapRegistry
from ..services.logging_service import LoggingService


def _normalize_source_type(n: Dict[str, Any]) -> str:
    """Normalize source_type for comparison (video_file, VideoFile, etc.)."""
    return str(n.get("source_type") or n.get("sourceType") or "").strip().lower().replace("_", "")


def _normalize_stage_id(n: Dict[str, Any]) -> str:
    """Normalize stage_id for comparison (some payloads use stage_id for source kind)."""
    return str(n.get("stage_id") or n.get("stageId") or "").strip().lower().replace("_", "")


def _node_name_or_label(n: Dict[str, Any]) -> str:
    """Single string from name/label for source-kind detection."""
    return str(n.get("name") or n.get("label") or n.get("id") or "").strip().lower().replace("_", "").replace(" ", "")


def _is_video_file_source_node(n: Dict[str, Any]) -> bool:
    if _normalize_source_type(n) == "videofile":
        return True
    if _is_source_node(n) and _normalize_stage_id(n) == "videofile":
        return True
    if _is_source_node(n) and "videofile" in _node_name_or_label(n):
        return True
    return False


def _is_image_file_source_node(n: Dict[str, Any]) -> bool:
    if _normalize_source_type(n) == "imagefile":
        return True
    if _is_source_node(n) and _normalize_stage_id(n) == "imagefile":
        return True
    if _is_source_node(n) and ("imagefile" in _node_name_or_label(n) or ("image" in _node_name_or_label(n) and "file" in _node_name_or_label(n))):
        return True
    return False


def _is_source_node(n: Dict[str, Any]) -> bool:
    """True if node is a source (type check case-insensitive)."""
    t = str(n.get("type") or "").strip().lower()
    return t == "source"


def _video_file_source_from_graph(algo: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """If graph has any video_file source with path set, return (node_id, path). Else None."""
    nodes = algo.get("nodes") or []
    for n in nodes:
        if not _is_source_node(n):
            continue
        if not _is_video_file_source_node(n):
            continue
        cfg = n.get("config") or {}
        path = (cfg.get("path") or cfg.get("location") or cfg.get("Location") or "").strip()
        if path:
            return (n.get("id", ""), path)
    return None


def _has_any_video_file_source(algo: Dict[str, Any]) -> bool:
    """True if graph has at least one source that is video_file (path may be empty)."""
    nodes = algo.get("nodes") or []
    for n in nodes:
        if _is_source_node(n) and _is_video_file_source_node(n):
            return True
    return False


def _image_file_source_from_graph(algo: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """If graph has any image_file source with path set, return (node_id, path). Else None."""
    nodes = algo.get("nodes") or []
    for n in nodes:
        if not _is_source_node(n):
            continue
        if not _is_image_file_source_node(n):
            continue
        cfg = n.get("config") or {}
        path = (cfg.get("path") or cfg.get("location") or cfg.get("Location") or "").strip()
        if path:
            return (n.get("id", ""), path)
    return None


def _has_any_image_file_source(algo: Dict[str, Any]) -> bool:
    """True if graph has at least one source that is image_file (path may be empty)."""
    nodes = algo.get("nodes") or []
    for n in nodes:
        if _is_source_node(n) and _is_image_file_source_node(n):
            return True
    return False


# Default search dirs when path from file picker is filename-only (browsers often don't send full path)
_VIDEO_FILE_SEARCH_DIRS = [
    os.getcwd(),
    "/home/svt/Documents",
    os.path.expanduser("~/Documents"),
]


def _resolve_video_file_path(path: str) -> Optional[str]:
    """Resolve path to an existing file. If path is relative/filename-only, try search dirs."""
    path = (path or "").strip()
    if not path:
        return None
    expanded = os.path.expanduser(path)
    if os.path.isabs(expanded) and os.path.isfile(expanded):
        return expanded
    # Relative or filename-only: try search dirs then cwd
    for base in _VIDEO_FILE_SEARCH_DIRS:
        if base:
            candidate = os.path.join(base, os.path.basename(path))
            if os.path.isfile(candidate):
                return candidate
    candidate = os.path.abspath(expanded)
    if os.path.isfile(candidate):
        return candidate
    return None


def _run_video_file_loop(
    instance_id: str,
    path: str,
    vision_pipeline: Any,
    stop_event: threading.Event,
    logger: LoggingService,
) -> None:
    """Read video file and feed frames to pipeline until end or stop."""
    import cv2
    frame_count = 0
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        logger.error(f"[VisionPipelineManager] Video file could not be opened: {path}")
        return
    try:
        fps = max(1.0, cap.get(cv2.CAP_PROP_FPS) or 30.0)
        interval = 1.0 / fps
        while not stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                break
            try:
                vision_pipeline.process_frame(frame)
                frame_count += 1
            except Exception as e:
                logger.warning(f"[VisionPipelineManager] File pipeline process_frame error: {e}")
            time.sleep(interval)
        logger.info(f"[VisionPipelineManager] Video file loop ended for {instance_id} after {frame_count} frames")
    finally:
        cap.release()


def _run_image_file_loop(
    instance_id: str,
    path: str,
    vision_pipeline: Any,
    stop_event: threading.Event,
    logger: LoggingService,
) -> None:
    """Load image and feed it to pipeline in a loop until stop (so StreamTap can show it)."""
    import cv2
    frame = cv2.imread(path)
    if frame is None:
        logger.error(f"[VisionPipelineManager] Image file could not be opened: {path}")
        return
    frame_count = 0
    interval = 1.0 / 10.0  # 10 fps for static image
    try:
        while not stop_event.is_set():
            try:
                vision_pipeline.process_frame(frame.copy())
                frame_count += 1
            except Exception as e:
                logger.warning(f"[VisionPipelineManager] Image pipeline process_frame error: {e}")
            time.sleep(interval)
        logger.info(f"[VisionPipelineManager] Image file loop ended for {instance_id} after {frame_count} frames")
    except Exception as e:
        logger.warning(f"[VisionPipelineManager] Image file loop error: {e}")


class VisionPipelineManager:
    """Manages pipeline instances. Stage 6+7: algorithm graphs + StreamTaps."""

    def __init__(
        self,
        camera_service: CameraService,
        camera_discovery: CameraDiscovery,
        algorithm_store: AlgorithmStore,
        logger: LoggingService,
        stream_tap_registry: Optional[StreamTapRegistry] = None,
    ):
        self.camera_service = camera_service
        self.camera_discovery = camera_discovery
        self.algorithm_store = algorithm_store
        self.logger = logger
        self.stream_tap_registry = stream_tap_registry or StreamTapRegistry()
        self._instances: Dict[str, PipelineInstance] = {}
        self._save_sinks: Dict[str, List[Any]] = {}  # instance_id -> [SaveVideoSink, SaveImageSink, ...]
        self._file_threads: Dict[str, Tuple[threading.Thread, threading.Event]] = {}  # instance_id -> (thread, stop_event)
        self.logger.info("[VisionPipelineManager] Initialized")

    def list_instances(self) -> List[Dict[str, Any]]:
        """List all pipeline instances (cameras running with vision pipeline)."""
        result = []
        seen_ids = set()
        managers = self.camera_service.get_all_camera_managers()
        self.logger.info(f"[VisionPipelineManager] list_instances: {len(managers)} manager(s), _instances keys={list(self._instances.keys())}")
        for camera_id, manager in managers.items():
            is_open = manager.is_open()
            vp = getattr(manager, "vision_pipeline", None)
            has_vp = vp is not None
            vp_truthy = bool(vp)
            self.logger.info(
                f"[VisionPipelineManager] list_instances manager {camera_id}: is_open={is_open} has_vision_pipeline={has_vp} vision_pipeline_truthy={vp_truthy}"
            )
            if is_open and has_vp and vp:
                inst = self._instances.get(
                    camera_id,
                    PipelineInstance(camera_id, "vision_pipeline", camera_id, "running", manager.vision_pipeline),
                )
                metrics = manager.get_metrics() if manager else {}
                result.append(inst.to_dict(metrics=metrics))
                seen_ids.add(camera_id)
        for inst_id, inst in self._instances.items():
            if inst.state == "running" and inst_id not in seen_ids:
                self.logger.info(f"[VisionPipelineManager] list_instances: adding from _instances (not in managers) inst_id={inst_id}")
                result.append(inst.to_dict())
                seen_ids.add(inst_id)
        self.logger.info(f"[VisionPipelineManager] list_instances: returning {len(result)} instance(s) ids={[r['id'] for r in result]}")
        return result

    def _camera_id_from_graph(self, algo: Dict[str, Any]) -> Optional[str]:
        """Phase 3: Get camera_id from the graph's CameraSource node config (pull from already-open camera)."""
        nodes = algo.get("nodes") or []
        for n in nodes:
            if n.get("type") == "source" and n.get("source_type") == "camera":
                cfg = n.get("config") or {}
                cid = cfg.get("camera_id") or ""
                if cid and isinstance(cid, str):
                    return cid.strip()
        return None

    def start(
        self,
        target: str,
        algorithm_id: Optional[str] = None,
        nodes: Optional[List[Any]] = None,
        edges: Optional[List[Any]] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Start a pipeline instance by attaching to an already-open camera (Phase 2).
        Camera source in the graph pulls frames from that already-open camera (Phase 3).
        Does not open or close the camera. Camera must be open first (Cameras page or auto_start).
        Graph can be provided inline (nodes, edges) or loaded by algorithm_id.
        Returns (instance_id, None) on success or (None, error_message) on failure.
        """
        if nodes is not None and edges is not None and len(nodes) > 0 and len(edges) >= 0:
            algo = {"nodes": nodes, "edges": edges}
            algo_id_for_log = algorithm_id or "(unsaved)"
        else:
            if not algorithm_id:
                self.logger.error("[VisionPipelineManager] No algorithm_id and no inline graph")
                return None, "Provide a saved pipeline (algorithm_id) or the current graph (nodes, edges)."
            algo = self.algorithm_store.get(algorithm_id)
            if not algo or not algo.get("nodes") or not algo.get("edges"):
                self.logger.error(f"[VisionPipelineManager] Algorithm {algorithm_id} not found or empty")
                return None, "Algorithm not found. Save the pipeline first (Save Algorithm), then Run."
            algo_id_for_log = algorithm_id

        try:
            plan = compile_graph(algo["nodes"], algo["edges"])
            result = build_pipeline_with_taps(plan, algo["nodes"], self.logger)
        except GraphValidationError as e:
            self.logger.warning(f"[VisionPipelineManager] Graph invalid ({algo_id_for_log}): {e}")
            return None, f"Invalid pipeline graph: {e}"
        except Exception as e:
            self.logger.warning(f"[VisionPipelineManager] Build failed ({algo_id_for_log}): {e}")
            return None, f"Pipeline build failed: {e}"

        if not result:
            return None, "Pipeline build produced no pipeline. Check graph connections."
        vision_pipeline, stream_taps, save_sinks = result

        # Log source nodes to help debug "Open the camera first" when using file sources
        for n in algo.get("nodes") or []:
            if _is_source_node(n):
                cfg = n.get("config") or {}
                self.logger.info(
                    f"[VisionPipelineManager] start: source node id={n.get('id')!r} source_type={n.get('source_type')!r} "
                    f"is_video_file={_is_video_file_source_node(n)} is_image_file={_is_image_file_source_node(n)} "
                    f"has_path={bool((cfg.get('path') or cfg.get('location') or '').strip())}"
                )

        # Video file source: run pipeline from file, no camera
        video_file = _video_file_source_from_graph(algo)
        if video_file is not None:
            _node_id, path = video_file
            path_abs = _resolve_video_file_path(path)
            if not path_abs or not os.path.isfile(path_abs):
                self.logger.error(f"[VisionPipelineManager] Video file not found: {path!r} (resolved to {path_abs!r})")
                return None, f"Video file not found. Looked for: {path} in /home/svt/Documents and ~/Documents. If you picked a file from the browser, type the full path (e.g. /home/svt/Documents/filename.mp4) in Location."
            instance_id = "file:" + hashlib.sha256(path_abs.encode()).hexdigest()[:16]
            stop_event = threading.Event()
            thread = threading.Thread(
                target=_run_video_file_loop,
                args=(instance_id, path_abs, vision_pipeline, stop_event, self.logger),
                daemon=True,
                name=f"vp-file-{instance_id}",
            )
            self._file_threads[instance_id] = (thread, stop_event)
            thread.start()
            inst = PipelineInstance(
                instance_id=instance_id,
                algorithm_id=algorithm_id or "(unsaved)",
                target=target,
                state="running",
                vision_pipeline=vision_pipeline,
            )
            self._instances[instance_id] = inst
            for tap in stream_taps:
                self.stream_tap_registry.register_tap(instance_id, tap)
                self.logger.info(f"[VisionPipelineManager] Registered StreamTap {tap.tap_id} for {instance_id}")
            self._save_sinks[instance_id] = save_sinks
            self.logger.info(f"[VisionPipelineManager] Started file-based pipeline for {path_abs}")
            return instance_id, None

        # Image file source: run pipeline from image file, no camera
        image_file = _image_file_source_from_graph(algo)
        if image_file is not None:
            _node_id, path = image_file
            path_abs = _resolve_video_file_path(path)  # same search dirs for images
            if not path_abs or not os.path.isfile(path_abs):
                self.logger.error(f"[VisionPipelineManager] Image file not found: {path!r} (resolved to {path_abs!r})")
                return None, f"Image file not found. Looked for: {path} in /home/svt/Documents and ~/Documents. Type the full path in Location if needed."
            instance_id = "file:" + hashlib.sha256(("img:" + path_abs).encode()).hexdigest()[:16]
            stop_event = threading.Event()
            thread = threading.Thread(
                target=_run_image_file_loop,
                args=(instance_id, path_abs, vision_pipeline, stop_event, self.logger),
                daemon=True,
                name=f"vp-image-{instance_id}",
            )
            self._file_threads[instance_id] = (thread, stop_event)
            thread.start()
            inst = PipelineInstance(
                instance_id=instance_id,
                algorithm_id=algorithm_id or "(unsaved)",
                target=target,
                state="running",
                vision_pipeline=vision_pipeline,
            )
            self._instances[instance_id] = inst
            for tap in stream_taps:
                self.stream_tap_registry.register_tap(instance_id, tap)
                self.logger.info(f"[VisionPipelineManager] Registered StreamTap {tap.tap_id} for {instance_id}")
            self._save_sinks[instance_id] = save_sinks
            self.logger.info(f"[VisionPipelineManager] Started image-based pipeline for {path_abs}")
            return instance_id, None

        # Video/Image file source but path empty: clear error (do not ask to open camera)
        if _has_any_video_file_source(algo):
            self.logger.error("[VisionPipelineManager] VideoFile source has no path set")
            return None, "Set the Location (path) for the VideoFile source node in the graph, then Run again."
        if _has_any_image_file_source(algo):
            self.logger.error("[VisionPipelineManager] ImageFile source has no path set")
            return None, "Set the Location (path) for the ImageFile source node in the graph, then Run again."

        # When target is "file", user expects file source; do not require camera
        if target and str(target).strip().lower() == "file":
            return None, "Add a VideoFile or ImageFile source to the graph, set its Location (path), then Run again."

        # Camera source: require camera already open
        source_camera_id = self._camera_id_from_graph(algo)
        camera_id = source_camera_id if source_camera_id else target
        self.logger.info(f"[VisionPipelineManager] start: camera_id from graph={source_camera_id!r}, target={target!r}, using={camera_id!r}")

        if not self.camera_service.is_camera_open(camera_id):
            self.logger.error(f"[VisionPipelineManager] Camera {camera_id} not open")
            return None, "Open the camera first. Use the Cameras page to open the camera, or ensure auto_start_cameras and camera config."

        camera_details = self.camera_discovery.get_camera_details(camera_id)
        if not camera_details:
            self.logger.error(f"[VisionPipelineManager] Camera {camera_id} not found")
            return None, f"Camera {camera_id} not found. Ensure the camera is connected and discoverable."

        manager = self.camera_service.get_camera_manager(camera_id)
        if not manager:
            return None, "Camera manager not available."

        manager.vision_pipeline = vision_pipeline
        manager.use_case = "vision_pipeline"
        self.logger.info(f"[VisionPipelineManager] Attached pipeline to camera {camera_id}")

        inst = PipelineInstance(
            instance_id=camera_id,
            algorithm_id=algorithm_id or "(unsaved)",
            target=camera_id,
            state="running",
            vision_pipeline=vision_pipeline,
        )
        self._instances[camera_id] = inst
        for tap in stream_taps:
            self.stream_tap_registry.register_tap(camera_id, tap)
            self.logger.info(f"[VisionPipelineManager] Registered StreamTap {tap.tap_id} for {camera_id}")
        self._save_sinks[camera_id] = save_sinks
        self.logger.info(f"[VisionPipelineManager] Started pipeline for camera {camera_id} (attach only)")
        return camera_id, None

    def stop(self, instance_id: str) -> bool:
        """Stop a pipeline instance. For camera: detach only (camera stays open). For file: stop thread."""
        if instance_id in self._instances:
            self._instances[instance_id].state = "stopped"
            self._instances[instance_id].set_vision_pipeline(None)
        if instance_id.startswith("file:"):
            thread_event = self._file_threads.pop(instance_id, None)
            if thread_event:
                thread, stop_event = thread_event
                stop_event.set()
                thread.join(timeout=2.0)
            self._instances.pop(instance_id, None)
        else:
            manager = self.camera_service.get_camera_manager(instance_id)
            if manager:
                manager.vision_pipeline = None
                cfg = self.camera_service.camera_config_service.get_camera_config(instance_id) or {}
                manager.use_case = cfg.get("use_case", "stream_only")
                self.logger.info(f"[VisionPipelineManager] Restored camera {instance_id} use_case={manager.use_case}")
        self.stream_tap_registry.unregister_instance(instance_id)
        for sink in self._save_sinks.pop(instance_id, []):
            try:
                sink.close()
            except Exception as e:
                self.logger.warning(f"[VisionPipelineManager] Save sink close error: {e}")
        self.logger.info(f"[VisionPipelineManager] Stopped pipeline {instance_id}")
        return True

    def stop_all(self) -> int:
        """Stop all pipeline instances. Returns number stopped."""
        running = [inst for inst in self.list_instances() if inst.get("state") == "running"]
        for inst in running:
            self.stop(inst.get("id", ""))
        self.logger.info(f"[VisionPipelineManager] Stopped all pipelines ({len(running)} instance(s))")
        return len(running)

    def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Get pipeline instance status/details."""
        if instance_id in self._instances:
            inst = self._instances[instance_id]
            if inst.state == "running":
                return inst.to_dict(metrics={})
        if instance_id.startswith("file:"):
            return None
        if not self.camera_service.is_camera_open(instance_id):
            return None
        manager = self.camera_service.get_camera_manager(instance_id)
        if not manager or not (hasattr(manager, "vision_pipeline") and manager.vision_pipeline):
            return None
        inst = self._instances.get(
            instance_id,
            PipelineInstance(instance_id, "vision_pipeline", instance_id, "running", manager.vision_pipeline),
        )
        metrics = manager.get_metrics() if manager else {}
        return inst.to_dict(metrics=metrics)

    # Stage 7: StreamTap access
    def get_stream_tap(self, instance_id: str, tap_id: str) -> Optional[StreamTap]:
        """Get a StreamTap for a pipeline instance."""
        return self.stream_tap_registry.get_tap(instance_id, tap_id)

    def list_stream_taps(self, instance_id: str) -> Dict[str, Any]:
        """List all StreamTaps for a pipeline instance."""
        taps = self.stream_tap_registry.list_taps(instance_id)
        return {tid: t.get_metrics() for tid, t in taps.items()}
