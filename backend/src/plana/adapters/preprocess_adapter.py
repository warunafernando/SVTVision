"""Preprocessing adapter implementation."""

import cv2
import numpy as np
from typing import Optional, Dict, Any
from ..ports.preprocess_port import PreprocessPort
from ..services.logging_service import LoggingService


class PreprocessAdapter(PreprocessPort):
    """Adapter for image preprocessing operations."""
    
    def __init__(self, logger: LoggingService):
        self.logger = logger
        self.config = {
            "blur_kernel_size": 3,  # Reduced blur for sharper edges (better for AprilTag)
            "threshold_type": "adaptive",  # "adaptive" or "binary"
            "adaptive_method": cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            "adaptive_threshold_type": cv2.THRESH_BINARY,
            "adaptive_block_size": 15,  # Increased for more stable threshold
            "adaptive_c": 3,  # Slightly increased for better contrast
            "binary_threshold": 127,
            "morphology": False,  # Disabled - can remove tag features
            "morph_kernel_size": 3
        }
        self.logger.info("PreprocessAdapter initialized")
    
    def preprocess(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Preprocess a raw frame.
        
        Processing steps:
        1. Convert to grayscale if needed
        2. Apply Gaussian blur
        3. Apply adaptive threshold
        4. Apply morphology operations (optional)
        """
        try:
            # Convert to grayscale if needed
            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame.copy()
            
            # Apply Gaussian blur
            blur_size = self.config["blur_kernel_size"]
            if blur_size > 0 and blur_size % 2 == 1:
                blurred = cv2.GaussianBlur(gray, (blur_size, blur_size), 0)
            else:
                blurred = gray
            
            # Apply threshold
            if self.config["threshold_type"] == "adaptive":
                # Adaptive threshold
                thresholded = cv2.adaptiveThreshold(
                    blurred,
                    255,
                    self.config["adaptive_method"],
                    self.config["adaptive_threshold_type"],
                    self.config["adaptive_block_size"],
                    self.config["adaptive_c"]
                )
            else:
                # Binary threshold
                _, thresholded = cv2.threshold(
                    blurred,
                    self.config["binary_threshold"],
                    255,
                    cv2.THRESH_BINARY
                )
            
            # Apply morphology operations (opening and closing)
            if self.config["morphology"]:
                kernel_size = self.config["morph_kernel_size"]
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
                processed = cv2.morphologyEx(thresholded, cv2.MORPH_CLOSE, kernel)
                processed = cv2.morphologyEx(processed, cv2.MORPH_OPEN, kernel)
            else:
                processed = thresholded
            
            return processed
        
        except Exception as e:
            self.logger.error(f"Error preprocessing frame: {e}")
            return None
    
    def get_config(self) -> Dict[str, Any]:
        """Get preprocessing configuration."""
        return self.config.copy()
    
    def set_config(self, config: Dict[str, Any]) -> bool:
        """Set preprocessing configuration."""
        try:
            # Validate and update config
            if "blur_kernel_size" in config:
                blur_size = int(config["blur_kernel_size"])
                if blur_size >= 0 and blur_size % 2 == 1:
                    self.config["blur_kernel_size"] = blur_size
                else:
                    self.logger.warning(f"Invalid blur_kernel_size: {blur_size} (must be odd >= 0)")
            
            if "threshold_type" in config:
                if config["threshold_type"] in ["adaptive", "binary"]:
                    self.config["threshold_type"] = config["threshold_type"]
            
            if "adaptive_block_size" in config:
                block_size = int(config["adaptive_block_size"])
                if block_size >= 3 and block_size % 2 == 1:
                    self.config["adaptive_block_size"] = block_size
            
            if "adaptive_c" in config:
                self.config["adaptive_c"] = float(config["adaptive_c"])
            
            if "binary_threshold" in config:
                threshold = int(config["binary_threshold"])
                if 0 <= threshold <= 255:
                    self.config["binary_threshold"] = threshold
            
            if "morphology" in config:
                self.config["morphology"] = bool(config["morphology"])
            
            if "morph_kernel_size" in config:
                morph_size = int(config["morph_kernel_size"])
                if morph_size >= 1:
                    self.config["morph_kernel_size"] = morph_size
            
            self.logger.info(f"Preprocess config updated: {self.config}")
            return True
        
        except Exception as e:
            self.logger.error(f"Error setting preprocess config: {e}")
            return False
