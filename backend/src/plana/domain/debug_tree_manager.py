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
        camera_service=None
    ):
        self.health_service = health_service
        self.logger = logger
        self.camera_service = camera_service
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
    
    def get_tree_dict(self) -> dict:
        """Get debug tree as dictionary."""
        return self.get_tree().to_dict()
