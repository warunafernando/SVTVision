"""CUDA AprilTag detector adapter.

This wraps the optional pybind11 module built from `backend/cuda_apriltag/`
and exposes a TagDetectorPort-compatible API.

If the native module is missing, importing this file will still succeed, but
constructing the adapter will raise RuntimeError so callers can safely fall
back to CPU.
"""

from __future__ import annotations

import time
from typing import List, Dict, Any, Optional

import cv2
import numpy as np

from ..ports.tag_detector_port import TagDetectorPort, TagDetection
from ..services.logging_service import LoggingService

try:
    # Built by backend/cuda_apriltag/build_cuda_apriltag.sh and copied into this package.
    from . import _cuda_apriltag  # type: ignore

    _CUDA_APRILTAG_AVAILABLE = True
except Exception:
    _cuda_apriltag = None
    _CUDA_APRILTAG_AVAILABLE = False


class CudaAprilTagDetectorAdapter(TagDetectorPort):
    """AprilTag detection using CUDA (hybrid GPU stage + CPU decode)."""

    # NOTE: CUDA detector code path currently assumes decimate=2.0 (fixed width*height/4 buffers).
    DEFAULT_QUAD_DECIMATE = 2.0
    DEFAULT_NTHREADS = 4

    def __init__(self, logger: LoggingService, family: str = "tag36h11"):
        self.logger = logger
        self.family = family

        self._quad_decimate = float(self.DEFAULT_QUAD_DECIMATE)
        self._nthreads = int(self.DEFAULT_NTHREADS)

        self._detector = None
        self._detector_w: int = 0
        self._detector_h: int = 0

        # False-positive guardrails:
        # decision_margin is a confidence score from libapriltag; low values are usually noise.
        # area_px2 filters tiny quads that frequently decode as garbage IDs.
        self._min_decision_margin: float = 40.0
        self._min_area_px2: float = 250.0

        # detect() breakdown timings (ms) updated each call.
        self._last_detect_parts_ms: Dict[str, float] = {}

        if not _CUDA_APRILTAG_AVAILABLE:
            raise RuntimeError("CUDA AprilTag native module not available; build backend/cuda_apriltag first")

        self.logger.info(f"[AprilTag CUDA] CudaAprilTagDetectorAdapter initialized family={family} quad_decimate={self._quad_decimate} nthreads={self._nthreads}")

    def _ensure_detector(self, width: int, height: int) -> None:
        if self._detector is not None and self._detector_w == width and self._detector_h == height:
            return
        if _cuda_apriltag is None:
            raise RuntimeError("CUDA AprilTag native module not loaded")
        self._detector = _cuda_apriltag.CudaAprilTagDetector(
            width=width,
            height=height,
            family=self.family,
            quad_decimate=float(self._quad_decimate),
            nthreads=int(self._nthreads),
        )
        self._detector_w = int(width)
        self._detector_h = int(height)
        self.logger.info(f"[AprilTag CUDA] Created detector width={width} height={height} quad_decimate={self._quad_decimate} nthreads={self._nthreads}")

    def get_config(self) -> Dict[str, Any]:
        return {"quad_decimate": self._quad_decimate, "nthreads": self._nthreads, "backend": "cuda"}

    def set_config(self, config: Dict[str, Any]) -> bool:
        try:
            changed = False
            if "quad_decimate" in config:
                v = float(config["quad_decimate"])
                # CUDA backend currently supports only 2.0; clamp to avoid native crashes.
                v = 2.0
                if v != self._quad_decimate:
                    self._quad_decimate = v
                    changed = True
            if "nthreads" in config:
                v = int(config["nthreads"])
                v = max(1, min(8, v))
                if v != self._nthreads:
                    self._nthreads = v
                    changed = True
            if changed and self._detector is not None:
                try:
                    self._detector.set_config(float(self._quad_decimate), int(self._nthreads))
                except Exception:
                    # If the native detector can't be reconfigured live, recreate on next detect.
                    self._detector = None
                    self._detector_w = 0
                    self._detector_h = 0
                self.logger.info(f"[AprilTag CUDA] Detector config updated quad_decimate={self._quad_decimate} nthreads={self._nthreads}")
            return True
        except Exception as e:
            self.logger.error(f"[AprilTag CUDA] set_config error: {e}")
            return False

    def get_last_detect_parts_ms(self) -> Dict[str, float]:
        return dict(self._last_detect_parts_ms)

    def detect(self, frame: np.ndarray) -> List[TagDetection]:
        if not _CUDA_APRILTAG_AVAILABLE:
            return []

        try:
            t0 = time.perf_counter_ns()
            if frame.ndim == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame.copy()
            t1 = time.perf_counter_ns()

            if gray.dtype != np.uint8:
                # Match CPU adapter behavior (assume [0,1] float)
                gray = (gray * 255).astype(np.uint8)
            t2 = time.perf_counter_ns()

            h, w = int(gray.shape[0]), int(gray.shape[1])
            self._ensure_detector(width=w, height=h)

            # Native detect: returns {"detections": [...], "timings_ms": {...}}
            res = self._detector.detect(gray)  # type: ignore[union-attr]
            t3 = time.perf_counter_ns()

            # Convert results into TagDetection objects
            detections: List[TagDetection] = []
            for d in (res.get("detections") or []):
                try:
                    dm = float(d.get("decision_margin", 0.0) or 0.0)
                    if dm < self._min_decision_margin:
                        continue
                    tag_id = int(d.get("id"))
                    corners_list = d.get("corners") or []
                    if len(corners_list) != 4:
                        continue
                    corners = np.array([[float(x), float(y)] for (x, y) in corners_list], dtype=np.float32)
                    # Area filter (shoelace). Reject tiny/degenerate shapes.
                    x = corners[:, 0]
                    y = corners[:, 1]
                    area = 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))
                    if area < self._min_area_px2:
                        continue
                    center_t = d.get("center") or (0.0, 0.0)
                    center = (float(center_t[0]), float(center_t[1]))
                    detections.append(TagDetection(tag_id=tag_id, corners=corners, center=center, family=self.family))
                except Exception:
                    continue
            t4 = time.perf_counter_ns()

            native_timings = {}
            try:
                native_timings = dict(res.get("timings_ms") or {})
            except Exception:
                native_timings = {}

            # Store breakdown (ms)
            self._last_detect_parts_ms = {
                "ensure_grayscale": (t1 - t0) / 1_000_000.0,
                "to_uint8": (t2 - t1) / 1_000_000.0,
                # Keep name stable even when CUDA is used: this is the detector call wall time.
                "apriltag_detect_call": (t3 - t2) / 1_000_000.0,
                "convert_results": (t4 - t3) / 1_000_000.0,
            }
            # Add CUDA-specific parts if provided by native module
            for k in ("gpu_stage_ms", "cpu_decode_ms", "detector_total_ms", "num_quads"):
                if k in native_timings:
                    try:
                        self._last_detect_parts_ms[k] = float(native_timings[k])
                    except Exception:
                        pass

            return detections
        except Exception as e:
            self.logger.error(f"[AprilTag CUDA] Error detecting AprilTags: {e}")
            self._last_detect_parts_ms = {}
            return []

    def draw_overlay(self, frame: np.ndarray, detections: List[TagDetection]) -> np.ndarray:
        """Reuse the same overlay drawing style as the CPU adapter."""
        try:
            if frame.ndim == 2:
                overlay = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            else:
                overlay = frame.copy()

            for det in detections:
                corners_int = det.corners.astype(np.int32)
                cv2.polylines(overlay, [corners_int], True, (0, 255, 0), 2)
                for corner in corners_int:
                    cv2.circle(overlay, tuple(corner), 5, (0, 0, 255), -1)
                center_int = (int(det.center[0]), int(det.center[1]))
                cv2.putText(
                    overlay,
                    f"Tag {det.tag_id}",
                    (center_int[0] - 30, center_int[1]),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 255),
                    2,
                )

            return overlay
        except Exception as e:
            self.logger.error(f"[AprilTag CUDA] Error drawing overlay: {e}")
            return frame

