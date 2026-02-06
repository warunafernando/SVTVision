"""Vision pipeline orchestrator: modular stages (preprocess → detect → overlay).

Pipeline is built from a list of stages so you can add, remove, or reorder stages
without changing this file. Default build uses PreprocessPort + TagDetectorPort.
See PIPELINE_MODULARITY.md for how to swap or add stages.
"""

import cv2
import numpy as np
from typing import Optional, Dict, Any, List, Tuple
from collections import deque
import threading
import time
from ..ports.preprocess_port import PreprocessPort
from ..ports.tag_detector_port import TagDetectorPort, TagDetection
from ..ports.pipeline_stage_port import PipelineStagePort
from ..services.logging_service import LoggingService
from ..adapters.gpu_frame_encoder import encode_frame_to_jpeg


class StageFrame:
    """Frame data for a specific pipeline stage."""

    def __init__(self, stage: str, frame: np.ndarray, jpeg_bytes: Optional[bytes] = None):
        self.stage = stage
        self.frame = frame
        self.jpeg_bytes = jpeg_bytes
        self.timestamp = None

    def get_jpeg_bytes(self) -> bytes:
        if self.jpeg_bytes is None:
            self.jpeg_bytes = encode_frame_to_jpeg(self.frame, quality=85)
        return self.jpeg_bytes


# --- Stage adapters: wrap PreprocessPort / TagDetectorPort for modular pipeline ---


class _PreprocessStage(PipelineStagePort):
    """Stage: raw grayscale → preprocessed (blur, threshold)."""

    def __init__(self, preprocessor: PreprocessPort):
        self._preprocessor = preprocessor

    @property
    def name(self) -> str:
        return "preprocess"

    def process(self, frame: np.ndarray, context: Dict[str, Any]) -> Tuple[Optional[np.ndarray], Dict[str, Any]]:
        out = self._preprocessor.preprocess(frame)
        return (out, context) if out is not None else (None, context)


class _DetectStage(PipelineStagePort):
    """Stage: preprocessed frame → run detector, fill context['detections']."""

    def __init__(self, tag_detector: TagDetectorPort):
        self._tag_detector = tag_detector

    @property
    def name(self) -> str:
        return "detect"

    def process(self, frame: np.ndarray, context: Dict[str, Any]) -> Tuple[np.ndarray, Dict[str, Any]]:
        detections = self._tag_detector.detect(frame)
        context["detections"] = detections
        return frame, context


class _OverlayStage(PipelineStagePort):
    """Stage: draw detections on raw frame → overlay frame."""

    def __init__(self, tag_detector: TagDetectorPort):
        self._tag_detector = tag_detector

    @property
    def name(self) -> str:
        return "detect_overlay"

    def process(self, frame: np.ndarray, context: Dict[str, Any]) -> Tuple[np.ndarray, Dict[str, Any]]:
        raw_frame = context.get("raw_frame", frame)
        detections = context.get("detections", [])
        overlay = self._tag_detector.draw_overlay(raw_frame, detections)
        return overlay, context


def _default_stages(preprocessor: PreprocessPort, tag_detector: TagDetectorPort) -> List[PipelineStagePort]:
    """Build default stage list: preprocess → detect → overlay. Change order or add stages here."""
    return [
        _PreprocessStage(preprocessor),
        _DetectStage(tag_detector),
        _OverlayStage(tag_detector),
    ]


class VisionPipeline:
    """Orchestrates the vision pipeline via a list of stages. Stages are run in order."""

    def __init__(
        self,
        preprocessor: PreprocessPort,
        tag_detector: TagDetectorPort,
        logger: LoggingService,
        stages: Optional[List[PipelineStagePort]] = None,
        stream_taps: Optional[Dict[str, List[Any]]] = None,
    ):
        self.logger = logger
        self._stages: List[PipelineStagePort] = (
            stages if stages is not None else _default_stages(preprocessor, tag_detector)
        )
        self._stage_frames: Dict[str, deque] = {}
        for s in self._stages:
            self._stage_frames[s.name] = deque(maxlen=3)
        self.raw_frames: deque = deque(maxlen=3)
        self.latest_detections: List[TagDetection] = []
        self.detection_stats: Dict[int, Dict[str, Any]] = {}
        self.detection_stats_lock = threading.Lock()
        self.frames_processed = 0
        self.detections_count = 0
        self.frames_with_detections = 0
        self.total_detections_all_tags = 0
        self._stream_taps: Dict[str, List[Any]] = stream_taps or {}
        self.logger.info("[Pipeline] VisionPipeline initialized")

    @classmethod
    def from_stages(
        cls,
        stages: List[PipelineStagePort],
        logger: LoggingService,
        stream_taps: Optional[Dict[str, List[Any]]] = None,
    ) -> "VisionPipeline":
        """Create pipeline from stage list (for graph-based execution, Stage 6)."""
        pipeline = cls(None, None, logger, stages=stages)
        if stream_taps:
            pipeline._stream_taps = stream_taps
        return pipeline

    def process_frame(self, raw_frame: np.ndarray) -> Dict[str, Any]:
        """Run pipeline: raw → stage1 → stage2 → … Store each stage output; return frames + detections."""
        try:
            raw_stage = StageFrame("raw", raw_frame)
            self.raw_frames.append(raw_stage)

            # Stage 7: Push raw frame to taps attached to source (CameraSource → StreamTap only)
            for tap in self._stream_taps.get("__source__", []):
                try:
                    tap.push_frame(raw_frame)
                except Exception as e:
                    self.logger.warning(f"[Pipeline] StreamTap __source__ dispatch error: {e}")

            if len(raw_frame.shape) == 3:
                gray = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = raw_frame.copy()

            context: Dict[str, Any] = {"raw_frame": raw_frame, "detections": []}
            frame = gray
            preprocess_stage = None
            detect_overlay_stage = None

            for stage in self._stages:
                if stage.name == "detect_overlay":
                    frame, context = stage.process(context["raw_frame"], context)
                else:
                    frame, context = stage.process(frame, context)
                if frame is None:
                    if stage.name == "preprocess":
                        self.logger.warning("[Pipeline] Preprocessing failed, skipping detect stage")
                        return {
                            "raw": raw_stage,
                            "preprocess": None,
                            "detect_overlay": None,
                            "detections": [],
                        }
                    continue
                sf = StageFrame(stage.name, frame)
                self._stage_frames[stage.name].append(sf)
                if stage.name == "preprocess":
                    preprocess_stage = sf
                elif stage.name == "detect_overlay":
                    detect_overlay_stage = sf

                # Stage 7: Dispatch to attached StreamTaps
                for tap in self._stream_taps.get(stage.name, []):
                    try:
                        tap.push_frame(frame)
                    except Exception as e:
                        self.logger.warning(f"[Pipeline] StreamTap dispatch error: {e}")

            detections = context.get("detections", [])
            self.latest_detections = detections
            n = len(detections)
            self.detections_count += n
            self.total_detections_all_tags += n

            current_time = time.time()
            if n > 0:
                self.frames_with_detections += 1
                with self.detection_stats_lock:
                    for d in detections:
                        tid = d.tag_id
                        if tid not in self.detection_stats:
                            self.detection_stats[tid] = {"count": 0, "first_seen": current_time, "last_seen": current_time}
                        self.detection_stats[tid]["count"] += 1
                        self.detection_stats[tid]["last_seen"] = current_time

            if self.frames_processed and self.frames_processed % 100 == 0:
                with self.detection_stats_lock:
                    summary = {tid: s["count"] for tid, s in self.detection_stats.items()}
                rate = (self.frames_with_detections / self.frames_processed) * 100
                self.logger.info(
                    f"[Pipeline] Detection stats: {self.frames_processed} frames, "
                    f"{rate:.1f}% with detections, tags={summary}, latest={[d.tag_id for d in detections]}"
                )

            self.frames_processed += 1
            out: Dict[str, Any] = {"raw": raw_stage, "detections": detections}
            for s in self._stages:
                out[s.name] = self._stage_frames[s.name][-1] if self._stage_frames[s.name] else None
            return out
        except Exception as e:
            self.logger.error(f"[Pipeline] Error processing frame: {e}")
            out = {"raw": None, "detections": []}
            for s in self._stages:
                out[s.name] = None
            return out

    def update_preprocess_config(self, config: Dict[str, Any]) -> bool:
        """Update config of the first preprocess stage (for live apply). Returns True if updated."""
        for stage in self._stages:
            if stage.name == "preprocess" and hasattr(stage, "_preprocessor"):
                ok = stage._preprocessor.set_config(config)
                if ok:
                    self.logger.info(f"[Pipeline] Live preprocess config applied: blur={config.get('blur_kernel_size')} adaptive_thr={config.get('adaptive_thresholding')} contrast_norm={config.get('contrast_normalization')}")
                return ok
        return False

    def get_latest_frame(self, stage: str) -> Optional[StageFrame]:
        if stage == "raw":
            return self.raw_frames[-1] if self.raw_frames else None
        q = self._stage_frames.get(stage)
        return q[-1] if q else None

    def get_latest_detections(self) -> List[TagDetection]:
        return self.latest_detections.copy()

    def get_metrics(self) -> Dict[str, Any]:
        rate = 0.0
        if self.frames_processed > 0:
            rate = (self.frames_with_detections / self.frames_processed) * 100
        with self.detection_stats_lock:
            tag_stats = {
                tid: {"count": s["count"], "detection_rate": (s["count"] / self.frames_processed * 100) if self.frames_processed else 0.0}
                for tid, s in self.detection_stats.items()
            }
        return {
            "frames_processed": self.frames_processed,
            "detections_count": self.detections_count,
            "latest_detections_count": len(self.latest_detections),
            "frames_with_detections": self.frames_with_detections,
            "detection_rate_percent": round(rate, 1),
            "tag_statistics": tag_stats,
        }
