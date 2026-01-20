"""Self-test runner for PlanA."""

from typing import Dict, Any, Optional
from ..services.logging_service import LoggingService


class SelfTestRunner:
    """Runner for self-tests."""
    
    def __init__(self, logger: LoggingService, camera_discovery=None, camera_service=None):
        self.logger = logger
        self.camera_discovery = camera_discovery
        self.camera_service = camera_service
    
    def run_test(self, test_name: str) -> Dict[str, Any]:
        """Run a self-test."""
        self.logger.info(f"Running self-test: {test_name}")
        
        if test_name == "smoke":
            return self._run_smoke_test()
        elif test_name == "camera_discovery_deep":
            return self._run_camera_discovery_deep_test()
        elif test_name == "open_stream":
            return self._run_open_stream_test()
        elif test_name == "settings_roundtrip":
            return self._run_settings_roundtrip_test()
        else:
            return {
                "test": test_name,
                "pass": False,
                "message": f"Unknown test: {test_name}"
            }
    
    def _run_smoke_test(self) -> Dict[str, Any]:
        """Run smoke test."""
        return {
            "test": "smoke",
            "pass": True,
            "message": "Smoke test passed"
        }
    
    def _run_camera_discovery_deep_test(self) -> Dict[str, Any]:
        """Run deep camera discovery test."""
        if not self.camera_discovery:
            return {
                "test": "camera_discovery_deep",
                "pass": False,
                "message": "Camera discovery not available"
            }
        
        cameras = self.camera_discovery.get_camera_list()
        
        if len(cameras) == 0:
            return {
                "test": "camera_discovery_deep",
                "pass": False,
                "status": "WARN",
                "message": "No cameras found",
                "details": {
                    "camera_count": 0
                }
            }
        
        # Test deep capabilities for each camera
        details_ok = True
        capabilities_ok = True
        controls_ok = True
        
        for camera in cameras:
            camera_id = camera["id"]
            
            # Test details
            details = self.camera_discovery.get_camera_details(camera_id)
            if not details or not details.get("usb_info"):
                details_ok = False
            
            # Test capabilities
            capabilities = self.camera_discovery.get_camera_capabilities(camera_id)
            if not capabilities:
                capabilities_ok = False
            
            # Test controls
            controls = self.camera_discovery.get_camera_controls(camera_id)
            if controls is None:
                controls_ok = False
        
        all_ok = details_ok and capabilities_ok and controls_ok
        
        return {
            "test": "camera_discovery_deep",
            "pass": all_ok,
            "status": "PASS" if all_ok else "WARN",
            "message": f"Camera discovery deep test: {len(cameras)} cameras found" + (
                "" if all_ok else " (some capabilities incomplete)"
            ),
            "details": {
                "camera_count": len(cameras),
                "details_ok": details_ok,
                "capabilities_ok": capabilities_ok,
                "controls_ok": controls_ok
            }
        }
    
    def _run_open_stream_test(self) -> Dict[str, Any]:
        """Run camera open/stream test."""
        import time
        
        if not self.camera_discovery:
            return {
                "test": "open_stream",
                "pass": False,
                "message": "Camera discovery not available"
            }
        
        if not self.camera_service:
            return {
                "test": "open_stream",
                "pass": False,
                "message": "Camera service not available"
            }
        
        cameras = self.camera_discovery.get_camera_list()
        
        if len(cameras) == 0:
            return {
                "test": "open_stream",
                "pass": False,
                "status": "WARN",
                "message": "No cameras found for streaming test",
                "details": {
                    "camera_count": 0
                }
            }
        
        # Test first camera
        test_camera = cameras[0]
        camera_id = test_camera["id"]
        device_path = test_camera.get("device_path")
        
        if not device_path:
            return {
                "test": "open_stream",
                "pass": False,
                "message": f"Camera {camera_id} has no device path"
            }
        
        # Try to open camera
        try:
            opened = self.camera_service.open_camera(camera_id, device_path)
            if not opened:
                return {
                    "test": "open_stream",
                    "pass": False,
                    "message": f"Failed to open camera {camera_id}",
                    "details": {
                        "camera_id": camera_id,
                        "device_path": device_path
                    }
                }
            
            # Wait a bit and capture some frames
            time.sleep(1.0)
            
            manager = self.camera_service.get_camera_manager(camera_id)
            if not manager:
                self.camera_service.close_camera(camera_id)
                return {
                    "test": "open_stream",
                    "pass": False,
                    "message": "Camera manager not found after open"
                }
            
            # Get metrics
            metrics = manager.get_metrics()
            frames_captured = metrics.get("frames_captured", 0)
            
            # Close camera
            self.camera_service.close_camera(camera_id)
            
            # Test passes if we got at least a few frames
            success = frames_captured > 0
            
            return {
                "test": "open_stream",
                "pass": success,
                "status": "PASS" if success else "FAIL",
                "message": f"Camera stream test: {frames_captured} frames captured" + (
                    "" if success else " (no frames captured)"
                ),
                "details": {
                    "camera_id": camera_id,
                    "device_path": device_path,
                    "frames_captured": frames_captured,
                    "fps": metrics.get("fps", 0),
                    "drops": metrics.get("frames_dropped", 0)
                }
            }
            
        except Exception as e:
            # Make sure to close camera on error
            try:
                self.camera_service.close_camera(camera_id)
            except:
                pass
            
            return {
                "test": "open_stream",
                "pass": False,
                "message": f"Exception during stream test: {str(e)}",
                "details": {
                    "camera_id": camera_id,
                    "error": str(e)
                }
            }
    
    def _run_settings_roundtrip_test(self) -> Dict[str, Any]:
        """Run settings roundtrip test (save/apply/verify)."""
        import time
        
        if not self.camera_discovery:
            return {
                "test": "settings_roundtrip",
                "pass": False,
                "message": "Camera discovery not available"
            }
        
        if not self.camera_service:
            return {
                "test": "settings_roundtrip",
                "pass": False,
                "message": "Camera service not available"
            }
        
        cameras = self.camera_discovery.get_camera_list()
        
        if len(cameras) == 0:
            return {
                "test": "settings_roundtrip",
                "pass": False,
                "status": "WARN",
                "message": "No cameras found for settings test",
                "details": {
                    "camera_count": 0
                }
            }
        
        # Test first camera
        test_camera = cameras[0]
        camera_id = test_camera["id"]
        device_path = test_camera.get("device_path")
        
        if not device_path:
            return {
                "test": "settings_roundtrip",
                "pass": False,
                "message": f"Camera {camera_id} has no device path"
            }
        
        try:
            # Test settings: 640x480 @ 30fps
            test_width = 640
            test_height = 480
            test_fps = 30.0
            test_format = "YUYV"
            
            # Open camera
            opened = self.camera_service.open_camera(camera_id, device_path, test_width, test_height, test_fps, test_format)
            if not opened:
                return {
                    "test": "settings_roundtrip",
                    "pass": False,
                    "message": f"Failed to open camera {camera_id}"
                }
            
            # Wait for settings to stabilize
            time.sleep(0.5)
            
            # Verify settings
            verification = self.camera_service.verify_camera_settings(
                camera_id, test_width, test_height, test_fps, test_format
            )
            
            verified = verification.get("verified", False)
            actual = verification.get("actual", {})
            
            # Close camera
            self.camera_service.close_camera(camera_id)
            
            return {
                "test": "settings_roundtrip",
                "pass": verified,
                "status": "PASS" if verified else "FAIL",
                "message": f"Settings roundtrip test: {'PASS' if verified else 'FAIL'}" + (
                    "" if verified else f" (expected {test_width}x{test_height}@{test_fps}fps, got {actual.get('width', '?')}x{actual.get('height', '?')}@{actual.get('fps', '?'):.1f}fps)"
                ),
                "details": {
                    "camera_id": camera_id,
                    "requested": {
                        "width": test_width,
                        "height": test_height,
                        "fps": test_fps,
                        "format": test_format
                    },
                    "actual": actual,
                    "verification": verification
                }
            }
            
        except Exception as e:
            # Make sure to close camera on error
            try:
                self.camera_service.close_camera(camera_id)
            except:
                pass
            
            return {
                "test": "settings_roundtrip",
                "pass": False,
                "message": f"Exception during settings test: {str(e)}",
                "details": {
                    "camera_id": camera_id,
                    "error": str(e)
                }
            }
