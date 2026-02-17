"""AprilTag detector adapter implementation."""

import cv2
import numpy as np
from typing import List, Dict, Any
import apriltag
import time
from ..ports.tag_detector_port import TagDetectorPort, TagDetection
from ..services.logging_service import LoggingService


class AprilTagDetectorAdapter(TagDetectorPort):
    """Adapter for AprilTag detection using apriltag library."""

    DEFAULT_QUAD_DECIMATE = 1.0  
    DEFAULT_NTHREADS = 4  # Use multiple CPU cores

    def __init__(self, logger: LoggingService, family: str = "tag36h11"):
        self.logger = logger
        self.family = family
        self._quad_decimate = self.DEFAULT_QUAD_DECIMATE
        self._nthreads = self.DEFAULT_NTHREADS
        try:
            self._create_detector()
            self.logger.info(f"[AprilTag] AprilTagDetectorAdapter initialized family={family} quad_decimate={self._quad_decimate} nthreads={self._nthreads}")
        except Exception as e:
            self.logger.error(f"[AprilTag] Failed to initialize AprilTag detector: {e}")
            self.detector = None

        # Last detect() breakdown timings (ms). Updated per detect() call.
        # Keys: ensure_grayscale, to_uint8, apriltag_detect_call, convert_results
        self._last_detect_parts_ms: Dict[str, float] = {}

        # False-positive guardrails (CPU path). Matches CUDA adapter intent.
        self._min_decision_margin: float = 40.0
        self._min_area_px2: float = 250.0

    def get_last_detect_parts_ms(self) -> Dict[str, float]:
        """Return the last detect() breakdown timings (ms)."""
        return dict(self._last_detect_parts_ms)

    def _create_detector(self) -> None:
        """Create or recreate detector with current _quad_decimate and _nthreads."""
        options = apriltag.DetectorOptions(
            families=self.family,
            border=1,
            nthreads=self._nthreads,
            quad_decimate=self._quad_decimate,
            quad_blur=0.0,
            refine_edges=True,
            refine_decode=False,
            refine_pose=False,
            debug=False,
            quad_contours=True,
        )
        self.detector = apriltag.Detector(options)

    def get_config(self) -> Dict[str, Any]:
        """Return current detector settings (quad_decimate, nthreads)."""
        return {"quad_decimate": self._quad_decimate, "nthreads": self._nthreads}

    def set_config(self, config: Dict[str, Any]) -> bool:
        """Update quad_decimate and/or nthreads; recreate detector. Returns True if updated."""
        try:
            changed = False
            if "quad_decimate" in config:
                v = float(config["quad_decimate"])
                v = max(0.5, min(4.0, v))
                if v != self._quad_decimate:
                    self._quad_decimate = v
                    changed = True
            if "nthreads" in config:
                v = int(config["nthreads"])
                v = max(1, min(8, v))
                if v != self._nthreads:
                    self._nthreads = v
                    changed = True
            if changed and self.detector is not None:
                self._create_detector()
                self.logger.info(f"[AprilTag] Detector config updated quad_decimate={self._quad_decimate} nthreads={self._nthreads}")
            return True
        except Exception as e:
            self.logger.error(f"[AprilTag] set_config error: {e}")
            return False

    def detect(self, frame: np.ndarray) -> List[TagDetection]:
        """Detect AprilTags in a frame.
        
        Args:
            frame: Preprocessed frame as numpy array (grayscale expected)
        
        Returns:
            List of TagDetection objects
        """
        if self.detector is None:
            return []
        
        try:
            # Breakdown timing (minimal overhead, coarse steps)
            t0 = time.perf_counter_ns()
            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame.copy()
            t1 = time.perf_counter_ns()

            if gray.dtype != np.uint8:
                gray = (gray * 255).astype(np.uint8)
            t2 = time.perf_counter_ns()

            detections_raw = self.detector.detect(gray)
            t3 = time.perf_counter_ns()

            # Convert to TagDetection objects
            detections = []
            for det in detections_raw:
                if det.tag_id is not None:
                    try:
                        dm = float(getattr(det, "decision_margin", 0.0) or 0.0)
                        if dm < self._min_decision_margin:
                            continue
                    except Exception:
                        pass
                    # Extract corners (4 points)
                    corners = np.array([
                        [det.corners[0][0], det.corners[0][1]],
                        [det.corners[1][0], det.corners[1][1]],
                        [det.corners[2][0], det.corners[2][1]],
                        [det.corners[3][0], det.corners[3][1]]
                    ])
                    try:
                        x = corners[:, 0]
                        y = corners[:, 1]
                        area = 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))
                        if area < self._min_area_px2:
                            continue
                    except Exception:
                        pass
                    
                    # Calculate center
                    center_x = float(np.mean(corners[:, 0]))
                    center_y = float(np.mean(corners[:, 1]))
                    
                    detection = TagDetection(
                        tag_id=int(det.tag_id),
                        corners=corners,
                        center=(center_x, center_y),
                        family=self.family
                    )
                    detections.append(detection)
            t4 = time.perf_counter_ns()

            # Store breakdown timings (ms) for the last detect() call
            self._last_detect_parts_ms = {
                "ensure_grayscale": (t1 - t0) / 1_000_000.0,
                "to_uint8": (t2 - t1) / 1_000_000.0,
                "apriltag_detect_call": (t3 - t2) / 1_000_000.0,
                "convert_results": (t4 - t3) / 1_000_000.0,
            }

            return detections
        
        except Exception as e:
            self.logger.error(f"[AprilTag] Error detecting AprilTags: {e}")
            self._last_detect_parts_ms = {}
            return []
    
    def draw_overlay(self, frame: np.ndarray, detections: List[TagDetection]) -> np.ndarray:
        """Draw detection overlay on frame.
        
        Draws:
        - Tag outline (polygon connecting corners)
        - Tag ID text at center
        - Corner markers
        """
        try:
            # Convert to color if grayscale
            if len(frame.shape) == 2:
                overlay = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            else:
                overlay = frame.copy()
            
            # Draw each detection
            for det in detections:
                # Draw tag outline (polygon)
                corners_int = det.corners.astype(np.int32)
                cv2.polylines(overlay, [corners_int], True, (0, 255, 0), 2)
                
                # Draw corner markers
                for corner in corners_int:
                    cv2.circle(overlay, tuple(corner), 5, (0, 0, 255), -1)
                
                # Draw tag ID text at center
                center_int = (int(det.center[0]), int(det.center[1]))
                text = f"Tag {det.tag_id}"
                cv2.putText(
                    overlay,
                    text,
                    (center_int[0] - 30, center_int[1]),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 255),
                    2
                )
            
            return overlay
        
        except Exception as e:
            self.logger.error(f"[AprilTag] Error drawing overlay: {e}")
            return frame
