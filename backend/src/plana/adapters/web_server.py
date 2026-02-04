"""Web server adapter for SVTVision."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from typing import Dict, Any
from ..services.config_service import ConfigService
from ..services.health_service import HealthService
from ..domain.debug_tree_manager import DebugTreeManager
from ..domain.camera_discovery import CameraDiscovery
from ..domain.camera_service import CameraService
from ..domain.algorithm_store import AlgorithmStore
from ..domain.stage_registry import StageRegistry
from ..domain.vision_pipeline_manager import VisionPipelineManager
from ..services.logging_service import LoggingService
from ..services.camera_config_service import CameraConfigService
from ..adapters.selftest_runner import SelfTestRunner
from fastapi import HTTPException, WebSocket, WebSocketDisconnect, Body, Request
from pydantic import BaseModel
from typing import Optional
import asyncio
import base64


class WebServerAdapter:
    """Web server adapter for HTTP/WebSocket communication."""
    
    def __init__(
        self,
        config_service: ConfigService,
        health_service: HealthService,
        debug_tree_manager: DebugTreeManager,
        logger: LoggingService,
        self_test_runner: SelfTestRunner,
        camera_discovery: CameraDiscovery,
        camera_config_service: CameraConfigService,
        camera_service: CameraService,
        algorithm_store: AlgorithmStore,
        stage_registry: StageRegistry,
        vision_pipeline_manager: VisionPipelineManager,
        frontend_dist_path: Path
    ):
        self.config_service = config_service
        self.health_service = health_service
        self.debug_tree_manager = debug_tree_manager
        self.logger = logger
        self.self_test_runner = self_test_runner
        self.camera_discovery = camera_discovery
        self.camera_config_service = camera_config_service
        self.camera_service = camera_service
        self.algorithm_store = algorithm_store
        self.stage_registry = stage_registry
        self.vision_pipeline_manager = vision_pipeline_manager
        self.frontend_dist_path = frontend_dist_path
        
        self.app = FastAPI(title="SVTVision API")
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self._setup_routes()
    
    def _setup_routes(self):
        """Set up API routes."""
        # Algorithms API - register directly on app first to avoid 405 with catch-all
        @self.app.get("/api/algorithms")
        async def list_algorithms() -> Dict[str, Any]:
            items = self.algorithm_store.list_all()
            return {"algorithms": items}

        @self.app.get("/api/algorithms/{algo_id}")
        async def get_algorithm(algo_id: str) -> Dict[str, Any]:
            data = self.algorithm_store.get(algo_id)
            if not data:
                raise HTTPException(status_code=404, detail="Algorithm not found")
            return data

        @self.app.post("/api/algorithms")
        async def create_algorithm(request: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
            name = request.get("name", "Untitled")
            nodes = request.get("nodes", [])
            edges = request.get("edges", [])
            layout = request.get("layout", {})
            algo_id = self.algorithm_store.save(None, name, nodes, edges, layout)
            return {"id": algo_id, "name": name}

        @self.app.put("/api/algorithms/{algo_id}")
        async def update_algorithm(algo_id: str, request: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
            existing = self.algorithm_store.get(algo_id)
            if not existing:
                raise HTTPException(status_code=404, detail="Algorithm not found")
            name = request.get("name", existing.get("name", "Untitled"))
            nodes = request.get("nodes", existing.get("nodes", []))
            edges = request.get("edges", existing.get("edges", []))
            layout = request.get("layout", existing.get("layout", {}))
            self.algorithm_store.save(algo_id, name, nodes, edges, layout)
            return {"id": algo_id, "name": name}

        @self.app.delete("/api/algorithms/{algo_id}")
        async def delete_algorithm(algo_id: str) -> None:
            if not self.algorithm_store.delete(algo_id):
                raise HTTPException(status_code=404, detail="Algorithm not found")

        @self.app.get("/api/system")
        async def get_system() -> Dict[str, Any]:
            """Get system information."""
            health = self.health_service.get_global_health()
            return {
                "appName": self.config_service.get("app_name", "SVTVision"),
                "buildId": self.config_service.get("build_id", "2024.01.20-dev"),
                "health": health.value,
                "connection": "connected"
            }
        
        @self.app.get("/api/debug/tree")
        async def get_debug_tree() -> Dict[str, Any]:
            """Get debug tree."""
            return self.debug_tree_manager.get_tree_dict()

        @self.app.get("/api/debug/top-faults")
        async def get_top_faults(max_faults: int = 5) -> Dict[str, Any]:
            """Get top faults (non-OK nodes) from debug tree, ordered by severity."""
            faults = self.debug_tree_manager.get_top_faults(max_faults=max_faults)
            return {"faults": faults}
        
        @self.app.get("/api/selftest/run")
        async def run_selftest(test: str) -> Dict[str, Any]:
            """Run a self-test."""
            return self.self_test_runner.run_test(test)

        # Vision Pipeline (VP) API stubs - Stage 0
        @self.app.get("/api/vp")
        async def vp_info() -> Dict[str, Any]:
            """Vision Pipeline API info stub."""
            return {"version": "0.1", "status": "skeleton", "message": "VP API stubs"}

        @self.app.get("/api/vp/stages")
        async def vp_stages() -> Dict[str, Any]:
            """Vision Pipeline stages from StageRegistry (palette discovery). Stage 9: includes custom stages."""
            return self.stage_registry.list_all()

        @self.app.post("/api/vp/stages")
        async def vp_stages_add(request: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
            """Stage 9: Register a custom stage (plugin-based addition). Palette auto-updates on next GET."""
            ok = self.stage_registry.add_stage(request)
            if not ok:
                raise HTTPException(status_code=400, detail="Invalid stage or id conflicts with built-in")
            return {"ok": True, "id": request.get("id")}

        @self.app.delete("/api/vp/stages/{stage_id}")
        async def vp_stages_remove(stage_id: str) -> Dict[str, Any]:
            """Stage 9: Remove a custom stage. Only custom stages can be removed."""
            if not self.stage_registry.remove_stage(stage_id):
                raise HTTPException(status_code=400, detail="Not a custom stage or not found")
            return {"ok": True, "id": stage_id}

        @self.app.get("/api/vp/algorithms")
        async def vp_algorithms() -> Dict[str, Any]:
            """Vision Pipeline algorithms (saved graphs)."""
            items = self.algorithm_store.list_all()
            return {"algorithms": items}

        @self.app.post("/api/vp/validate")
        async def vp_validate(request: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
            """Validate pipeline graph (DAG, single-source, single-input-per-port)."""
            from ..domain.graph_model import (
                PipelineGraph,
                GraphNode,
                GraphEdge,
                validate_graph,
                GraphValidationError,
            )
            nodes_raw = request.get("nodes", [])
            edges_raw = request.get("edges", [])
            nodes = [
                GraphNode(
                    id=n.get("id", ""),
                    type=n.get("type", "stage"),
                    stage_id=n.get("stage_id"),
                    source_type=n.get("source_type"),
                    sink_type=n.get("sink_type"),
                    config=n.get("config"),
                    ports=n.get("ports"),
                )
                for n in nodes_raw
            ]
            edges = [
                GraphEdge(
                    id=e.get("id", ""),
                    source_node=e.get("source_node", ""),
                    source_port=e.get("source_port", ""),
                    target_node=e.get("target_node", ""),
                    target_port=e.get("target_port", ""),
                )
                for e in edges_raw
            ]
            graph = PipelineGraph(nodes=nodes, edges=edges)
            try:
                validate_graph(graph)
                return {"valid": True, "errors": []}
            except GraphValidationError as ex:
                return {"valid": False, "errors": ex.errors}

        @self.app.post("/api/vp/compile")
        async def vp_compile(request: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
            """Compile pipeline graph to execution plan (main path + side taps). Stage 5."""
            from ..domain.runtime_compiler import compile_graph, GraphValidationError
            nodes_raw = request.get("nodes", [])
            edges_raw = request.get("edges", [])
            try:
                plan = compile_graph(nodes_raw, edges_raw)
                return {"valid": True, "plan": plan.to_dict()}
            except GraphValidationError as ex:
                return {"valid": False, "errors": ex.errors}

        # Pipeline instances (start/stop/list)
        @self.app.get("/api/pipelines")
        async def get_pipelines() -> Dict[str, Any]:
            instances = self.vision_pipeline_manager.list_instances()
            self.logger.info(f"[WebServer] GET /api/pipelines returning {len(instances)} instance(s)")
            return {"instances": instances}

        @self.app.get("/api/pipelines/{instance_id}")
        async def get_pipeline(instance_id: str) -> Dict[str, Any]:
            inst = self.vision_pipeline_manager.get_instance(instance_id)
            if not inst:
                raise HTTPException(status_code=404, detail="Pipeline instance not found")
            return inst

        @self.app.post("/api/pipelines")
        async def post_pipelines(request: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
            target = request.get("target")
            if not target:
                raise HTTPException(status_code=400, detail="target (camera_id) is required")
            algorithm_id = request.get("algorithm_id") or None
            nodes = request.get("nodes")
            edges = request.get("edges")
            has_inline = isinstance(nodes, list) and isinstance(edges, list) and len(nodes) > 0
            if not has_inline and not algorithm_id:
                raise HTTPException(
                    status_code=400,
                    detail="Provide algorithm_id (saved pipeline) or nodes and edges (current graph).",
                )
            instance_id, err_msg = self.vision_pipeline_manager.start(
                target=target, algorithm_id=algorithm_id, nodes=nodes if has_inline else None, edges=edges if has_inline else None
            )
            if not instance_id:
                raise HTTPException(
                    status_code=500,
                    detail=err_msg or "Failed to start pipeline. Ensure the camera is open and the graph is valid.",
                )
            self.logger.info(f"[WebServer] POST /api/pipelines started instance_id={instance_id} target={target}")
            return {"id": instance_id, "state": "running"}

        @self.app.post("/api/pipelines/{instance_id}/stop")
        async def post_pipeline_stop(instance_id: str) -> Dict[str, Any]:
            success = self.vision_pipeline_manager.stop(instance_id)
            if not success:
                raise HTTPException(status_code=404, detail="Pipeline instance not found or already stopped")
            return {"id": instance_id, "state": "stopped"}

        @self.app.post("/api/pipelines/stop-all")
        async def post_pipelines_stop_all() -> Dict[str, Any]:
            stopped = self.vision_pipeline_manager.stop_all()
            return {"stopped": stopped}

        # Camera discovery endpoints
        @self.app.get("/api/cameras")
        async def get_cameras() -> Dict[str, Any]:
            """Get list of all cameras."""
            cameras = self.camera_discovery.get_camera_list()
            return {"cameras": cameras}
        
        @self.app.get("/api/cameras/{camera_id}")
        async def get_camera(camera_id: str) -> Dict[str, Any]:
            """Get camera details."""
            details = self.camera_discovery.get_camera_details(camera_id)
            if not details:
                raise HTTPException(status_code=404, detail="Camera not found")
            return details
        
        @self.app.get("/api/cameras/{camera_id}/capabilities")
        async def get_camera_capabilities(camera_id: str) -> Dict[str, Any]:
            """Get camera capabilities."""
            capabilities = self.camera_discovery.get_camera_capabilities(camera_id)
            if not capabilities:
                raise HTTPException(status_code=404, detail="Camera not found")
            return capabilities
        
        @self.app.get("/api/cameras/{camera_id}/controls")
        async def get_camera_controls(camera_id: str) -> Dict[str, Any]:
            """Get camera controls."""
            controls = self.camera_discovery.get_camera_controls(camera_id)
            if controls is None:
                raise HTTPException(status_code=404, detail="Camera not found")
            return {"controls": controls}
        
        # Camera naming endpoints
        class CameraNameRequest(BaseModel):
            position: str  # front, middle, back
            side: Optional[str] = None  # left, right, or None
        
        @self.app.post("/api/cameras/{camera_id}/name")
        async def set_camera_name(camera_id: str, request: CameraNameRequest) -> Dict[str, Any]:
            """Set camera name based on position and side."""
            # Validate position
            if request.position not in ['front', 'middle', 'back']:
                raise HTTPException(status_code=400, detail="Position must be 'front', 'middle', or 'back'")
            
            # Validate side if provided
            if request.side and request.side not in ['left', 'right']:
                raise HTTPException(status_code=400, detail="Side must be 'left' or 'right'")
            
            self.camera_config_service.set_camera_name(camera_id, request.position, request.side)
            return {
                "camera_id": camera_id,
                "name": self.camera_config_service.get_camera_name(camera_id),
                "position": request.position,
                "side": request.side
            }
        
        @self.app.get("/api/cameras/{camera_id}/name")
        async def get_camera_name(camera_id: str) -> Dict[str, Any]:
            """Get camera name configuration."""
            config = self.camera_config_service.get_camera_config(camera_id)
            if config:
                return config
            return {
                "name": None,
                "position": None,
                "side": None
            }
        
        # Camera resolution/FPS endpoints
        class CameraResolutionRequest(BaseModel):
            format: str
            width: int
            height: int
            fps: float
        
        @self.app.post("/api/cameras/{camera_id}/resolution")
        async def set_camera_resolution(camera_id: str, request: CameraResolutionRequest) -> Dict[str, Any]:
            """Set camera resolution and FPS."""
            self.camera_config_service.set_camera_resolution_fps(
                camera_id,
                request.format,
                request.width,
                request.height,
                request.fps
            )
            return {
                "camera_id": camera_id,
                "resolution": {
                    "format": request.format,
                    "width": request.width,
                    "height": request.height,
                    "fps": request.fps
                }
            }
        
        @self.app.get("/api/cameras/{camera_id}/resolution")
        async def get_camera_resolution(camera_id: str) -> Dict[str, Any]:
            """Get camera resolution and FPS configuration."""
            resolution = self.camera_config_service.get_camera_resolution_fps(camera_id)
            if resolution:
                return resolution
            return {
                "format": None,
                "width": None,
                "height": None,
                "fps": None
            }
        
        # Camera settings endpoints (Stage 3)
        class CameraSettingsRequest(BaseModel):
            resolution: Optional[Dict[str, Any]] = None
            exposure: Optional[float] = None
            gain: Optional[float] = None
            saturation: Optional[float] = None
            use_case: Optional[str] = None  # apriltag, stream_only, vision_pipeline
        
        @self.app.get("/api/cameras/{camera_id}/detection_stats")
        async def get_detection_stats(camera_id: str) -> Dict[str, Any]:
            """Get detection statistics for a camera."""
            manager = self.camera_service.get_camera_manager(camera_id)
            if not manager or not manager.is_open():
                raise HTTPException(status_code=404, detail="Camera not open")
            
            if not hasattr(manager, 'vision_pipeline') or not manager.vision_pipeline:
                return {
                    "camera_id": camera_id,
                    "has_pipeline": False,
                    "message": "Camera does not have vision pipeline"
                }
            
            pipeline = manager.vision_pipeline
            metrics = pipeline.get_metrics()
            
            return {
                "camera_id": camera_id,
                "has_pipeline": True,
                "metrics": metrics
            }
        
        @self.app.get("/api/cameras/{camera_id}/settings")
        async def get_camera_settings(camera_id: str) -> Dict[str, Any]:
            """Get camera settings (requested and actual).
            
            Returns saved settings from per-camera file and actual settings if camera is open.
            """
            # Get requested settings from per-camera settings file
            requested_settings = self.camera_config_service.get_camera_settings(camera_id) or {}
            
            # Get actual settings if camera is open
            actual_settings = {}
            if self.camera_service.is_camera_open(camera_id):
                manager = self.camera_service.get_camera_manager(camera_id)
                if manager and hasattr(manager, 'camera_port'):
                    try:
                        actual_settings = manager.camera_port.get_actual_settings() or {}
                    except Exception as e:
                        self.logger.warning(f"[Stream] Failed to get actual settings: {e}")
                        actual_settings = {}
            
            # Verify resolution match if both exist
            verification = {"verified": False, "reason": "Settings not available"}
            if requested_settings.get("resolution") and actual_settings:
                req_res = requested_settings["resolution"]
                if (actual_settings.get("width") == req_res.get("width") and
                    actual_settings.get("height") == req_res.get("height") and
                    abs(actual_settings.get("fps", 0) - req_res.get("fps", 0)) < 1.0 and
                    actual_settings.get("format") == req_res.get("format")):
                    verification = {"verified": True, "reason": "Settings match"}
                else:
                    verification = {"verified": False, "reason": "Settings mismatch"}
            
            return {
                "camera_id": camera_id,
                "requested": requested_settings,
                "actual": actual_settings,
                "verification": verification
            }

        @self.app.get("/api/cameras/{camera_id}/detector-config")
        async def get_detector_config(camera_id: str) -> Dict[str, Any]:
            """Get detector config for a camera (use_case, etc.). Returns empty if not set."""
            config = self.camera_config_service.get_camera_config(camera_id) or {}
            return {
                "camera_id": camera_id,
                "use_case": config.get("use_case", "stream_only"),
                "family": "tag36h11",
            }

        @self.app.get("/api/cameras/{camera_id}/preprocessing-config")
        async def get_preprocessing_config(camera_id: str) -> Dict[str, Any]:
            """Get preprocessing config for a camera. Returns defaults if not set."""
            config = self.camera_config_service.get_camera_config(camera_id) or {}
            preprocessing = config.get("preprocessing", {})
            return {
                "camera_id": camera_id,
                "preprocessing": preprocessing if preprocessing else {
                    "blur_kernel_size": 3,
                    "adaptive_block_size": 15,
                    "adaptive_c": 3,
                    "morphology": False,
                },
            }
        
        @self.app.post("/api/cameras/{camera_id}/settings")
        async def set_camera_settings(camera_id: str, request: CameraSettingsRequest) -> Dict[str, Any]:
            """Set camera settings."""
            settings = {}
            
            # Handle use_case (validate and save). Phase 1: apriltag = Y-only (grayscale) path.
            if request.use_case is not None:
                valid_use_cases = ['apriltag', 'stream_only', 'vision_pipeline']
                if request.use_case not in valid_use_cases:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid use_case. Must be one of: {', '.join(valid_use_cases)}"
                    )
                settings["use_case"] = request.use_case
            
            if request.resolution:
                # Save resolution to config
                res = request.resolution
                self.camera_config_service.set_camera_resolution_fps(
                    camera_id,
                    res.get("format", "YUYV"),
                    res.get("width", 640),
                    res.get("height", 480),
                    res.get("fps", 30.0)
                )
                settings["resolution"] = request.resolution
                
                # Apply to open camera if available
                if self.camera_service.is_camera_open(camera_id):
                    res = request.resolution
                    success = self.camera_service.apply_camera_settings(
                        camera_id,
                        res.get("width", 640),
                        res.get("height", 480),
                        res.get("fps", 30.0),
                        res.get("format", "YUYV")
                    )
                    if not success:
                        self.logger.warning(f"[Stream] Failed to apply settings to open camera {camera_id}")
            
            # Save other settings
            if request.exposure is not None:
                settings["exposure"] = request.exposure
            if request.gain is not None:
                settings["gain"] = request.gain
            if request.saturation is not None:
                settings["saturation"] = request.saturation
            
            if settings:
                self.camera_config_service.set_camera_settings(camera_id, settings)
            
            # Verify settings if camera is open
            verification = {}
            if self.camera_service.is_camera_open(camera_id) and request.resolution:
                res = request.resolution
                verification = self.camera_service.verify_camera_settings(
                    camera_id,
                    res.get("width", 640),
                    res.get("height", 480),
                    res.get("fps", 30.0),
                    res.get("format", "YUYV")
                )
            
            return {
                "camera_id": camera_id,
                "settings": settings,
                "verification": verification
            }
        
        # Camera open/close endpoints
        @self.app.post("/api/cameras/{camera_id}/open")
        async def open_camera(camera_id: str, request: Request) -> Dict[str, Any]:
            """Open a camera. Uses saved use_case from config (apriltag=grayscale) unless body has stream_only: true."""
            # Get camera details to find device path
            camera_details = self.camera_discovery.get_camera_details(camera_id)
            if not camera_details:
                raise HTTPException(status_code=404, detail="Camera not found")
            
            device_path = camera_details.get("device_path")
            if not device_path:
                raise HTTPException(status_code=400, detail="Camera device path not available")
            
            # Default: use saved use_case from config (apriltag → grayscale). Set stream_only: true to force stream-only.
            stream_only = None  # None = use config use_case
            try:
                body_bytes = await request.body()
                if body_bytes:
                    import json
                    body = json.loads(body_bytes)
                    if isinstance(body, dict) and "stream_only" in body:
                        stream_only = bool(body["stream_only"])
            except Exception:
                pass
            self.logger.info(f"[Stream] Opening camera {camera_id} stream_only={stream_only} (None=use config use_case)")
            try:
                success = self.camera_service.open_camera(
                    camera_id,
                    device_path,
                    stream_only=stream_only if stream_only is not None else False,
                )
            except Exception as e:
                self.logger.error(f"[Stream] Open camera {camera_id} exception: {e}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to open camera: {e}. Ensure your user is in the 'video' group (run: sudo usermod -aG video $USER, then log out and back in)."
                )
            
            if not success:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to open camera. Ensure your user is in the 'video' group (run: sudo usermod -aG video $USER, then log out and back in), and no other app is using the device."
                )
            
            return {
                "camera_id": camera_id,
                "status": "opened",
                "device_path": device_path
            }
        
        @self.app.post("/api/cameras/{camera_id}/close")
        async def close_camera(camera_id: str) -> Dict[str, Any]:
            """Close a camera."""
            success = self.camera_service.close_camera(camera_id)
            
            if not success:
                raise HTTPException(status_code=404, detail="Camera not open")
            
            return {
                "camera_id": camera_id,
                "status": "closed"
            }
        
        @self.app.get("/api/cameras/{camera_id}/status")
        async def get_camera_status(camera_id: str) -> Dict[str, Any]:
            """Get camera streaming status and metrics."""
            is_open = self.camera_service.is_camera_open(camera_id)
            
            result = {
                "camera_id": camera_id,
                "open": is_open,
                "metrics": {}
            }
            
            if is_open:
                manager = self.camera_service.get_camera_manager(camera_id)
                if manager:
                    result["metrics"] = manager.get_metrics()
            
            return result
        
        # Control settings endpoint (immediate application)
        # Accept dynamic control names (e.g., brightness, contrast, gain, etc.)
        @self.app.post("/api/cameras/{camera_id}/controls")
        async def apply_control_settings(camera_id: str, request: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
            """Apply control settings dynamically (any control name) immediately to an open camera."""
            if not self.camera_service.is_camera_open(camera_id):
                raise HTTPException(status_code=400, detail="Camera must be open to apply control settings")
            
            # Get camera manager to apply controls directly via v4l2-ctl
            manager = self.camera_service.get_camera_manager(camera_id)
            if not manager:
                raise HTTPException(status_code=404, detail="Camera manager not found")
            
            # Get device path
            device_path = manager.device_path if hasattr(manager, 'device_path') else None
            if not device_path:
                # Try to get from camera discovery
                camera_details = self.camera_discovery.get_camera_details(camera_id)
                device_path = camera_details.get("device_path") if camera_details else None
            
            if not device_path:
                raise HTTPException(status_code=400, detail="Camera device path not available")
            
            # Apply each control using v4l2-ctl
            import subprocess
            applied_settings = {}
            failed_settings = []
            
            for control_name, value in request.items():
                try:
                    # Use v4l2-ctl to set control
                    result = subprocess.run(
                        ["v4l2-ctl", "-d", device_path, "--set-ctrl", f"{control_name}={value}"],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if result.returncode == 0:
                        applied_settings[control_name] = value
                        # Save all controls to config for persistence (per camera ID)
                        current_settings = self.camera_config_service.get_camera_settings(camera_id) or {}
                        current_settings[control_name] = value
                        self.camera_config_service.set_camera_settings(camera_id, current_settings)
                    else:
                        failed_settings.append(f"{control_name}: {result.stderr.strip()}")
                except Exception as e:
                    failed_settings.append(f"{control_name}: {str(e)}")
            
            if failed_settings and not applied_settings:
                raise HTTPException(status_code=500, detail=f"Failed to apply controls: {', '.join(failed_settings)}")
            
            return {
                "camera_id": camera_id,
                "applied": applied_settings,
                "failed": failed_settings if failed_settings else None
            }
        
        # WebSocket streaming endpoint
        @self.app.websocket("/ws/stream")
        async def stream_video(websocket: WebSocket):
            """WebSocket endpoint for video streaming."""
            await websocket.accept()
            
            # Get query parameters
            camera_id = websocket.query_params.get("camera")
            stage = websocket.query_params.get("stage", "raw")
            
            if not camera_id:
                await websocket.close(code=1008, reason="Missing camera parameter")
                return
            
            manager = self.camera_service.get_camera_manager(camera_id)
            if not manager:
                await websocket.close(code=1008, reason="Camera manager not found")
                return
            
            # Validate stage from pipeline (or default stages if no pipeline)
            pipeline = getattr(manager, "vision_pipeline", None)
            valid_stages = ["raw"] + ([s.name for s in pipeline._stages] if pipeline and hasattr(pipeline, "_stages") else ["preprocess", "detect_overlay"])
            if stage not in valid_stages:
                await websocket.close(code=1008, reason=f"Invalid stage: {stage}. Must be one of {valid_stages}")
                return
            
            # Check if camera is open
            if not self.camera_service.is_camera_open(camera_id):
                await websocket.close(code=1008, reason="Camera not open")
                return
            
            self.logger.info(f"Starting video stream for camera {camera_id}, stage={stage}")
            
            try:
                frames_sent = 0
                last_frame_data = None  # Track last frame to avoid sending duplicates
                
                while True:
                    # Get latest frame for the requested stage
                    frame_data = manager.get_latest_frame(stage)
                    
                    # Only send if frame changed or is first frame
                    if frame_data and frame_data != last_frame_data:
                        try:
                            # Get detections if stage is detect_overlay
                            detections = []
                            if stage == "detect_overlay":
                                detections_raw = manager.get_latest_detections()
                                detections = [det.to_dict() for det in detections_raw]
                            
                            # Send frame as base64-encoded JSON message
                            frame_b64 = base64.b64encode(frame_data).decode('utf-8')
                            await websocket.send_json({
                                "type": "frame",
                                "camera_id": camera_id,
                                "stage": stage,
                                "data": frame_b64,
                                "metrics": manager.get_metrics(),
                                "detections": detections
                            })
                            last_frame_data = frame_data
                            frames_sent += 1
                            if frames_sent % 100 == 0:
                                self.logger.info(f"[Stream] {camera_id} ({stage}): Sent {frames_sent} frames")
                        except Exception as e:
                            self.logger.error(f"[Stream] Error sending frame for {camera_id}: {e}")
                            break
                    
                    # Match the camera FPS for streaming rate
                    metrics = manager.get_metrics()
                    target_fps = metrics.get("settings", {}).get("fps", 30.0)
                    frame_interval = 1.0 / target_fps if target_fps > 0 else 0.033
                    await asyncio.sleep(frame_interval)
                    
            except WebSocketDisconnect:
                self.logger.info(f"[Stream] WebSocket disconnected for camera {camera_id}")
            except Exception as e:
                self.logger.error(f"[Stream] Error in video stream for {camera_id}: {e}")
                try:
                    await websocket.close(code=1011, reason="Internal error")
                except:
                    pass

        # Stage 7: WebSocket endpoint for StreamTap
        @self.app.websocket("/ws/vp/tap/{instance_id}/{tap_id}")
        async def stream_tap_video(websocket: WebSocket, instance_id: str, tap_id: str):
            """WebSocket endpoint for StreamTap video streaming (Stage 7)."""
            await websocket.accept()
            tap = self.vision_pipeline_manager.get_stream_tap(instance_id, tap_id)
            if not tap:
                self.logger.warning(f"[StreamTap] Tap not found instance_id={instance_id!r} tap_id={tap_id!r}")
                try:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"StreamTap {tap_id} not found for instance {instance_id}",
                    })
                except Exception:
                    pass
                await websocket.close(code=1008, reason=f"StreamTap {tap_id} not found for instance {instance_id}")
                return

            self.logger.info(f"[StreamTap] Started streaming {tap_id} for instance {instance_id}")
            frames_sent = 0
            last_jpeg = None

            try:
                while True:
                    # Get latest frame from StreamTap
                    jpeg_data = tap.get_jpeg()
                    
                    if jpeg_data and jpeg_data != last_jpeg:
                        try:
                            frame_b64 = base64.b64encode(jpeg_data).decode('utf-8')
                            await websocket.send_json({
                                "type": "frame",
                                "tap_id": tap_id,
                                "instance_id": instance_id,
                                "data": frame_b64,
                                "metrics": tap.get_metrics(),
                            })
                            last_jpeg = jpeg_data
                            frames_sent += 1
                            if frames_sent % 100 == 0:
                                self.logger.info(f"[StreamTap] {tap_id}: Sent {frames_sent} frames")
                        except Exception as e:
                            self.logger.error(f"[StreamTap] Error sending frame: {e}")
                            break
                    
                    await asyncio.sleep(0.033)  # ~30fps
            except WebSocketDisconnect:
                self.logger.info(f"[StreamTap] WebSocket disconnected for {tap_id}")
            except Exception as e:
                self.logger.error(f"[StreamTap] Error in stream for {tap_id}: {e}")
                try:
                    await websocket.close(code=1011, reason="Internal error")
                except:
                    pass

        # API to list StreamTaps for a pipeline instance
        @self.app.get("/api/vp/taps/{instance_id}")
        async def list_stream_taps(instance_id: str) -> Dict[str, Any]:
            """List all StreamTaps for a pipeline instance."""
            return {"taps": self.vision_pipeline_manager.list_stream_taps(instance_id)}

        # Serve static files in production mode
        if self.frontend_dist_path.exists():
            @self.app.get("/{full_path:path}")
            async def serve_frontend(full_path: str):
                """Serve frontend static files. Exclude /api to avoid shadowing API routes."""
                if full_path.startswith("api/") or full_path.startswith("api"):
                    raise HTTPException(status_code=404, detail="Not found")
                if full_path == "" or full_path == "/":
                    full_path = "index.html"

                file_path = self.frontend_dist_path / full_path
                if file_path.exists() and file_path.is_file():
                    return FileResponse(file_path)
                else:
                    # Fallback to index.html for SPA routing
                    return FileResponse(self.frontend_dist_path / "index.html")
            
            self.app.mount(
                "/assets",
                StaticFiles(directory=self.frontend_dist_path / "assets"),
                name="assets"
            )
    
    def get_app(self) -> FastAPI:
        """Get FastAPI application."""
        return self.app
