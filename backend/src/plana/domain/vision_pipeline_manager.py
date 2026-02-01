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
        self.logger.info("[VisionPipelineManager] Initialized")

    def list_instances(self) -> List[Dict[str, Any]]:
        """List all pipeline instances (cameras running AprilTag pipeline)."""
        result = []
        for camera_id, manager in self.camera_service.get_all_camera_managers().items():
            if manager.is_open() and hasattr(manager, "vision_pipeline") and manager.vision_pipeline:
                inst = self._instances.get(
                    camera_id,
                    PipelineInstance(camera_id, "apriltag_cpu", camera_id, "running", manager.vision_pipeline),
                )
                metrics = manager.get_metrics() if manager else {}
                result.append(inst.to_dict(metrics=metrics))
        return result

    def start(self, algorithm_id: str, target: str) -> Optional[str]:
        """
        Start a pipeline instance.
        Stage 6: loads algorithm from store, compiles to plan, builds pipeline, opens camera.
        Falls back to default AprilTag pipeline if algorithm not found or build fails.
        Returns instance id (camera_id) or None on failure.
        """
        camera_id = target
        camera_details = self.camera_discovery.get_camera_details(camera_id)
        if not camera_details:
            self.logger.error(f"[VisionPipelineManager] Camera {camera_id} not found")
            return None

        device_path = camera_details.get("device_path")
        if not device_path:
            self.logger.error(f"[VisionPipelineManager] Camera {camera_id} has no device_path")
            return None

        vision_pipeline = None
        stream_taps: List[StreamTap] = []
        save_sinks: List[Any] = []
        algo = self.algorithm_store.get(algorithm_id)
        if algo and algo.get("nodes") and algo.get("edges"):
            try:
                plan = compile_graph(algo["nodes"], algo["edges"])
                result = build_pipeline_with_taps(plan, algo["nodes"], self.logger)
                if result:
                    vision_pipeline, stream_taps, save_sinks = result
            except GraphValidationError as e:
                self.logger.warning(f"[VisionPipelineManager] Algorithm {algorithm_id} invalid: {e}")
            except Exception as e:
                self.logger.warning(f"[VisionPipelineManager] Build failed for {algorithm_id}: {e}")

        try:
            success = self.camera_service.open_camera(
                camera_id, device_path, vision_pipeline=vision_pipeline
            )
            if success:
                manager = self.camera_service.get_camera_manager(camera_id)
                vision_pipeline = manager.vision_pipeline if manager and hasattr(manager, "vision_pipeline") else None
                inst = PipelineInstance(
                    instance_id=camera_id,
                    algorithm_id=algorithm_id,
                    target=camera_id,
                    state="running",
                    vision_pipeline=vision_pipeline,
                )
                self._instances[camera_id] = inst
                # Stage 7: Register StreamTaps
                for tap in stream_taps:
                    self.stream_tap_registry.register_tap(camera_id, tap)
                    self.logger.info(f"[VisionPipelineManager] Registered StreamTap {tap.tap_id} for {camera_id}")
                self.logger.info(f"[VisionPipelineManager] Started pipeline for camera {camera_id}")
                return camera_id
        except Exception as e:
            self.logger.error(f"[VisionPipelineManager] Failed to start pipeline for {camera_id}: {e}")
        return None

    def stop(self, instance_id: str) -> bool:
        """Stop a pipeline instance."""
        success = self.camera_service.close_camera(instance_id)
        if success:
            if instance_id in self._instances:
                self._instances[instance_id].state = "stopped"
                self._instances[instance_id].set_vision_pipeline(None)
            # Stage 7: Unregister StreamTaps
            self.stream_tap_registry.unregister_instance(instance_id)
            # Stage 8: Close SaveVideo/SaveImage sinks
            for sink in self._save_sinks.pop(instance_id, []):
                try:
                    sink.close()
                except Exception as e:
                    self.logger.warning(f"[VisionPipelineManager] Save sink close error: {e}")
            self.logger.info(f"[VisionPipelineManager] Stopped pipeline {instance_id}")
        return success

    def get_instance(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """Get pipeline instance status/details."""
        if not self.camera_service.is_camera_open(instance_id):
            return None
        manager = self.camera_service.get_camera_manager(instance_id)
        if not manager or not (hasattr(manager, "vision_pipeline") and manager.vision_pipeline):
            return None
        inst = self._instances.get(
            instance_id,
            PipelineInstance(instance_id, "apriltag_cpu", instance_id, "running", manager.vision_pipeline),
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
