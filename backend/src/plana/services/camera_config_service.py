"""Camera configuration service for SVTVision."""

import json
from pathlib import Path
from typing import Dict, Optional, Any
from .logging_service import LoggingService


class CameraConfigService:
    """Service for managing camera configuration and naming.
    
    Camera names are stored in cameras.json.
    Camera settings are stored in separate files: config/cameras/{camera_id}.json
    """
    
    def __init__(self, config_dir: Path, logger: LoggingService):
        self.config_dir = config_dir
        self.logger = logger
        self.config_file = config_dir / "cameras.json"  # Only for camera names
        self.cameras_dir = config_dir / "cameras"  # Directory for per-camera settings
        self.cameras_dir.mkdir(parents=True, exist_ok=True)
        self.camera_names: Dict[str, Dict[str, str]] = {}
        self._load_names_config()
    
    def _load_names_config(self):
        """Load camera names configuration from JSON file."""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    self.camera_names = data.get("camera_names", {})
                self.logger.info(f"Loaded camera names from {self.config_file}: {len(self.camera_names)} cameras")
            except Exception as e:
                self.logger.error(f"Failed to load camera names: {e}")
                self.camera_names = {}
        else:
            # Create default config file
            self.camera_names = {}
            self._save_names_config()
            self.logger.info(f"Created new camera names file: {self.config_file}")
    
    def _save_names_config(self):
        """Save camera names configuration to JSON file."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                "camera_names": self.camera_names,
                "version": "1.0"
            }
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=2)
            self.logger.info(f"Saved camera names to {self.config_file}")
        except Exception as e:
            self.logger.error(f"Failed to save camera names: {e}")
    
    def _get_camera_settings_file(self, camera_id: str) -> Path:
        """Get the path to a camera's settings file."""
        # Sanitize camera_id for filename (replace special chars)
        safe_id = camera_id.replace('/', '_').replace('\\', '_')
        return self.cameras_dir / f"{safe_id}.json"
    
    def _load_camera_settings(self, camera_id: str) -> Dict[str, Any]:
        """Load settings for a specific camera from its settings file."""
        settings_file = self._get_camera_settings_file(camera_id)
        if settings_file.exists():
            try:
                with open(settings_file, 'r') as f:
                    settings = json.load(f)
                self.logger.debug(f"Loaded settings for camera {camera_id} from {settings_file}")
                return settings
            except Exception as e:
                self.logger.error(f"Failed to load settings for camera {camera_id}: {e}")
                return {}
        return {}
    
    def _save_camera_settings(self, camera_id: str, settings: Dict[str, Any]) -> None:
        """Save settings for a specific camera to its settings file."""
        settings_file = self._get_camera_settings_file(camera_id)
        try:
            with open(settings_file, 'w') as f:
                json.dump(settings, f, indent=2)
            self.logger.debug(f"Saved settings for camera {camera_id} to {settings_file}")
        except Exception as e:
            self.logger.error(f"Failed to save settings for camera {camera_id}: {e}")
    
    def get_camera_name(self, camera_id: str) -> Optional[str]:
        """Get custom name for a camera."""
        name_info = self.camera_names.get(camera_id)
        if name_info:
            return name_info.get("name")
        return None
    
    def migrate_old_config(self, old_id: str, new_id: str):
        """Migrate camera config from old ID to new ID."""
        if old_id in self.camera_names and new_id not in self.camera_names:
            self.camera_names[new_id] = self.camera_names[old_id]
            self._save_config()
            self.logger.info(f"Migrated camera config from {old_id} to {new_id}")
    
    def set_camera_name(
        self, 
        camera_id: str, 
        position: str, 
        side: Optional[str] = None
    ):
        """Set camera name based on position and side.
        
        Args:
            camera_id: Stable camera ID
            position: 'front', 'middle', or 'back'
            side: 'left', 'right', or None
        """
        # Build name: position + side (if provided)
        if side:
            name = f"{position}-{side}"
        else:
            name = position
        
        # Ensure camera config exists
        if camera_id not in self.camera_names:
            self.camera_names[camera_id] = {}
        
        self.camera_names[camera_id].update({
            "name": name,
            "position": position,
            "side": side
        })
        self._save_config()
        self.logger.info(f"Set camera {camera_id} name to '{name}'")
    
    def set_camera_resolution_fps(
        self,
        camera_id: str,
        format: str,
        width: int,
        height: int,
        fps: float
    ):
        """Set camera resolution and FPS configuration.
        
        Args:
            camera_id: Stable camera ID
            format: Pixel format (e.g., 'YUYV')
            width: Resolution width
            height: Resolution height
            fps: Frames per second
        """
        # Save to per-camera settings file
        self.set_camera_settings(camera_id, {
            "resolution": {
                "format": format,
                "width": width,
                "height": height,
                "fps": fps
            }
        })
        self.logger.info(f"Set camera {camera_id} resolution to {width}x{height} @ {fps}fps ({format})")
    
    def get_camera_resolution_fps(self, camera_id: str) -> Optional[Dict]:
        """Get camera resolution and FPS configuration."""
        settings = self._load_camera_settings(camera_id)
        if settings and "resolution" in settings:
            return settings["resolution"]
        return None
    
    def get_all_camera_names(self) -> Dict[str, Dict[str, str]]:
        """Get all camera name mappings."""
        return self.camera_names.copy()
    
    def get_camera_config(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Get full config for a camera (name + settings)."""
        # Get name info from cameras.json
        name_info = self.camera_names.get(camera_id, {}).copy()
        
        # Get settings from per-camera file
        settings = self._load_camera_settings(camera_id)
        
        # Merge name info with settings
        if name_info or settings:
            config = {**name_info, **settings}
            return config
        return None
    
    def get_camera_settings(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Get camera settings from the per-camera settings file.
        
        Returns all settings including resolution, controls, etc.
        """
        settings = self._load_camera_settings(camera_id)
        return settings if settings else None
    
    def set_camera_settings(self, camera_id: str, settings: Dict[str, Any]) -> None:
        """Set camera settings.
        
        This method saves ALL settings from the settings dict to the camera's
        per-camera settings file. Settings are merged with existing settings.
        """
        # Load existing settings
        existing_settings = self._load_camera_settings(camera_id)
        
        # Merge new settings with existing
        existing_settings.update(settings)
        
        # Save merged settings
        self._save_camera_settings(camera_id, existing_settings)
        self.logger.info(f"Saved settings for camera {camera_id}: {list(settings.keys())}")
