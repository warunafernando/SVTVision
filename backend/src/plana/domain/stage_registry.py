"""
Stage Registry - Registers all vision pipeline stages with discovery API.
Stages can be loaded from config (pipeline_stages.json) or use code defaults.
Stage 9: Plugin-based stage addition via custom_pipeline_stages.json and add_stage/remove_stage.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional, Set
import json


def _default_stages() -> List[Dict[str, Any]]:
    """Built-in stage definitions (code defaults)."""
    return [
        {
            "id": "preprocess_cpu",
            "name": "preprocess_cpu",
            "label": "Preprocess (CPU)",
            "execution_type": "cpu",
            "type": "stage",
            "ports": {
                "inputs": [{"name": "frame", "type": "frame"}],
                "outputs": [{"name": "frame", "type": "frame"}],
            },
            "settings_schema": [
                {"key": "blur_kernel_size", "type": "number", "default": 3, "min": 1, "max": 21, "label": "Blur kernel size"},
                {"key": "threshold_type", "type": "select", "default": "adaptive", "options": [{"value": "adaptive", "label": "Adaptive"}, {"value": "binary", "label": "Binary"}], "label": "Threshold type"},
                {"key": "adaptive_block_size", "type": "number", "default": 15, "min": 3, "max": 51, "label": "Adaptive block size"},
                {"key": "adaptive_c", "type": "number", "default": 3, "min": 0, "max": 20, "label": "Adaptive C"},
                {"key": "binary_threshold", "type": "number", "default": 127, "min": 0, "max": 255, "label": "Binary threshold"},
                {"key": "morphology", "type": "boolean", "default": False, "label": "Morphology"},
                {"key": "morph_kernel_size", "type": "number", "default": 3, "min": 1, "max": 15, "label": "Morph kernel size"},
            ],
        },
        {
            "id": "preprocess_gpu",
            "name": "preprocess_gpu",
            "label": "Preprocess (GPU)",
            "execution_type": "gpu",
            "type": "stage",
            "ports": {
                "inputs": [{"name": "frame", "type": "frame"}],
                "outputs": [{"name": "frame", "type": "frame"}],
            },
            "settings_schema": [
                {"key": "blur_kernel_size", "type": "number", "default": 3, "min": 1, "max": 21, "label": "Blur kernel size"},
                {"key": "threshold_type", "type": "select", "default": "adaptive", "options": [{"value": "adaptive", "label": "Adaptive"}, {"value": "binary", "label": "Binary"}], "label": "Threshold type"},
                {"key": "adaptive_block_size", "type": "number", "default": 15, "min": 3, "max": 51, "label": "Adaptive block size"},
                {"key": "adaptive_c", "type": "number", "default": 3, "min": 0, "max": 20, "label": "Adaptive C"},
                {"key": "binary_threshold", "type": "number", "default": 127, "min": 0, "max": 255, "label": "Binary threshold"},
                {"key": "morphology", "type": "boolean", "default": False, "label": "Morphology"},
                {"key": "morph_kernel_size", "type": "number", "default": 3, "min": 1, "max": 15, "label": "Morph kernel size"},
            ],
        },
        {
            "id": "detect_apriltag_cpu",
            "name": "detect_apriltag_cpu",
            "label": "AprilTag Detect (CPU)",
            "execution_type": "cpu",
            "type": "stage",
            "ports": {
                "inputs": [{"name": "frame", "type": "frame"}],
                "outputs": [{"name": "frame", "type": "frame"}, {"name": "detections", "type": "detections"}],
            },
            "settings_schema": [
                {"key": "tag_family", "type": "select", "default": "tag36h11", "options": [{"value": "tag36h11", "label": "tag36h11"}, {"value": "tag25h9", "label": "tag25h9"}, {"value": "tag16h5", "label": "tag16h5"}], "label": "Tag family"},
            ],
        },
        {
            "id": "overlay_cpu",
            "name": "overlay_cpu",
            "label": "Overlay (CPU)",
            "execution_type": "cpu",
            "type": "stage",
            "ports": {
                "inputs": [{"name": "frame", "type": "frame"}, {"name": "detections", "type": "detections"}],
                "outputs": [{"name": "frame", "type": "frame"}],
            },
            "settings_schema": [],
        },
    ]


def _default_sources() -> List[Dict[str, Any]]:
    """Built-in source definitions. CameraSource: config.camera_id = which already-open camera to pull frames from (Phase 3)."""
    return [
        {"id": "camera", "name": "CameraSource", "type": "source", "source_type": "camera", "ports": {"inputs": [], "outputs": [{"name": "frame", "type": "frame"}]}},
        {"id": "video_file", "name": "VideoFileSource", "type": "source", "source_type": "video_file", "ports": {"inputs": [], "outputs": [{"name": "frame", "type": "frame"}]}},
        {"id": "image_file", "name": "ImageFileSource", "type": "source", "source_type": "image_file", "ports": {"inputs": [], "outputs": [{"name": "frame", "type": "frame"}]}},
    ]


def _default_sinks() -> List[Dict[str, Any]]:
    """Built-in sink definitions."""
    return [
        {"id": "stream_tap", "name": "StreamTap", "type": "sink", "sink_type": "stream_tap", "ports": {"inputs": [{"name": "frame", "type": "frame"}], "outputs": [{"name": "frame", "type": "frame"}]}},
        {"id": "save_video", "name": "SaveVideo", "type": "sink", "sink_type": "save_video", "ports": {"inputs": [{"name": "frame", "type": "frame"}], "outputs": [{"name": "frame", "type": "frame"}]}},
        {"id": "save_image", "name": "SaveImage", "type": "sink", "sink_type": "save_image", "ports": {"inputs": [{"name": "frame", "type": "frame"}], "outputs": [{"name": "frame", "type": "frame"}]}},
        {"id": "svt_output", "name": "SVTVisionOutput", "type": "sink", "sink_type": "svt_output", "ports": {"inputs": [{"name": "frame", "type": "frame"}], "outputs": []}},
    ]


class StageRegistry:
    """
    Registry of vision pipeline stages, sources, and sinks.
    Loads from config/pipeline_stages.json if present; otherwise uses code defaults.
    """

    def __init__(self, config_dir: Path, logger: Optional[Any] = None):
        self.config_dir = Path(config_dir)
        self.config_file = self.config_dir / "pipeline_stages.json"
        self.custom_stages_file = self.config_dir / "custom_pipeline_stages.json"
        self.logger = logger
        self._stages: Dict[str, Dict[str, Any]] = {}
        self._sources: Dict[str, Dict[str, Any]] = {}
        self._sinks: Dict[str, Dict[str, Any]] = {}
        self._custom_stage_ids: Set[str] = set()
        self._load()

    def _load(self) -> None:
        """Load stages from config or use defaults."""
        defaults_stages = {s["id"]: s for s in _default_stages()}
        defaults_sources = {s["id"]: s for s in _default_sources()}
        defaults_sinks = {s["id"]: s for s in _default_sinks()}

        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                stages_cfg = data.get("stages", [])
                sources_cfg = data.get("sources", [])
                sinks_cfg = data.get("sinks", [])

                # Merge config over defaults
                for s in stages_cfg:
                    sid = s.get("id")
                    if sid:
                        base = defaults_stages.get(sid, {})
                        defaults_stages[sid] = {**base, **s}
                for s in sources_cfg:
                    sid = s.get("id")
                    if sid:
                        base = defaults_sources.get(sid, {})
                        defaults_sources[sid] = {**base, **s}
                for s in sinks_cfg:
                    sid = s.get("id")
                    if sid:
                        base = defaults_sinks.get(sid, {})
                        defaults_sinks[sid] = {**base, **s}

                if self.logger:
                    self.logger.info(f"[StageRegistry] Loaded from {self.config_file}")
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"[StageRegistry] Failed to load {self.config_file}: {e}, using defaults")
        else:
            if self.logger:
                self.logger.info("[StageRegistry] Using built-in stage definitions")

        self._stages = defaults_stages
        self._sources = defaults_sources
        self._sinks = defaults_sinks

        # Stage 9: Load custom stages (plugin-based addition)
        self._load_custom_stages()

    def _load_custom_stages(self) -> None:
        """Load custom stages from custom_pipeline_stages.json."""
        if not self.custom_stages_file.exists():
            return
        try:
            with open(self.custom_stages_file, "r") as f:
                data = json.load(f)
            custom_list = data.get("stages", []) if isinstance(data, dict) else data
            if not isinstance(custom_list, list):
                return
            for s in custom_list:
                sid = s.get("id")
                if sid and isinstance(s, dict):
                    self._stages[sid] = {**s, "type": "stage"}
                    self._custom_stage_ids.add(sid)
            if self.logger and self._custom_stage_ids:
                self.logger.info(f"[StageRegistry] Loaded {len(self._custom_stage_ids)} custom stages")
        except Exception as e:
            if self.logger:
                self.logger.warning(f"[StageRegistry] Failed to load custom stages: {e}")

    def _save_custom_stages(self) -> None:
        """Persist custom stages to custom_pipeline_stages.json."""
        custom_list = [self._stages[sid] for sid in sorted(self._custom_stage_ids) if sid in self._stages]
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.custom_stages_file, "w") as f:
            json.dump({"stages": custom_list}, f, indent=2)
        if self.logger:
            self.logger.info(f"[StageRegistry] Saved {len(custom_list)} custom stages")

    def add_stage(self, stage_def: Dict[str, Any]) -> bool:
        """
        Register a custom stage (Stage 9). Persists to custom_pipeline_stages.json.
        stage_def must have: id, name or label, type "stage", ports (inputs, outputs).
        Returns True if added, False if invalid or id conflicts with built-in.
        """
        sid = stage_def.get("id")
        if not sid or not isinstance(sid, str) or not sid.strip():
            if self.logger:
                self.logger.warning("[StageRegistry] add_stage: missing or invalid id")
            return False
        sid = str(sid).strip()
        if sid in {s["id"] for s in _default_stages()}:
            if self.logger:
                self.logger.warning(f"[StageRegistry] add_stage: cannot override built-in stage {sid}")
            return False
        ports = stage_def.get("ports")
        if not isinstance(ports, dict) or "inputs" not in ports or "outputs" not in ports:
            if self.logger:
                self.logger.warning("[StageRegistry] add_stage: missing or invalid ports")
            return False
        full_def = {
            "id": sid,
            "name": stage_def.get("name", stage_def.get("label", sid)),
            "label": stage_def.get("label", stage_def.get("name", sid)),
            "execution_type": stage_def.get("execution_type", "cpu"),
            "type": "stage",
            "ports": ports,
            "settings_schema": stage_def.get("settings_schema", []),
        }
        self._stages[sid] = full_def
        self._custom_stage_ids.add(sid)
        self._save_custom_stages()
        if self.logger:
            self.logger.info(f"[StageRegistry] Added custom stage {sid}")
        return True

    def remove_stage(self, stage_id: str) -> bool:
        """
        Remove a custom stage (Stage 9). Only custom stages can be removed.
        Returns True if removed, False if not found or built-in.
        """
        if stage_id not in self._custom_stage_ids:
            if self.logger:
                self.logger.warning(f"[StageRegistry] remove_stage: {stage_id} is not a custom stage")
            return False
        self._stages.pop(stage_id, None)
        self._custom_stage_ids.discard(stage_id)
        self._save_custom_stages()
        if self.logger:
            self.logger.info(f"[StageRegistry] Removed custom stage {stage_id}")
        return True

    def is_custom_stage(self, stage_id: str) -> bool:
        """Return True if stage_id is a custom (plugin-added) stage."""
        return stage_id in self._custom_stage_ids

    def list_stages(self) -> List[Dict[str, Any]]:
        """Return all registered stages for the palette. Stage 9: includes 'custom': True for plugin-added stages."""
        return [
            {**s, "custom": sid in self._custom_stage_ids}
            for sid, s in self._stages.items()
        ]

    def list_sources(self) -> List[Dict[str, Any]]:
        """Return all registered sources for the palette."""
        return list(self._sources.values())

    def list_sinks(self) -> List[Dict[str, Any]]:
        """Return all registered sinks for the palette."""
        return list(self._sinks.values())

    def list_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """Return stages, sources, and sinks for discovery."""
        return {
            "stages": self.list_stages(),
            "sources": self.list_sources(),
            "sinks": self.list_sinks(),
        }

    def get_stage(self, stage_id: str) -> Optional[Dict[str, Any]]:
        """Get a stage by id."""
        return self._stages.get(stage_id)

    def get_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        """Get a source by id."""
        return self._sources.get(source_id)

    def get_sink(self, sink_id: str) -> Optional[Dict[str, Any]]:
        """Get a sink by id."""
        return self._sinks.get(sink_id)
