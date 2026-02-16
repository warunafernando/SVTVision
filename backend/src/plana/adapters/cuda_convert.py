"""
GPU-accelerated BGR → grayscale (as 3-channel BGR) for camera/stream path.
Uses CuPy when available to reduce CPU load in camera manager; falls back to OpenCV.
"""

import sys
import numpy as np
from typing import Optional

try:
    import cupy as cp
    _CUPY_AVAILABLE = True
except ImportError:
    cp = None
    _CUPY_AVAILABLE = False

# BGR weights for grayscale (OpenCV convention): 0.114*B + 0.587*G + 0.299*R
_GRAY_WEIGHTS_BGR = np.array([0.114, 0.587, 0.299], dtype=np.float32)
_cuda_convert_logged = False


def bgr_to_grayscale_bgr(frame: np.ndarray) -> np.ndarray:
    """
    Convert BGR frame to grayscale represented as 3-channel BGR (for JPEG encode).
    Uses GPU (CuPy) when available to reduce CPU; otherwise cv2.cvtColor.
    """
    if _CUPY_AVAILABLE and frame.ndim == 3 and frame.shape[2] == 3:
        out = _bgr_to_grayscale_bgr_cuda(frame)
        if out is not None:
            return out
    return _bgr_to_grayscale_bgr_cpu(frame)


def _bgr_to_grayscale_bgr_cuda(frame: np.ndarray) -> Optional[np.ndarray]:
    """CuPy path: BGR → gray on GPU, return numpy BGR (3-channel gray)."""
    global _cuda_convert_logged
    try:
        arr = cp.asarray(frame, dtype=cp.float32)
        w = cp.asarray(_GRAY_WEIGHTS_BGR, dtype=cp.float32)
        gray = (arr * w).sum(axis=2)
        gray = cp.clip(gray, 0, 255).astype(cp.uint8)
        # Stack to 3 channels for BGR output (same as cv2 GRAY2BGR)
        gray_bgr = cp.stack([gray, gray, gray], axis=2)
        out = cp.asnumpy(gray_bgr)
        if not _cuda_convert_logged:
            print("[Camera] BGR→gray: using CUDA (CuPy)", file=sys.stderr)
            _cuda_convert_logged = True
        return out
    except Exception:
        return None


def _bgr_to_grayscale_bgr_cpu(frame: np.ndarray) -> np.ndarray:
    """OpenCV CPU path."""
    import cv2
    if frame.ndim == 3 and frame.shape[2] == 3:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    return frame


def is_gpu_conversion_available() -> bool:
    """True if BGR→gray will use GPU (CuPy)."""
    return _CUPY_AVAILABLE
