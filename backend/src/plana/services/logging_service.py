"""Minimal logging service for SVTVision."""

import logging
from typing import Optional


class LoggingService:
    """Minimal logging service for application-wide logging."""
    
    def __init__(self):
        self.logger = logging.getLogger("plana")
        self.logger.setLevel(logging.INFO)
        
        # Console handler
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(logging.INFO)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def info(self, message: str):
        """Log info message."""
        self.logger.info(message)
    
    def warning(self, message: str):
        """Log warning message."""
        self.logger.warning(message)
    
    def error(self, message: str):
        """Log error message."""
        self.logger.error(message)
    
    def debug(self, message: str):
        """Log debug message."""
        self.logger.debug(message)
