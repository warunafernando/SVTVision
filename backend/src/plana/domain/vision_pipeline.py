"""Vision pipeline orchestrator for preprocessing and detection."""

import cv2
import numpy as np
from typing import Optional, Dict, Any, List
from collections import deque
import threading
import time
from ..ports.preprocess_port import PreprocessPort
from ..ports.tag_detector_port import TagDetectorPort, TagDetection
from ..services.logging_service import LoggingService


class StageFrame:
    """Frame data for a specific pipeline stage."""
    
    def __init__(self, stage: str, frame: np.ndarray, jpeg_bytes: Optional[bytes] = None):
        self.stage = stage  # "raw", "preprocess", "detect_overlay"
        self.frame = frame  # Raw numpy array
        self.jpeg_bytes = jpeg_bytes  # JPEG-encoded bytes (cached)
        self.timestamp = None  # Set when frame is created
    
    def get_jpeg_bytes(self) -> bytes:
        """Get JPEG-encoded bytes (encode if not cached)."""
        if self.jpeg_bytes is None:
            # Encode to JPEG
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, 85]
            _, jpeg_bytes = cv2.imencode('.jpg', self.frame, encode_params)
            if jpeg_bytes is not None:
                self.jpeg_bytes = jpeg_bytes.tobytes()
            else:
                # Fallback: return empty bytes
                self.jpeg_bytes = b''
        return self.jpeg_bytes


class VisionPipeline:
    """Orchestrates the vision pipeline: Raw → Preprocess → Detect."""
    
    def __init__(
        self,
        preprocessor: PreprocessPort,
        tag_detector: TagDetectorPort,
        logger: LoggingService
    ):
        self.preprocessor = preprocessor
        self.tag_detector = tag_detector
        self.logger = logger
        
        # Frame queues for each stage (bounded, drop-oldest)
        self.raw_frames: deque[StageFrame] = deque(maxlen=3)
        self.preprocess_frames: deque[StageFrame] = deque(maxlen=3)
        self.detect_overlay_frames: deque[StageFrame] = deque(maxlen=3)
        
        # Latest detections
        self.latest_detections: List[TagDetection] = []
        
        # Detection statistics - track detection consistency
        self.detection_stats: Dict[int, Dict[str, Any]] = {}  # tag_id -> {count, last_seen, first_seen}
        self.detection_stats_lock = threading.Lock()
        
        # Metrics
        self.frames_processed = 0
        self.detections_count = 0
        self.frames_with_detections = 0
        self.total_detections_all_tags = 0
        
        self.logger.info("[Pipeline] VisionPipeline initialized")
    
    def process_frame(self, raw_frame: np.ndarray) -> Dict[str, Any]:
        """Process a raw frame through the pipeline.
        
        Pipeline stages:
        1. Raw frame (input - grayscale for AprilTag cameras)
        2. Preprocess (blur, threshold, etc.)
        3. Detect (AprilTag detection)
        4. Detect Overlay (draw detections on frame)
        
        Args:
            raw_frame: Raw frame as numpy array (BGR format or grayscale converted to BGR)
        
        Returns:
            Dict with stage frames and detections
        """
        try:
            # Stage 1: Raw frame (already grayscale for AprilTag cameras)
            raw_stage = StageFrame("raw", raw_frame)
            self.raw_frames.append(raw_stage)
            
            # Convert to grayscale for preprocessing if needed
            if len(raw_frame.shape) == 3:
                gray_frame = cv2.cvtColor(raw_frame, cv2.COLOR_BGR2GRAY)
            else:
                gray_frame = raw_frame
            
            # Stage 2: Preprocess (works on grayscale)
            preprocessed = self.preprocessor.preprocess(gray_frame)
            if preprocessed is None:
                self.logger.warning("[Pipeline] Preprocessing failed, skipping detect stage")
                return {
                    "raw": raw_stage,
                    "preprocess": None,
                    "detect_overlay": None,
                    "detections": []
                }
            
            preprocess_stage = StageFrame("preprocess", preprocessed)
            self.preprocess_frames.append(preprocess_stage)
            
            # Stage 3: Detect AprilTags
            detections = self.tag_detector.detect(preprocessed)
            self.latest_detections = detections
            detection_count = len(detections)
            self.detections_count += detection_count
            self.total_detections_all_tags += detection_count
            
            # Update detection statistics for consistency tracking
            current_time = time.time()
            if detection_count > 0:
                self.frames_with_detections += 1
                with self.detection_stats_lock:
                    for det in detections:
                        tag_id = det.tag_id
                        if tag_id not in self.detection_stats:
                            self.detection_stats[tag_id] = {
                                "count": 0,
                                "first_seen": current_time,
                                "last_seen": current_time
                            }
                        self.detection_stats[tag_id]["count"] += 1
                        self.detection_stats[tag_id]["last_seen"] = current_time
            
            # Log detection statistics every 100 frames
            if self.frames_processed % 100 == 0 and self.frames_processed > 0:
                with self.detection_stats_lock:
                    stats_summary = {tag_id: stats["count"] for tag_id, stats in self.detection_stats.items()}
                    detection_rate = (self.frames_with_detections / self.frames_processed) * 100
                    self.logger.info(
                        f"[Pipeline] Detection stats: {self.frames_processed} frames processed, "
                        f"{detection_rate:.1f}% with detections, "
                        f"Tags detected: {stats_summary}, "
                        f"Latest: {[d.tag_id for d in detections]}"
                    )
            
            # Stage 4: Draw overlay on raw frame (raw_frame is already grayscale-converted BGR format)
            overlay_frame = self.tag_detector.draw_overlay(raw_frame, detections)
            detect_overlay_stage = StageFrame("detect_overlay", overlay_frame)
            self.detect_overlay_frames.append(detect_overlay_stage)
            
            self.frames_processed += 1
            
            return {
                "raw": raw_stage,
                "preprocess": preprocess_stage,
                "detect_overlay": detect_overlay_stage,
                "detections": detections
            }
        
        except Exception as e:
            self.logger.error(f"[Pipeline] Error processing frame in vision pipeline: {e}")
            return {
                "raw": None,
                "preprocess": None,
                "detect_overlay": None,
                "detections": []
            }
    
    def get_latest_frame(self, stage: str) -> Optional[StageFrame]:
        """Get latest frame for a specific stage.
        
        Args:
            stage: Stage name ("raw", "preprocess", "detect_overlay")
        
        Returns:
            Latest StageFrame for the stage, or None if not available
        """
        if stage == "raw":
            return self.raw_frames[-1] if self.raw_frames else None
        elif stage == "preprocess":
            return self.preprocess_frames[-1] if self.preprocess_frames else None
        elif stage == "detect_overlay":
            return self.detect_overlay_frames[-1] if self.detect_overlay_frames else None
        else:
            return None
    
    def get_latest_detections(self) -> List[TagDetection]:
        """Get latest detections."""
        return self.latest_detections.copy()
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get pipeline metrics."""
        detection_rate = 0.0
        if self.frames_processed > 0:
            detection_rate = (self.frames_with_detections / self.frames_processed) * 100
        
        # Get detection statistics
        with self.detection_stats_lock:
            tag_stats = {
                tag_id: {
                    "count": stats["count"],
                    "detection_rate": (stats["count"] / self.frames_processed * 100) if self.frames_processed > 0 else 0.0
                }
                for tag_id, stats in self.detection_stats.items()
            }
        
        return {
            "frames_processed": self.frames_processed,
            "detections_count": self.detections_count,
            "latest_detections_count": len(self.latest_detections),
            "frames_with_detections": self.frames_with_detections,
            "detection_rate_percent": round(detection_rate, 1),
            "tag_statistics": tag_stats
        }
