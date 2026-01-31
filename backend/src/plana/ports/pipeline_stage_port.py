"""Pipeline stage port for modular vision pipeline stages.

Each stage has a name and process(frame, context) -> (frame, context).
The pipeline runs stages in order; context carries detections and metadata.
Stages can be swapped, added, or reordered without changing VisionPipeline.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional
import numpy as np


class PipelineStagePort(ABC):
    """Port for a single pipeline stage. Implement to add or replace stages."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stage name (e.g. 'preprocess', 'detect_overlay'). Used for frame storage and get_latest_frame(stage)."""
        pass

    @abstractmethod
    def process(self, frame: np.ndarray, context: Dict[str, Any]) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
        """Run this stage.

        Args:
            frame: Input frame (grayscale or BGR depending on stage).
            context: Mutable dict with 'raw_frame', 'detections', etc. Update in place or return updated.

        Returns:
            (output_frame, context). output_frame is stored under self.name if not None.
        """
        pass
