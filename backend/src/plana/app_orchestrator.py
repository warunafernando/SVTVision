"""Application orchestrator for PlanA."""

from pathlib import Path
from .services.logging_service import LoggingService
from .services.config_service import ConfigService
from .services.health_service import HealthService, HealthStatus
from .services.message_bus import MessageBus
from .domain.debug_tree_manager import DebugTreeManager
from .domain.camera_discovery import CameraDiscovery
from .domain.camera_service import CameraService
from .adapters.uvc_v4l2_discovery import UVCV4L2DiscoveryAdapter
from .adapters.web_server import WebServerAdapter
from .adapters.selftest_runner import SelfTestRunner
from .services.camera_config_service import CameraConfigService
import threading
import time


class AppOrchestrator:
    """Orchestrates application startup and component lifecycle."""
    
    def __init__(self, config_dir: Path, frontend_dist_path: Path):
        # Initialize services in order
        self.logger = LoggingService()
        self.config_service = ConfigService(config_dir, self.logger)
        self.health_service = HealthService()
        self.message_bus = MessageBus(self.logger)
        
        # Initialize camera config service
        self.camera_config_service = CameraConfigService(config_dir, self.logger)
        
        # Initialize camera service (needed for debug tree)
        self.camera_service = CameraService(
            self.logger,
            self.camera_config_service
        )
        
        # Initialize domain managers
        self.debug_tree_manager = DebugTreeManager(
            self.health_service,
            self.logger,
            self.camera_service
        )
        
        # Initialize camera discovery
        discovery_adapter = UVCV4L2DiscoveryAdapter(self.logger)
        self.camera_discovery = CameraDiscovery(
            discovery_adapter,
            self.message_bus,
            self.logger,
            self.camera_config_service
        )
        
        # Initialize adapters
        self.self_test_runner = SelfTestRunner(
            self.logger,
            self.camera_discovery,
            self.camera_service
        )
        self.web_server = WebServerAdapter(
            self.config_service,
            self.health_service,
            self.debug_tree_manager,
            self.logger,
            self.self_test_runner,
            self.camera_discovery,
            self.camera_config_service,
            self.camera_service,
            frontend_dist_path
        )
        
        # Set initial health
        self.health_service.set_component_health(
            "webserver",
            HealthStatus.OK,
            "Listening on :8080"
        )
        self.health_service.set_component_health(
            "system",
            HealthStatus.OK,
            "All systems operational"
        )
        
        # Set camera discovery health
        camera_count = len(self.camera_discovery.get_camera_list())
        self.health_service.set_component_health(
            "camera_discovery",
            HealthStatus.OK if camera_count > 0 else HealthStatus.WARN,
            f"{camera_count} cameras found" if camera_count > 0 else "No cameras found"
        )
        
        # Auto-start cameras that have saved settings
        self._auto_start_cameras()

        # Start hot-plug monitoring (after web server is initialized)
        self._start_hotplug_monitoring()
    
    def _auto_start_cameras(self):
        """Auto-start cameras that have saved resolution/FPS settings."""
        cameras = self.camera_discovery.get_camera_list()
        if not cameras:
            self.logger.info("No cameras found for auto-start")
            return
        
        started_count = 0
        for camera in cameras:
            camera_id = camera["id"]
            device_path = camera.get("device_path")
            
            if not device_path:
                self.logger.warning(f"Camera {camera_id} has no device_path, skipping auto-start")
                continue
            
            # Check if camera has saved settings
            config = self.camera_config_service.get_camera_config(camera_id)
            if config and config.get("resolution"):
                res = config["resolution"]
                if res.get("format") and res.get("width") and res.get("height") and res.get("fps"):
                    # Auto-start this camera
                    try:
                        success = self.camera_service.open_camera(
                            camera_id,
                            device_path,
                            res.get("width"),
                            res.get("height"),
                            res.get("fps"),
                            res.get("format")
                        )
                        if success:
                            started_count += 1
                            self.logger.info(f"Auto-started camera {camera_id} with settings {res.get('width')}x{res.get('height')}@{res.get('fps')}fps")
                        else:
                            self.logger.warning(f"Failed to auto-start camera {camera_id}")
                    except Exception as e:
                        self.logger.error(f"Error auto-starting camera {camera_id}: {e}")
                else:
                    self.logger.debug(f"Camera {camera_id} has incomplete resolution settings, skipping auto-start")
            else:
                self.logger.debug(f"Camera {camera_id} has no saved settings, skipping auto-start")
        
        self.logger.info(f"Auto-started {started_count} camera(s) out of {len(cameras)} discovered")
        
        # Update health status
        if started_count > 0:
            self.health_service.set_component_health(
                "camera_manager",
                HealthStatus.OK,
                f"{started_count} camera(s) auto-started"
            )

    def _start_hotplug_monitoring(self):
        """Start hot-plug monitoring thread (checks every 3 seconds)."""
        def monitor():
            while True:
                try:
                    time.sleep(3)  # Check every 3 seconds
                    self.camera_discovery.refresh()
                except Exception as e:
                    self.logger.error(f"Error in hot-plug monitoring: {e}")
        
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        self.logger.info("Hot-plug monitoring started (3 second interval)")
    
    def start(self):
        """Start the application."""
        self.logger.info("Starting PlanA application...")
        self.logger.info(f"App: {self.config_service.get('app_name')}")
        self.logger.info(f"Build: {self.config_service.get('build_id')}")
        return self.web_server.get_app()
    
    def shutdown(self):
        """Shutdown the application."""
        self.logger.info("Shutting down PlanA application...")
