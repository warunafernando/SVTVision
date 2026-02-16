"""
GPU-accelerated frame-to-JPEG encoding for streaming (CUDA path).
- Encoding: nvJPEG (CUDA) when available, else CPU cv2.imencode.
- Stream path: optional BGR→Y on GPU (CuPy) for AprilTag, then encode on GPU.
"""

import sys
from typing import Optional
import numpy as np

# Lazy singleton for GPU encoder (nvJPEG); None = not tried yet, False = unavailable, else encoder instance
_nvjpeg_encoder: Optional[object] = None
_stream_cuda_logged = False


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
    # nvJPEG path: only for 3-channel frames. (Grayscale frames are better encoded on CPU via cv2.imencode.)
    encoder = _init_gpu_encoder()
    if (
        encoder is not None
        and hasattr(encoder, 'encode')
        and getattr(frame, "ndim", 0) == 3
        and frame.shape[2] == 3
    ):
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


def encode_frame_for_stream(
    frame: np.ndarray,
    use_case: str = "stream_only",
    quality: int = 85,
) -> Optional[bytes]:
    """
    Encode a frame for the streaming path using CUDA when available.
    - use_case "apriltag": convert to Y (grayscale) on GPU if CuPy available, then encode.
    - use_case "stream_only": encode as-is.
    Encoding uses nvJPEG (CUDA) when available, else CPU.
    Returns JPEG bytes or None on failure.
    """
    global _stream_cuda_logged
    frame_to_encode = frame

    if use_case == "apriltag" and frame.ndim == 3 and frame.shape[2] == 3:
        try:
            from .cuda_convert import bgr_to_grayscale_bgr
            frame_to_encode = bgr_to_grayscale_bgr(frame)
            if not _stream_cuda_logged:
                from .cuda_convert import is_gpu_conversion_available
                if is_gpu_conversion_available():
                    print("[Stream] CUDA: BGR→Y on GPU (CuPy), then nvJPEG encode", file=sys.stderr)
                _stream_cuda_logged = True
        except Exception:
            import cv2
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            frame_to_encode = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    elif use_case == "apriltag" and frame.ndim == 2:
        import cv2
        frame_to_encode = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

    out = encode_frame_to_jpeg(frame_to_encode, quality=quality)
    return out if out else None
