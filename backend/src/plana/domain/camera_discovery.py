"""Camera discovery domain service."""

from typing import List, Dict, Any, Optional
from ..ports.camera_discovery_port import CameraDiscoveryPort
from ..services.message_bus import MessageBus
from ..services.logging_service import LoggingService
from ..services.camera_config_service import CameraConfigService


class CameraDiscovery:
    """Domain service for camera discovery."""
    
    def __init__(
        self,
        discovery_port: CameraDiscoveryPort,
        message_bus: MessageBus,
        logger: LoggingService,
        camera_config_service: Optional[CameraConfigService] = None
    ):
        self.discovery_port = discovery_port
        self.message_bus = message_bus
        self.logger = logger
        self.camera_config_service = camera_config_service
        self._cameras: List[Dict[str, Any]] = []
        self._update_cameras()
    
    def get_camera_list(self) -> List[Dict[str, Any]]:
        """Get list of all cameras with custom names applied."""
        cameras = self._cameras.copy()
        # Apply custom names if available
        if self.camera_config_service:
            for camera in cameras:
                custom_name = self.camera_config_service.get_camera_name(camera["id"])
                if custom_name:
                    camera["name"] = custom_name
                    camera["custom_name"] = custom_name
                camera["config"] = self.camera_config_service.get_camera_config(camera["id"])
        return cameras
    
    def get_camera_details(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a camera."""
        return self.discovery_port.get_camera_details(camera_id)
    
    def get_camera_capabilities(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Get camera capabilities."""
        return self.discovery_port.get_camera_capabilities(camera_id)
    
    def get_camera_controls(self, camera_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get camera controls."""
        return self.discovery_port.get_camera_controls(camera_id)
    
    def refresh(self):
        """Refresh camera list and publish updates."""
        old_ids = {c["id"] for c in self._cameras}
        self._update_cameras()
        new_ids = {c["id"] for c in self._cameras}
        
        # Publish changes
        if old_ids != new_ids:
            self.message_bus.publish("camera_list_updated", {
                "cameras": self._cameras
            })
            self.logger.info(f"[Discovery] Camera list updated: {len(self._cameras)} cameras")
    
    def _update_cameras(self):
        """Update internal camera list."""
        try:
            self._cameras = self.discovery_port.discover_cameras()
        except Exception as e:
            self.logger.error(f"[Discovery] Error updating camera list: {e}")
            self._cameras = []
