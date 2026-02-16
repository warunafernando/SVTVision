"""AprilTag-only timed pipeline stages.

These wrappers implement PipelineStagePort and measure per-frame timings with
minimal overhead. They are intended to be used ONLY for the AprilTag pipeline
(use_case == "apriltag") so we can report per-stage timings without modifying
the core VisionPipeline implementation.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple

import numpy as np

from ..ports.pipeline_stage_port import PipelineStagePort
from ..ports.preprocess_port import PreprocessPort
from ..ports.tag_detector_port import TagDetectorPort


def _elapsed_ms(start_ns: int, end_ns: int) -> float:
    return (end_ns - start_ns) / 1_000_000.0


class _TimedStageBase(PipelineStagePort):
    """Common helpers for timed stages."""

    def __init__(self) -> None:
        self._last_ms: float = 0.0

    def get_last_ms(self) -> float:
        """Return last measured stage duration (ms)."""
        return self._last_ms


class ApriltagTimedPreprocessStage(_TimedStageBase):
    """Stage: raw/grayscale -> preprocessed image (threshold, blur, etc.)."""

    def __init__(self, preprocessor: PreprocessPort):
        super().__init__()
        # Keep the same attribute name VisionPipeline uses for live updates.
        self._preprocessor = preprocessor

    @property
    def name(self) -> str:
        return "preprocess"

    def process(self, frame: np.ndarray, context: Dict[str, Any]) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
        t0 = time.perf_counter_ns()
        out = self._preprocessor.preprocess(frame)
        t1 = time.perf_counter_ns()
        self._last_ms = _elapsed_ms(t0, t1)
        return (out, context) if out is not None else (None, context)


class ApriltagTimedDetectStage(_TimedStageBase):
    """Stage: preprocessed image -> detections (stored in context['detections'])."""

    def __init__(self, tag_detector: TagDetectorPort):
        super().__init__()
        # Keep the same attribute name VisionPipeline uses for live updates.
        self._tag_detector = tag_detector

    @property
    def name(self) -> str:
        return "detect"

    def process(self, frame: np.ndarray, context: Dict[str, Any]) -> Tuple[np.ndarray, Dict[str, Any]]:
        t0 = time.perf_counter_ns()
        detections = self._tag_detector.detect(frame)
        t1 = time.perf_counter_ns()
        self._last_ms = _elapsed_ms(t0, t1)
        context["detections"] = detections
        return frame, context


class ApriltagTimedOverlayStage(_TimedStageBase):
    """Stage: raw frame + detections -> overlay frame."""

    def __init__(self, tag_detector: TagDetectorPort):
        super().__init__()
        self._tag_detector = tag_detector

    @property
    def name(self) -> str:
        return "detect_overlay"

    def process(self, frame: np.ndarray, context: Dict[str, Any]) -> Tuple[np.ndarray, Dict[str, Any]]:
        raw_frame = context.get("raw_frame", frame)
        detections = context.get("detections", [])
        t0 = time.perf_counter_ns()
        overlay = self._tag_detector.draw_overlay(raw_frame, detections)
        t1 = time.perf_counter_ns()
        self._last_ms = _elapsed_ms(t0, t1)
        return overlay, context

