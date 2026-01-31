"""Configuration service for SVTVision."""

import json
from pathlib import Path
from typing import Any, Dict, Optional
from ..services.logging_service import LoggingService


class ConfigService:
    """Service for managing application configuration."""
    
    def __init__(self, config_dir: Path, logger: LoggingService):
        self.config_dir = config_dir
        self.logger = logger
        self.config: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self):
        """Load configuration from files."""
        config_file = self.config_dir / "app.json"
        if config_file.exists():
            try:
                with open(config_file, 'r') as f:
                    self.config = json.load(f)
                self.logger.info(f"[Config] Loaded config from {config_file}")
            except Exception as e:
                self.logger.error(f"[Config] Failed to load config: {e}")
                self.config = {}
        else:
            # Default config
            self.config = {
                "app_name": "SVTVision",
                "build_id": "2024.01.20-dev",
                "version": "0.1.0"
            }
            self._save_config()
    
    def _save_config(self):
        """Save configuration to file."""
        config_file = self.config_dir / "app.json"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            self.logger.error(f"[Config] Failed to save config: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set configuration value."""
        self.config[key] = value
        self._save_config()
