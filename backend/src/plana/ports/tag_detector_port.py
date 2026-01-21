"""Tag detector port interface for AprilTag detection operations."""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import numpy as np


class TagDetection:
    """AprilTag detection result."""
    
    def __init__(
        self,
        tag_id: int,
        corners: np.ndarray,  # 4x2 array of corner coordinates
        center: tuple[float, float],
        family: str = "tag36h11"
    ):
        self.tag_id = tag_id
        self.corners = corners  # 4 corners, each with (x, y)
        self.center = center  # (cx, cy)
        self.family = family
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert detection to dictionary."""
        return {
            "tag_id": self.tag_id,
            "corners": self.corners.tolist(),
            "center": self.center,
            "family": self.family
        }


class TagDetectorPort(ABC):
    """Port interface for AprilTag detection operations."""
    
    @abstractmethod
    def detect(self, frame: np.ndarray) -> List[TagDetection]:
        """Detect AprilTags in a frame.
        
        Args:
            frame: Preprocessed frame as numpy array (grayscale)
        
        Returns:
            List of TagDetection objects
        """
        pass
    
    @abstractmethod
    def draw_overlay(self, frame: np.ndarray, detections: List[TagDetection]) -> np.ndarray:
        """Draw detection overlay on frame.
        
        Args:
            frame: Frame to draw on (can be color or grayscale)
            detections: List of TagDetection objects
        
        Returns:
            Frame with overlay drawn (same format as input)
        """
        pass
