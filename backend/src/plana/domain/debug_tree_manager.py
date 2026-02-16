"""Debug tree manager for maintaining the debug tree state."""

import subprocess
import time
from typing import List, Optional, Dict, Any
from .debug_tree import DebugTreeNode, NodeStatus
from ..services.health_service import HealthService
from ..services.logging_service import LoggingService


def _get_cpu_gpu_usage() -> Dict[str, Any]:
    """Get CPU and GPU usage. Returns dict with cpu_percent, gpu_percent, gpu_memory_used_mb, gpu_memory_total_mb."""
    out: Dict[str, Any] = {
        "cpu_percent": None,
        "gpu_percent": None,
        "gpu_memory_used_mb": None,
        "gpu_memory_total_mb": None,
    }
    # CPU: try psutil, else /proc/stat (Linux)
    try:
        import psutil
        out["cpu_percent"] = round(psutil.cpu_percent(interval=None) or 0, 1)
    except ImportError:
        try:
            with open("/proc/stat", "r") as f:
                line = f.readline()
            parts = line.split()
            if parts[0] == "cpu" and len(parts) >= 5:
                user, nice, system, idle = int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                total1 = user + nice + system + idle
                time.sleep(0.05)
                with open("/proc/stat", "r") as f:
                    line2 = f.readline()
                parts2 = line2.split()
                if parts2[0] == "cpu" and len(parts2) >= 5:
                    user2, nice2, system2, idle2 = int(parts2[1]), int(parts2[2]), int(parts2[3]), int(parts2[4])
                    total2 = user2 + nice2 + system2 + idle2
                    if total2 > total1:
                        out["cpu_percent"] = round(100.0 * (1.0 - (idle2 - idle) / (total2 - total1)), 1)
        except Exception:
            pass
    # GPU: try pynvml, else nvidia-smi
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        out["gpu_percent"] = util.gpu
        out["gpu_memory_used_mb"] = round(mem.used / (1024 * 1024), 1)
        out["gpu_memory_total_mb"] = round(mem.total / (1024 * 1024), 1)
        pynvml.nvmlShutdown()
    except Exception:
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(",")
                if len(parts) >= 3:
                    out["gpu_percent"] = int(parts[0].strip().split()[0] or 0)
                    out["gpu_memory_used_mb"] = float(parts[1].strip().split()[0] or 0)
                    out["gpu_memory_total_mb"] = float(parts[2].strip().split()[0] or 0)
        except Exception:
            pass
    return out


class DebugTreeManager:
    """Manages the debug tree with simulated nodes."""
    
    def __init__(
        self,
        health_service: HealthService,
        logger: LoggingService,
        camera_service=None,
        camera_discovery=None
    ):
        self.health_service = health_service
        self.logger = logger
        self.camera_service = camera_service
        self.camera_discovery = camera_discovery
        self.root_node = self._create_simulated_tree()
    
    def _create_simulated_tree(self) -> DebugTreeNode:
        """Create simulated debug tree for Stage 0."""
        return DebugTreeNode(
            id="root",
            name="System",
            status=NodeStatus.OK,
            reason="All systems operational",
            metrics={"fps": 30.0, "latency": 16},
            children=[
                DebugTreeNode(
                    id="host",
                    name="Host",
                    status=NodeStatus.OK,
                    reason="CPU/GPU",
                    metrics={
                        "cpu_percent": None,
                        "gpu_percent": None,
                        "gpu_memory_used_mb": None,
                        "gpu_memory_total_mb": None,
                    },
                ),
                DebugTreeNode(
                    id="camera_manager",
                    name="Camera Manager",
                    status=NodeStatus.OK,
                    reason="Running",
                    metrics={
                        "fps": 30.0,
                        "latency": 2,
                        "drops": 0,
                        "lastUpdateAge": 16
                    },
                    children=[
                        DebugTreeNode(
                            id="camera_discovery",
                            name="Camera Discovery",
                            status=NodeStatus.OK,
                            reason="2 cameras found",
                            metrics={"lastUpdateAge": 1000}
                        ),
                        DebugTreeNode(
                            id="camera_capture",
                            name="Camera Capture",
                            status=NodeStatus.OK,
                            reason="Streaming",
                            metrics={
                                "fps": 30.0,
                                "latency": 1,
                                "drops": 0,
                                "lastUpdateAge": 16
                            }
                        )
                    ]
                ),
                DebugTreeNode(
                    id="vision_pipeline",
                    name="Vision Pipeline",
                    status=NodeStatus.WARN,
                    reason="No camera open",
                    metrics={
                        "fps": 0.0,
                        "latency": 0,
                        "lastUpdateAge": 5000
                    },
                    children=[
                        DebugTreeNode(
                            id="preprocess",
                            name="Preprocess",
                            status=NodeStatus.STALE,
                            reason="No input",
                            metrics={
                                "fps": 0.0,
                                "lastUpdateAge": 5000
                            }
                        ),
                        DebugTreeNode(
                            id="detection",
                            name="Tag Detection",
                            status=NodeStatus.STALE,
                            reason="No input",
                            metrics={
                                "fps": 0.0,
                                "latency": 0,
                                "lastUpdateAge": 5000
                            }
                        )
                    ]
                ),
                DebugTreeNode(
                    id="webserver",
                    name="Web Server",
                    status=NodeStatus.OK,
                    reason="Listening on :8080",
                    metrics={"lastUpdateAge": 0}
                )
            ]
        )
    
    def get_tree(self) -> DebugTreeNode:
        """Get the current debug tree with updated camera status."""
        # Update Host node with CPU/GPU usage
        for child in self.root_node.children:
            if child.id == "host":
                usage = _get_cpu_gpu_usage()
                child.metrics = {k: v for k, v in usage.items() if v is not None}
                reason_parts = []
                if usage.get("cpu_percent") is not None:
                    reason_parts.append(f"CPU {usage['cpu_percent']}%")
                if usage.get("gpu_percent") is not None:
                    reason_parts.append(f"GPU {usage['gpu_percent']}%")
                if reason_parts:
                    child.reason = " | ".join(reason_parts)
                break

        # Update camera capture node with real metrics
        camera_manager_node = None
        camera_capture_node = None

        # Find camera_manager and camera_capture nodes
        for child in self.root_node.children:
            if child.id == "camera_manager":
                camera_manager_node = child
                for subchild in child.children:
                    if subchild.id == "camera_capture":
                        camera_capture_node = subchild
                        break
                break
        
        # Add/update individual camera nodes
        if camera_manager_node:
            self._update_camera_nodes(camera_manager_node)
        
        # Update vision pipeline node with real metrics
        vision_pipeline_node = None
        for child in self.root_node.children:
            if child.id == "vision_pipeline":
                vision_pipeline_node = child
                break
        
        if vision_pipeline_node:
            self._update_vision_pipeline_node(vision_pipeline_node)
        
        # Update camera_capture node and Camera Manager node with real metrics if camera service available
        if camera_capture_node and self.camera_service:
            managers = self.camera_service.get_all_camera_managers()
            if managers:
                # Aggregate metrics from all open cameras
                total_fps = 0.0
                total_drops = 0
                total_frames = 0
                max_age = 0.0
                open_count = 0
                
                for camera_id, manager in managers.items():
                    if manager.is_open():
                        metrics = manager.get_metrics()
                        total_fps += metrics.get("fps", 0.0)
                        total_drops += metrics.get("frames_dropped", 0)
                        total_frames += metrics.get("frames_captured", 0)
                        age = metrics.get("last_frame_age", 0.0)  # Already in milliseconds
                        if age > max_age:
                            max_age = age
                        open_count += 1
                
                avg_fps = round(total_fps / open_count, 1) if open_count > 0 else 0.0
                if open_count > 0:
                    camera_capture_node.status = NodeStatus.OK
                    camera_capture_node.reason = f"{open_count} camera(s) streaming"
                    camera_capture_node.metrics = {
                        "fps": avg_fps,
                        "latency": 1,
                        "drops": total_drops,
                        "frames_captured": total_frames,  # Add total frames captured
                        "lastUpdateAge": int(max_age)  # Already in milliseconds, don't multiply
                    }
                    # Camera Manager row: show same aggregate FPS as children
                    if camera_manager_node:
                        camera_manager_node.status = NodeStatus.OK
                        camera_manager_node.reason = f"{open_count} camera(s) @ {avg_fps} fps"
                        camera_manager_node.metrics = {
                            "fps": avg_fps,
                            "latency": 1,
                            "drops": total_drops,
                            "lastUpdateAge": int(max_age)
                        }
                else:
                    camera_capture_node.status = NodeStatus.WARN
                    camera_capture_node.reason = "No cameras open"
                    camera_capture_node.metrics = {
                        "fps": 0.0,
                        "latency": 0,
                        "drops": 0,
                        "lastUpdateAge": 5000
                    }
                    if camera_manager_node:
                        camera_manager_node.status = NodeStatus.OK
                        camera_manager_node.reason = "Running"
                        camera_manager_node.metrics = {"fps": 0.0, "latency": 0, "drops": 0, "lastUpdateAge": 5000}
            else:
                camera_capture_node.status = NodeStatus.WARN
                camera_capture_node.reason = "No cameras open"
                camera_capture_node.metrics = {
                    "fps": 0.0,
                    "latency": 0,
                    "drops": 0,
                    "lastUpdateAge": 5000
                }
                if camera_manager_node:
                    camera_manager_node.status = NodeStatus.OK
                    camera_manager_node.reason = "Running"
                    camera_manager_node.metrics = {"fps": 0.0, "latency": 0, "drops": 0, "lastUpdateAge": 5000}
        
        return self.root_node
    
    def _update_camera_nodes(self, camera_manager_node: DebugTreeNode) -> None:
        """Add or update individual camera nodes under camera_manager."""
        # Get list of detected cameras
        detected_cameras = []
        if self.camera_discovery:
            try:
                camera_list = self.camera_discovery.get_camera_list()
                # get_camera_list() returns a list directly, not a dict with "cameras" key
                if isinstance(camera_list, list):
                    detected_cameras = camera_list
                elif isinstance(camera_list, dict):
                    detected_cameras = camera_list.get("cameras", [])
            except Exception as e:
                self.logger.warning(f"[DebugTree] Failed to get camera list for debug tree: {e}")
        
        # Update Camera Discovery node with actual count
        for child in camera_manager_node.children:
            if child.id == "camera_discovery":
                n = len(detected_cameras)
                child.reason = f"{n} camera{'s' if n != 1 else ''} found"
                child.metrics = {"lastUpdateAge": 0}
                break
        
        # Get camera managers for open cameras
        camera_managers = {}
        if self.camera_service:
            camera_managers = self.camera_service.get_all_camera_managers()
        
        # Create a set of camera IDs that should be in the tree
        camera_ids_in_tree = set()
        for camera in detected_cameras:
            camera_ids_in_tree.add(camera.get("id", ""))
        
        # Remove camera nodes that are no longer detected
        camera_manager_node.children = [
            child for child in camera_manager_node.children 
            if not child.id.startswith("camera_") or child.id in ["camera_discovery", "camera_capture"] or child.id in camera_ids_in_tree
        ]
        
        # Add or update camera nodes
        for camera in detected_cameras:
            camera_id = camera.get("id", "")
            if not camera_id:
                continue
            
            # Find existing camera node
            camera_node = None
            for child in camera_manager_node.children:
                if child.id == camera_id:
                    camera_node = child
                    break
            
            # Get camera name
            camera_name = camera.get("name", camera_id)
            if camera.get("custom_name"):
                camera_name = camera.get("custom_name")
            
            # Get camera status
            is_open = camera_id in camera_managers and camera_managers[camera_id].is_open()
            status = NodeStatus.OK if is_open else NodeStatus.WARN
            reason = "Open and streaming" if is_open else "Not open"
            
            # Get camera metrics if open
            metrics = {}
            if is_open:
                manager = camera_managers[camera_id]
                manager_metrics = manager.get_metrics()
                metrics = {
                    "fps": manager_metrics.get("fps", 0.0),
                    "drops": manager_metrics.get("frames_dropped", 0),
                    "frames_captured": manager_metrics.get("frames_captured", 0),
                    "lastUpdateAge": manager_metrics.get("last_frame_age", 0)
                }
            else:
                metrics = {
                    "fps": 0.0,
                    "drops": 0,
                    "frames_captured": 0,
                    "lastUpdateAge": 5000
                }
            
            # Create or update camera node
            if camera_node:
                camera_node.name = camera_name
                camera_node.status = status
                camera_node.reason = reason
                camera_node.metrics = metrics
            else:
                # Insert camera nodes before camera_discovery and camera_capture
                camera_node = DebugTreeNode(
                    id=camera_id,
                    name=camera_name,
                    status=status,
                    reason=reason,
                    metrics=metrics
                )
                # Insert at the end, after camera_discovery and camera_capture
                camera_manager_node.children.append(camera_node)
    
    def _update_vision_pipeline_node(self, vision_pipeline_node: DebugTreeNode) -> None:
        """Update vision pipeline node with per-camera pipeline metrics."""
        if not self.camera_service:
            return
        
        # Get all camera managers
        managers = self.camera_service.get_all_camera_managers()
        
        # Find cameras with vision pipelines
        pipeline_cameras = []
        total_preprocess_fps = 0.0
        total_tags_detected = 0
        total_frames_processed = 0
        active_pipeline_count = 0
        
        for camera_id, manager in managers.items():
            if manager.is_open() and hasattr(manager, 'vision_pipeline') and manager.vision_pipeline:
                pipeline = manager.vision_pipeline
                metrics = pipeline.get_metrics()
                
                frames_processed = metrics.get("frames_processed", 0)
                detections_count = metrics.get("detections_count", 0)
                latest_detections_count = metrics.get("latest_detections_count", 0)
                
                # Estimate FPS from frames_processed (assuming ~30fps processing)
                # This is approximate - we could track timing if needed
                camera_metrics = manager.get_metrics()
                camera_fps = camera_metrics.get("fps", 0.0)
                preprocess_fps = camera_fps  # Preprocess FPS matches camera FPS
                
                total_preprocess_fps += preprocess_fps
                total_tags_detected += latest_detections_count
                total_frames_processed += frames_processed
                active_pipeline_count += 1
                
                # Get camera name
                camera_name = camera_id
                if self.camera_discovery:
                    try:
                        cameras = self.camera_discovery.get_camera_list()
                        for cam in cameras:
                            if cam.get("id") == camera_id:
                                camera_name = cam.get("custom_name") or cam.get("name", camera_id)
                                break
                    except:
                        pass
                
                pipeline_cameras.append({
                    "camera_id": camera_id,
                    "camera_name": camera_name,
                    "preprocess_fps": preprocess_fps,
                    "tags_detected": latest_detections_count,
                    "frames_processed": frames_processed,
                    "total_detections": detections_count
                })
        
        # Update vision pipeline status
        if active_pipeline_count > 0:
            vision_pipeline_node.status = NodeStatus.OK
            vision_pipeline_node.reason = f"{active_pipeline_count} camera pipeline(s) active"
            avg_preprocess_fps = total_preprocess_fps / active_pipeline_count if active_pipeline_count > 0 else 0.0
            vision_pipeline_node.metrics = {
                "fps": round(avg_preprocess_fps, 1),
                "tags_detected": total_tags_detected,
                "frames_processed": total_frames_processed,
                "lastUpdateAge": 100
            }
        else:
            vision_pipeline_node.status = NodeStatus.OK  # OK when no cameras, not WARN
            vision_pipeline_node.reason = "No cameras with pipeline open"
            vision_pipeline_node.metrics = {
                "fps": 0.0,
                "tags_detected": 0,
                "frames_processed": 0,
                "lastUpdateAge": 5000
            }
        
        # Update preprocess and detection child nodes
        preprocess_node = None
        detection_node = None
        for child in vision_pipeline_node.children:
            if child.id == "preprocess":
                preprocess_node = child
            elif child.id == "detection":
                detection_node = child
        
        # Update preprocess node
        if preprocess_node:
            if active_pipeline_count > 0:
                avg_preprocess_fps = total_preprocess_fps / active_pipeline_count if active_pipeline_count > 0 else 0.0
                preprocess_node.status = NodeStatus.OK
                preprocess_node.reason = f"Processing {active_pipeline_count} camera(s)"
                preprocess_node.metrics = {
                    "fps": round(avg_preprocess_fps, 1),
                    "lastUpdateAge": 100
                }
            else:
                preprocess_node.status = NodeStatus.STALE
                preprocess_node.reason = "No input"
                preprocess_node.metrics = {
                    "fps": 0.0,
                    "lastUpdateAge": 5000
                }
        
        # Update detection node
        if detection_node:
            if active_pipeline_count > 0:
                detection_node.status = NodeStatus.OK
                detection_node.reason = f"{total_tags_detected} tag(s) detected"
                detection_node.metrics = {
                    "fps": round(total_preprocess_fps / active_pipeline_count, 1) if active_pipeline_count > 0 else 0.0,
                    "tags_detected": total_tags_detected,
                    "latency": 10,  # Approximate detection latency
                    "lastUpdateAge": 100
                }
            else:
                detection_node.status = NodeStatus.STALE
                detection_node.reason = "No input"
                detection_node.metrics = {
                    "fps": 0.0,
                    "tags_detected": 0,
                    "latency": 0,
                    "lastUpdateAge": 5000
                }
        
        # Create/update per-camera pipeline nodes
        # Remove old pipeline camera nodes that no longer exist
        vision_pipeline_node.children = [
            child for child in vision_pipeline_node.children 
            if child.id in ["preprocess", "detection"] or any(p["camera_id"] == child.id for p in pipeline_cameras)
        ]
        
        # Add/update per-camera pipeline nodes
        for pipeline_data in pipeline_cameras:
            camera_id = pipeline_data["camera_id"]
            camera_name = pipeline_data["camera_name"]
            
            # Find existing pipeline camera node
            pipeline_camera_node = None
            for child in vision_pipeline_node.children:
                if child.id == camera_id:
                    pipeline_camera_node = child
                    break
            
            if pipeline_camera_node:
                # Update existing node
                pipeline_camera_node.name = f"{camera_name} Pipeline"
                pipeline_camera_node.status = NodeStatus.OK
                pipeline_camera_node.reason = f"{pipeline_data['tags_detected']} tag(s)"
                pipeline_camera_node.metrics = {
                    "fps": round(pipeline_data["preprocess_fps"], 1),
                    "tags_detected": pipeline_data["tags_detected"],
                    "frames_processed": pipeline_data["frames_processed"],
                    "lastUpdateAge": 100
                }
            else:
                # Create new node (insert after preprocess and detection)
                pipeline_camera_node = DebugTreeNode(
                    id=camera_id,
                    name=f"{camera_name} Pipeline",
                    status=NodeStatus.OK,
                    reason=f"{pipeline_data['tags_detected']} tag(s)",
                    metrics={
                        "fps": round(pipeline_data["preprocess_fps"], 1),
                        "tags_detected": pipeline_data["tags_detected"],
                        "frames_processed": pipeline_data["frames_processed"],
                        "lastUpdateAge": 100
                    }
                )
                vision_pipeline_node.children.append(pipeline_camera_node)
    
    def get_top_faults(self, max_faults: int = 5) -> List[Dict[str, Any]]:
        """Collect nodes with status != OK from the tree, ordered by severity (ERROR > STALE > WARN)."""
        root = self.get_tree()
        faults: List[Dict[str, Any]] = []

        def severity_order(status: NodeStatus) -> int:
            order = {NodeStatus.ERROR: 3, NodeStatus.STALE: 2, NodeStatus.WARN: 1, NodeStatus.OK: 0}
            return order.get(status, 0)

        def walk(node: DebugTreeNode, path_parts: List[str]) -> None:
            path = " > ".join(path_parts) if path_parts else node.name
            if node.status != NodeStatus.OK:
                faults.append({
                    "path": path,
                    "node_id": node.id,
                    "name": node.name,
                    "status": node.status.value,
                    "reason": node.reason,
                    "metrics": node.metrics or {},
                })
            for child in node.children:
                walk(child, path_parts + [child.name])

        walk(root, [root.name])
        faults.sort(key=lambda f: severity_order(NodeStatus(f["status"])), reverse=True)
        return faults[:max_faults]

    def get_tree_dict(self) -> dict:
        """Get debug tree as dictionary."""
        return self.get_tree().to_dict()
