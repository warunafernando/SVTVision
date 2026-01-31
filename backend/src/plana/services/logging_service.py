"""Minimal logging service for SVTVision.

Log messages use section prefixes for filtering and debugging:
  [App] Application lifecycle, auto-start, hot-plug
  [Config] / [CameraConfig] Configuration load/save
  [Discovery] Camera discovery (UVC/v4l2)
  [Camera] / [CameraManager] / [CameraService] Camera open/close, capture, pipeline
  [Stream] WebSocket streaming, settings apply
  [Pipeline] Vision pipeline, detection stats
  [Preprocess] Preprocessing adapter
  [AprilTag] AprilTag detector
  [SelfTest] Self-test runner
  [DebugTree] Debug tree builder
  [MessageBus] Pub/sub (debug level)

Levels: DEBUG=verbose, INFO=normal flow, WARNING=recoverable, ERROR=failures.
Set LOG_LEVEL=DEBUG in environment to see debug messages (e.g. [MessageBus], [Discovery] details).
"""

import logging
import os
from typing import Optional


class LoggingService:
    """Minimal logging service for application-wide logging."""
    
    def __init__(self):
        self.logger = logging.getLogger("plana")
        level_name = (os.environ.get("LOG_LEVEL") or "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)
        self.logger.setLevel(level)
        
        # Console handler
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(level)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def info(self, message: str, **kwargs):
        """Log info message."""
        self.logger.info(message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self.logger.warning(message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message (kwargs e.g. exc_info=True for traceback)."""
        self.logger.error(message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self.logger.debug(message, **kwargs)
