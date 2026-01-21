"""AprilTag detector adapter implementation."""

import cv2
import numpy as np
from typing import List
import apriltag
from ..ports.tag_detector_port import TagDetectorPort, TagDetection
from ..services.logging_service import LoggingService


class AprilTagDetectorAdapter(TagDetectorPort):
    """Adapter for AprilTag detection using apriltag library."""
    
    def __init__(self, logger: LoggingService, family: str = "tag36h11"):
        self.logger = logger
        self.family = family
        try:
            # Create AprilTag detector with optimized options for better detection
            options = apriltag.DetectorOptions(
                families=family,
                border=1,  # Border around tag (1 is standard)
                nthreads=1,  # Number of threads (1 for single camera processing)
                quad_decimate=1.0,  # Decimation factor (1.0 = full resolution)
                quad_blur=0.0,  # Blur for quad detection (0 = no blur)
                refine_edges=True,  # Refine edge detection
                refine_decode=False,  # Faster without refine_decode
                refine_pose=False,  # Faster without pose refinement
                debug=False,
                quad_contours=True  # Use quad contours
            )
            self.detector = apriltag.Detector(options)
            self.logger.info(f"AprilTagDetectorAdapter initialized with family {family}, optimized settings")
        except Exception as e:
            self.logger.error(f"Failed to initialize AprilTag detector: {e}")
            self.detector = None
    
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
            # Ensure frame is grayscale and uint8
            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame.copy()
            
            if gray.dtype != np.uint8:
                gray = (gray * 255).astype(np.uint8)
            
            # Detect tags
            detections_raw = self.detector.detect(gray)
            
            # Convert to TagDetection objects
            detections = []
            for det in detections_raw:
                if det.tag_id is not None:
                    # Extract corners (4 points)
                    corners = np.array([
                        [det.corners[0][0], det.corners[0][1]],
                        [det.corners[1][0], det.corners[1][1]],
                        [det.corners[2][0], det.corners[2][1]],
                        [det.corners[3][0], det.corners[3][1]]
                    ])
                    
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
            
            return detections
        
        except Exception as e:
            self.logger.error(f"Error detecting AprilTags: {e}")
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
            self.logger.error(f"Error drawing overlay: {e}")
            return frame
