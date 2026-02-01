"""Pipeline instance: represents a running algorithm (camera + vision pipeline)."""

from typing import Optional, Dict, Any


class PipelineInstance:
    """A running pipeline instance (Phase 2: camera running AprilTag pipeline)."""

    def __init__(
        self,
        instance_id: str,
        algorithm_id: str,
        target: str,
        state: str,
        vision_pipeline=None,
    ):
        self.instance_id = instance_id
        self.algorithm_id = algorithm_id
        self.target = target
        self.state = state
        self._vision_pipeline = vision_pipeline

    def set_vision_pipeline(self, pipeline) -> None:
        self._vision_pipeline = pipeline

    def to_dict(self, metrics: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "id": self.instance_id,
            "algorithm_id": self.algorithm_id,
            "target": self.target,
            "state": self.state,
            "metrics": metrics or {},
        }
