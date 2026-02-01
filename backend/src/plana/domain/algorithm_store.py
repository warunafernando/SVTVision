"""
Algorithm Store - Persists PipelineGraphs to JSON files.
Saves to config/algorithms/*.json for load-back on restart.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from ..services.logging_service import LoggingService


def _slugify(name: str) -> str:
    """Create a filesystem-safe id from a name."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name.lower()).strip("_") or "untitled"


class AlgorithmStore:
    """Persists pipeline graphs (algorithms) as JSON files."""

    def __init__(self, config_dir: Path, logger: Optional[LoggingService] = None):
        self.config_dir = Path(config_dir)
        self.algorithms_dir = self.config_dir / "algorithms"
        self.algorithms_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or LoggingService()

    def _path_for_id(self, algo_id: str) -> Path:
        return self.algorithms_dir / f"{algo_id}.json"

    def list_all(self) -> List[Dict[str, Any]]:
        """List all saved algorithms (id, name, updated_at)."""
        result: List[Dict[str, Any]] = []
        if not self.algorithms_dir.exists():
            return result
        for p in sorted(self.algorithms_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                algo_id = p.stem
                result.append({
                    "id": algo_id,
                    "name": data.get("name", algo_id),
                    "updated_at": data.get("updated_at", ""),
                })
            except Exception as e:
                self.logger.warning(f"[AlgorithmStore] Failed to read {p}: {e}")
        return result

    def get(self, algo_id: str) -> Optional[Dict[str, Any]]:
        """Load algorithm by id. Returns full graph dict or None."""
        path = self._path_for_id(algo_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["id"] = algo_id
            return data
        except Exception as e:
            self.logger.warning(f"[AlgorithmStore] Failed to read {path}: {e}")
            return None

    def save(self, algo_id: Optional[str], name: str, nodes: List, edges: List, layout: Optional[Dict] = None) -> str:
        """Save algorithm. Returns id (new or existing)."""
        import datetime
        now = datetime.datetime.utcnow().isoformat() + "Z"
        if not algo_id:
            base = _slugify(name)
            algo_id = base
            i = 0
            while self._path_for_id(algo_id).exists():
                i += 1
                algo_id = f"{base}_{i}"
        path = self._path_for_id(algo_id)
        doc = {
            "name": name,
            "description": "",
            "nodes": nodes,
            "edges": edges,
            "layout": layout or {},
            "updated_at": now,
        }
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        self.logger.info(f"[AlgorithmStore] Saved algorithm {algo_id}")
        return algo_id

    def delete(self, algo_id: str) -> bool:
        """Delete algorithm by id. Returns True if removed."""
        path = self._path_for_id(algo_id)
        if not path.exists():
            return False
        try:
            path.unlink()
            self.logger.info(f"[AlgorithmStore] Deleted algorithm {algo_id}")
            return True
        except Exception as e:
            self.logger.warning(f"[AlgorithmStore] Failed to delete {path}: {e}")
            return False
