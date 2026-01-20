"""Debug tree manager for maintaining the debug tree state."""

from typing import List, Optional
from .debug_tree import DebugTreeNode, NodeStatus
from ..services.health_service import HealthService
from ..services.logging_service import LoggingService


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
        
        # Update camera_capture node with real metrics if camera service available
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
                
                if open_count > 0:
                    camera_capture_node.status = NodeStatus.OK
                    camera_capture_node.reason = f"{open_count} camera(s) streaming"
                    camera_capture_node.metrics = {
                        "fps": round(total_fps / open_count, 1),
                        "latency": 1,
                        "drops": total_drops,
                        "frames_captured": total_frames,  # Add total frames captured
                        "lastUpdateAge": int(max_age)  # Already in milliseconds, don't multiply
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
            else:
                camera_capture_node.status = NodeStatus.WARN
                camera_capture_node.reason = "No cameras open"
                camera_capture_node.metrics = {
                    "fps": 0.0,
                    "latency": 0,
                    "drops": 0,
                    "lastUpdateAge": 5000
                }
        
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
                self.logger.warning(f"Failed to get camera list for debug tree: {e}")
        
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
    
    def get_tree_dict(self) -> dict:
        """Get debug tree as dictionary."""
        return self.get_tree().to_dict()
