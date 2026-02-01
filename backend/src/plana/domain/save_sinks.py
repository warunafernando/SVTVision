"""
SaveVideo / SaveImage - Stage 8.
Side-tap sinks that write frames to file.
"""

import os
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any

import cv2
import numpy as np


class SaveVideoSink:
    """
    Writes frames to a video file (Stage 8).
    Opens writer on first frame; call close() when pipeline stops.
    """

    def __init__(
        self,
        sink_id: str,
        attach_point: str,
        output_path: str,
        fps: float = 30.0,
        fourcc: str = "mp4v",
        logger: Optional[Any] = None,
    ):
        self.sink_id = sink_id
        self.attach_point = attach_point
        self.output_path = str(Path(output_path).resolve())
        self.fps = max(1.0, min(300.0, fps))
        self.fourcc = fourcc
        self.logger = logger
        self._writer: Optional[cv2.VideoWriter] = None
        self._lock = threading.Lock()
        self._frame_count = 0
        self._created_at = time.time()

    def push_frame(self, frame: np.ndarray) -> None:
        """Write frame to video file. Opens writer on first frame."""
        with self._lock:
            if frame is None or frame.size == 0:
                return
            h, w = frame.shape[:2]
            if self._writer is None:
                os.makedirs(os.path.dirname(self.output_path) or ".", exist_ok=True)
                fourcc_code = cv2.VideoWriter_fourcc(*self.fourcc)
                self._writer = cv2.VideoWriter(
                    self.output_path,
                    fourcc_code,
                    self.fps,
                    (w, h),
                    isColor=(len(frame.shape) == 3 and frame.shape[2] >= 3),
                )
                if not self._writer.isOpened():
                    if self.logger:
                        self.logger.error(f"[SaveVideo] Failed to open {self.output_path}")
                    return
                if self.logger:
                    self.logger.info(f"[SaveVideo] Opened {self.output_path} {w}x{h} @ {self.fps}fps")
            if self._writer.isOpened():
                self._writer.write(frame)
                self._frame_count += 1

    def close(self) -> None:
        """Release video writer. Call when pipeline stops."""
        with self._lock:
            if self._writer is not None:
                self._writer.release()
                self._writer = None
                if self.logger:
                    self.logger.info(f"[SaveVideo] Closed {self.output_path}, wrote {self._frame_count} frames")

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "sink_id": self.sink_id,
                "attach_point": self.attach_point,
                "output_path": self.output_path,
                "frame_count": self._frame_count,
                "is_open": self._writer is not None and self._writer.isOpened(),
                "uptime_seconds": time.time() - self._created_at,
            }


class SaveImageSink:
    """
    Writes frames to image file(s) (Stage 8).
    Mode: overwrite = single file; sequence = frame_00001.jpg, ...
    """

    def __init__(
        self,
        sink_id: str,
        attach_point: str,
        output_path: str,
        mode: str = "overwrite",
        logger: Optional[Any] = None,
    ):
        self.sink_id = sink_id
        self.attach_point = attach_point
        self._output_path = str(Path(output_path).resolve())
        self.mode = mode if mode in ("overwrite", "sequence") else "overwrite"
        self.logger = logger
        self._lock = threading.Lock()
        self._frame_count = 0
        self._sequence = 0
        self._created_at = time.time()

    def push_frame(self, frame: np.ndarray) -> None:
        """Write frame to image file."""
        with self._lock:
            if frame is None or frame.size == 0:
                return
            if self.mode == "overwrite":
                path = self._output_path
            else:
                self._sequence += 1
                base = Path(self._output_path)
                stem = base.stem
                suffix = base.suffix or ".jpg"
                parent = base.parent
                path = str(parent / f"{stem}_{self._sequence:05d}{suffix}")
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            try:
                success = cv2.imwrite(path, frame)
                if success:
                    self._frame_count += 1
                elif self.logger:
                    self.logger.warning(f"[SaveImage] Failed to write {path}")
            except Exception as e:
                if self.logger:
                    self.logger.error(f"[SaveImage] Error writing {path}: {e}")

    def close(self) -> None:
        """No-op for image sink (each write is independent)."""
        pass

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "sink_id": self.sink_id,
                "attach_point": self.attach_point,
                "output_path": self._output_path,
                "mode": self.mode,
                "frame_count": self._frame_count,
                "sequence": self._sequence,
                "uptime_seconds": time.time() - self._created_at,
            }
