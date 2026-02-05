"""
GPU-accelerated frame-to-JPEG encoding for streaming.
Uses nvJPEG when available (pynvjpeg), otherwise falls back to CPU cv2.imencode.
"""

import sys
from typing import Optional
import numpy as np

# Lazy singleton for GPU encoder (nvJPEG); None = not tried yet, False = unavailable, else encoder instance
_nvjpeg_encoder: Optional[object] = None


def _init_gpu_encoder() -> Optional[object]:
    """Try to create nvJPEG encoder. Returns encoder instance or None."""
    global _nvjpeg_encoder
    if _nvjpeg_encoder is not None:
        return _nvjpeg_encoder if _nvjpeg_encoder is not False else None
    try:
        from nvjpeg import NvJpeg
        _nvjpeg_encoder = NvJpeg()
        print("[GPU] Video frame→stream encoding: nvJPEG (GPU)", file=sys.stderr)
        return _nvjpeg_encoder
    except Exception:
        try:
            import nvjpeg
            _nvjpeg_encoder = nvjpeg.NvJpeg() if hasattr(nvjpeg, 'NvJpeg') else None
            if _nvjpeg_encoder is not None:
                print("[GPU] Video frame→stream encoding: nvJPEG (GPU)", file=sys.stderr)
            return _nvjpeg_encoder
        except Exception:
            pass
        _nvjpeg_encoder = False
        return None


def encode_frame_to_jpeg(frame: np.ndarray, quality: int = 85) -> bytes:
    """
    Encode a BGR frame (H, W, 3) to JPEG bytes for streaming.
    Uses GPU (nvJPEG) when available, otherwise CPU (cv2.imencode).
    """
    encoder = _init_gpu_encoder()
    if encoder is not None and hasattr(encoder, 'encode'):
        try:
            # pynvjpeg: encode(img) or encode(img, quality); OpenCV frames are BGR (nvJPEG accepts BGR)
            out = encoder.encode(frame, quality)
            if out is not None and isinstance(out, (bytes, bytearray)):
                return bytes(out)
        except Exception:
            pass
    # CPU fallback
    import cv2
    _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if buf is not None else b''


def is_gpu_encoding_available() -> bool:
    """Return True if GPU (nvJPEG) encoding will be used."""
    return _init_gpu_encoder() is not None
