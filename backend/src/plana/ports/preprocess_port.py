"""Preprocessing port interface for image processing operations."""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import numpy as np


class PreprocessPort(ABC):
    """Port interface for image preprocessing operations."""
    
    @abstractmethod
    def preprocess(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Preprocess a raw frame.
        
        Args:
            frame: Raw frame as numpy array (BGR format from OpenCV)
        
        Returns:
            Preprocessed frame as numpy array, or None if preprocessing failed
        """
        pass
    
    @abstractmethod
    def get_config(self) -> Dict[str, Any]:
        """Get preprocessing configuration.
        
        Returns:
            Dict with preprocessing settings
        """
        pass
    
    @abstractmethod
    def set_config(self, config: Dict[str, Any]) -> bool:
        """Set preprocessing configuration.
        
        Args:
            config: Dict with preprocessing settings
        
        Returns:
            True if config set successfully
        """
        pass
