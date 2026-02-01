"""
StreamTap - Stage 7.
Holds the latest frame from a pipeline node for WebSocket streaming.
"""

import threading
import time
import cv2
import numpy as np
from typing import Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class StreamTapFrame:
    """A frame held by StreamTap."""
    frame: np.ndarray
    timestamp: float
    jpeg_bytes: Optional[bytes] = None

    def get_jpeg_bytes(self) -> bytes:
        """Lazy encode frame to JPEG."""
        if self.jpeg_bytes is None:
            encode_params = [cv2.IMWRITE_JPEG_QUALITY, 85]
            _, buf = cv2.imencode('.jpg', self.frame, encode_params)
            self.jpeg_bytes = buf.tobytes() if buf is not None else b''
        return self.jpeg_bytes


class StreamTap:
    """
    Holds the latest frame from a pipeline node.
    Thread-safe for concurrent frame updates and reads.
    """

    def __init__(self, tap_id: str, attach_point: str):
        """
        Args:
            tap_id: Unique ID for this tap (usually node_id of the StreamTap sink)
            attach_point: The main path node_id this tap reads from
        """
        self.tap_id = tap_id
        self.attach_point = attach_point
        self._frame: Optional[StreamTapFrame] = None
        self._lock = threading.Lock()
        self._frame_count = 0
        self._created_at = time.time()

    def push_frame(self, frame: np.ndarray) -> None:
        """Update the latest frame (called by pipeline)."""
        with self._lock:
            self._frame = StreamTapFrame(
                frame=frame.copy(),
                timestamp=time.time(),
            )
            self._frame_count += 1

    def get_frame(self) -> Optional[StreamTapFrame]:
        """Get the latest frame (called by WebSocket streamer)."""
        with self._lock:
            return self._frame

    def get_jpeg(self) -> Optional[bytes]:
        """Get the latest frame as JPEG bytes."""
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.get_jpeg_bytes()

    def get_metrics(self) -> Dict[str, Any]:
        """Get tap metrics."""
        with self._lock:
            return {
                "tap_id": self.tap_id,
                "attach_point": self.attach_point,
                "frame_count": self._frame_count,
                "has_frame": self._frame is not None,
                "uptime_seconds": time.time() - self._created_at,
            }


class StreamTapRegistry:
    """
    Registry of StreamTaps for all running pipeline instances.
    Maps (instance_id, tap_id) → StreamTap.
    """

    def __init__(self):
        self._taps: Dict[str, Dict[str, StreamTap]] = {}  # instance_id → {tap_id → StreamTap}
        self._lock = threading.Lock()

    def register_tap(self, instance_id: str, tap: StreamTap) -> None:
        """Register a StreamTap for a pipeline instance."""
        with self._lock:
            if instance_id not in self._taps:
                self._taps[instance_id] = {}
            self._taps[instance_id][tap.tap_id] = tap

    def unregister_instance(self, instance_id: str) -> None:
        """Remove all taps for a pipeline instance."""
        with self._lock:
            self._taps.pop(instance_id, None)

    def get_tap(self, instance_id: str, tap_id: str) -> Optional[StreamTap]:
        """Get a specific StreamTap."""
        with self._lock:
            return self._taps.get(instance_id, {}).get(tap_id)

    def list_taps(self, instance_id: str) -> Dict[str, StreamTap]:
        """List all taps for a pipeline instance."""
        with self._lock:
            return dict(self._taps.get(instance_id, {}))

    def list_all(self) -> Dict[str, Dict[str, Any]]:
        """List all taps with metrics."""
        with self._lock:
            result = {}
            for inst_id, taps in self._taps.items():
                result[inst_id] = {tid: t.get_metrics() for tid, t in taps.items()}
            return result
