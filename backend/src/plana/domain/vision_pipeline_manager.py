"""Vision Pipeline Manager: manages pipeline instances (start/stop/list)."""

from typing import Dict, Any, List, Optional
from .camera_service import CameraService
from .camera_discovery import CameraDiscovery
from .algorithm_store import AlgorithmStore
from .pipeline_instance import PipelineInstance
from .runtime_compiler import compile_graph, GraphValidationError
from .pipeline_builder import build_pipeline_with_taps
from .stream_tap import StreamTap, StreamTapRegistry
from ..services.logging_service import LoggingService


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

    def start(self, algorithm_id: str, target: str) -> tuple[Optional[str], Optional[str]]:
        """
        Start a pipeline instance by attaching to an already-open camera (Phase 2).
        Camera source in the graph pulls frames from that already-open camera (Phase 3).
        Does not open or close the camera. Camera must be open first (Cameras page or auto_start).
        Returns (instance_id, None) on success or (None, error_message) on failure.
        """
        algo = self.algorithm_store.get(algorithm_id)
        if not algo or not algo.get("nodes") or not algo.get("edges"):
            self.logger.error(f"[VisionPipelineManager] Algorithm {algorithm_id} not found or empty")
            return None, "Algorithm not found. Save the pipeline first (Save Algorithm), then Run."

        # Phase 3: resolve camera from graph CameraSource config, else use Run target
        source_camera_id = self._camera_id_from_graph(algo)
        camera_id = source_camera_id if source_camera_id else target
        self.logger.info(f"[VisionPipelineManager] start: camera_id from graph={source_camera_id!r}, target={target!r}, using={camera_id!r}")

        # Phase 2: require camera already open
        if not self.camera_service.is_camera_open(camera_id):
            self.logger.error(f"[VisionPipelineManager] Camera {camera_id} not open")
            return None, "Open the camera first. Use the Cameras page to open the camera, or ensure auto_start_cameras and camera config."

        camera_details = self.camera_discovery.get_camera_details(camera_id)
        if not camera_details:
            self.logger.error(f"[VisionPipelineManager] Camera {camera_id} not found")
            return None, f"Camera {camera_id} not found. Ensure the camera is connected and discoverable."

        try:
            plan = compile_graph(algo["nodes"], algo["edges"])
            result = build_pipeline_with_taps(plan, algo["nodes"], self.logger)
        except GraphValidationError as e:
            self.logger.warning(f"[VisionPipelineManager] Algorithm {algorithm_id} invalid: {e}")
            return None, f"Invalid pipeline graph: {e}"
        except Exception as e:
            self.logger.warning(f"[VisionPipelineManager] Build failed for {algorithm_id}: {e}")
            return None, f"Pipeline build failed: {e}"

        if not result:
            return None, "Pipeline build produced no pipeline. Check graph connections."
        vision_pipeline, stream_taps, save_sinks = result

        manager = self.camera_service.get_camera_manager(camera_id)
        if not manager:
            return None, "Camera manager not available."

        # Phase 2: attach pipeline to already-open camera (no open_camera)
        manager.vision_pipeline = vision_pipeline
        manager.use_case = "vision_pipeline"
        self.logger.info(f"[VisionPipelineManager] Attached pipeline to camera {camera_id}")

        inst = PipelineInstance(
            instance_id=camera_id,
            algorithm_id=algorithm_id,
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
        """Stop a pipeline instance by detaching only. Camera remains open (Phase 2)."""
        if instance_id in self._instances:
            self._instances[instance_id].state = "stopped"
            self._instances[instance_id].set_vision_pipeline(None)
        # Detach pipeline from manager; camera stays open
        manager = self.camera_service.get_camera_manager(instance_id)
        if manager:
            manager.vision_pipeline = None
            # Restore use_case from config (e.g. apriltag or stream_only)
            cfg = self.camera_service.camera_config_service.get_camera_config(instance_id) or {}
            manager.use_case = cfg.get("use_case", "stream_only")
            self.logger.info(f"[VisionPipelineManager] Restored camera {instance_id} use_case={manager.use_case}")
        # Stage 7: Unregister StreamTaps
        self.stream_tap_registry.unregister_instance(instance_id)
        # Stage 8: Close SaveVideo/SaveImage sinks
        for sink in self._save_sinks.pop(instance_id, []):
            try:
                sink.close()
            except Exception as e:
                self.logger.warning(f"[VisionPipelineManager] Save sink close error: {e}")
        self.logger.info(f"[VisionPipelineManager] Stopped pipeline {instance_id} (detach only, camera stays open)")
        return True

    def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Get pipeline instance status/details."""
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
