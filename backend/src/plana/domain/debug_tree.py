"""Debug tree domain model."""

from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class NodeStatus(Enum):
    """Debug tree node status."""
    OK = "OK"
    WARN = "WARN"
    STALE = "STALE"
    ERROR = "ERROR"


class DebugTreeNode:
    """Represents a node in the debug tree."""
    
    def __init__(
        self,
        id: str,
        name: str,
        status: NodeStatus,
        reason: str,
        metrics: Optional[Dict[str, Any]] = None,
        children: Optional[List['DebugTreeNode']] = None
    ):
        self.id = id
        self.name = name
        self.status = status
        self.reason = reason
        self.metrics = metrics or {}
        self.children = children or []
        self.last_update = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert node to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "reason": self.reason,
            "metrics": self.metrics,
            "children": [child.to_dict() for child in self.children]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DebugTreeNode':
        """Create node from dictionary."""
        children = [
            cls.from_dict(child) for child in data.get("children", [])
        ]
        return cls(
            id=data["id"],
            name=data["name"],
            status=NodeStatus(data["status"]),
            reason=data["reason"],
            metrics=data.get("metrics", {}),
            children=children
        )
