"""GPU preprocessing using CuPy only (no OpenCV in the GPU path)."""

import numpy as np
from typing import Optional, Dict, Any

# Optional CuPy: GPU path uses only CuPy; fallback uses OpenCV
try:
    import cupy as cp
    from cupyx.scipy import ndimage as cp_ndimage
    _CUPY_AVAILABLE = True
except ImportError:
    cp = None
    cp_ndimage = None
    _CUPY_AVAILABLE = False

# OpenCV only for CPU fallback (frame I/O elsewhere still uses OpenCV)
import cv2

from ..ports.preprocess_port import PreprocessPort
from ..services.logging_service import LoggingService


# BGR weights for grayscale (OpenCV convention): 0.114*B + 0.587*G + 0.299*R
_GRAY_WEIGHTS_BGR = np.array([0.114, 0.587, 0.299], dtype=np.float32)


def get_preprocess_gpu_runtime() -> str:
    """Return 'gpu' if CuPy is available (GPU path), else 'cpu' (OpenCV fallback)."""
    return "gpu" if _CUPY_AVAILABLE else "cpu"


class GpuPreprocessAdapter(PreprocessPort):
    """
    Preprocess on GPU using CuPy only (no OpenCV in GPU path).
    Steps: grayscale, Gaussian blur, adaptive/binary threshold, optional morphology.
    Falls back to OpenCV CPU when CuPy is not available or GPU path fails.
    """

    def __init__(self, logger: LoggingService):
        self.logger = logger
        self._cupy_ok = _CUPY_AVAILABLE
        if self._cupy_ok:
            self.logger.info("[Preprocess GPU] Using CuPy (no OpenCV in GPU path)")
        else:
            self.logger.info("[Preprocess GPU] CuPy not available, using OpenCV CPU fallback")
        # Config keys match CPU preprocess (full parity); GPU path uses CuPy for all steps
        self.config = {
            "blur_kernel_size": 3,
            "threshold_type": "adaptive",
            "adaptive_thresholding": False,
            "contrast_normalization": False,
            "adaptive_method": getattr(cv2, "ADAPTIVE_THRESH_GAUSSIAN_C", 1),
            "adaptive_threshold_type": getattr(cv2, "THRESH_BINARY", 0),
            "adaptive_block_size": 15,
            "adaptive_c": 3,
            "binary_threshold": 127,
            "morphology": False,
            "morph_kernel_size": 3,
        }

    def preprocess(self, frame: np.ndarray) -> Optional[np.ndarray]:
        if self._cupy_ok:
            out = self._preprocess_gpu(frame)
            if out is not None:
                return out
        return self._preprocess_cpu(frame)

    def _preprocess_gpu(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Full pipeline on GPU with CuPy only (no OpenCV)."""
        try:
            xp = cp
            # 1) Grayscale (BGR -> gray)
            if frame.ndim == 3 and frame.shape[2] == 3:
                arr = cp.asarray(frame, dtype=cp.float32)
                w = cp.asarray(_GRAY_WEIGHTS_BGR, dtype=cp.float32)
                gray = (arr * w).sum(axis=2)
                gray = cp.clip(gray, 0, 255).astype(cp.uint8)
            else:
                gray = cp.asarray(frame, dtype=cp.uint8)

            # 1b) Optional: contrast normalization (min-max stretch)
            if self.config.get("contrast_normalization", False):
                gmin, gmax = float(cp.min(gray)), float(cp.max(gray))
                if gmax > gmin:
                    gray = cp.clip((gray.astype(cp.float32) - gmin) / (gmax - gmin) * 255, 0, 255).astype(cp.uint8)

            # 2) Gaussian blur
            blur_size = min(31, max(0, self.config["blur_kernel_size"]))
            if blur_size > 0 and blur_size % 2 == 1:
                sigma = max(0.5, (blur_size - 1) / 4.0)
                gray = gray.astype(cp.float32)
                blurred = cp_ndimage.gaussian_filter(gray, sigma=sigma, mode="nearest")
                blurred = cp.clip(blurred, 0, 255).astype(cp.uint8)
            else:
                blurred = gray

            # 3) Threshold
            if self.config["threshold_type"] == "adaptive":
                block_size = max(3, self.config["adaptive_block_size"])
                if block_size % 2 == 0:
                    block_size += 1
                c = float(self.config["adaptive_c"])
                sigma_adapt = max(0.5, block_size / 4.0)
                blurred_f = blurred.astype(cp.float32)
                local_mean = cp_ndimage.gaussian_filter(blurred_f, sigma=sigma_adapt, mode="nearest")
                thresh = local_mean - c
                processed = cp.where(blurred_f >= thresh, 255, 0).astype(cp.uint8)
            else:
                t = int(self.config["binary_threshold"])
                processed = cp.where(blurred >= t, 255, 0).astype(cp.uint8)

            # 4) Morphology (close then open)
            if self.config["morphology"]:
                k = max(1, self.config["morph_kernel_size"])
                structure = cp.ones((k, k), dtype=cp.uint8)
                binary = processed > 0
                binary = cp_ndimage.binary_closing(binary, structure=structure)
                binary = cp_ndimage.binary_opening(binary, structure=structure)
                processed = cp.where(binary, 255, 0).astype(cp.uint8)

            return cp.asnumpy(processed)
        except Exception as e:
            self.logger.debug(f"[Preprocess GPU] CuPy path failed: {e}, using CPU fallback")
            return None

    def _preprocess_cpu(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """OpenCV CPU fallback (same behavior as PreprocessAdapter)."""
        try:
            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame.copy()

            if self.config.get("contrast_normalization", False):
                gmin, gmax = gray.min(), gray.max()
                if gmax > gmin:
                    gray = np.clip((gray.astype(np.float32) - gmin) / (gmax - gmin) * 255, 0, 255).astype(np.uint8)

            blur_size = self.config["blur_kernel_size"]
            if blur_size > 0 and blur_size % 2 == 1:
                blurred = cv2.GaussianBlur(gray, (blur_size, blur_size), 0)
            else:
                blurred = gray

            use_adaptive = self.config.get("adaptive_thresholding", self.config.get("threshold_type") == "adaptive")
            if use_adaptive:
                thresholded = cv2.adaptiveThreshold(
                    blurred, 255,
                    self.config["adaptive_method"],
                    self.config["adaptive_threshold_type"],
                    self.config["adaptive_block_size"],
                    self.config["adaptive_c"],
                )
            else:
                _, thresholded = cv2.threshold(
                    blurred, self.config["binary_threshold"], 255, cv2.THRESH_BINARY
                )

            if self.config["morphology"]:
                k = self.config["morph_kernel_size"]
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))
                processed = cv2.morphologyEx(thresholded, cv2.MORPH_CLOSE, kernel)
                processed = cv2.morphologyEx(processed, cv2.MORPH_OPEN, kernel)
            else:
                processed = thresholded

            return processed
        except Exception as e:
            self.logger.error(f"[Preprocess GPU] CPU fallback error: {e}")
            return None

    def get_config(self) -> Dict[str, Any]:
        return self.config.copy()

    def set_config(self, config: Dict[str, Any]) -> bool:
        try:
            if "blur_kernel_size" in config:
                blur_size = int(config["blur_kernel_size"])
                if blur_size >= 0 and blur_size % 2 == 1:
                    self.config["blur_kernel_size"] = blur_size
            if "threshold_type" in config and config["threshold_type"] in ("adaptive", "binary"):
                self.config["threshold_type"] = config["threshold_type"]
            if "adaptive_block_size" in config:
                block_size = int(config["adaptive_block_size"])
                if block_size >= 3 and block_size % 2 == 1:
                    self.config["adaptive_block_size"] = block_size
            if "adaptive_c" in config:
                self.config["adaptive_c"] = float(config["adaptive_c"])
            if "binary_threshold" in config:
                t = int(config["binary_threshold"])
                if 0 <= t <= 255:
                    self.config["binary_threshold"] = t
            if "morphology" in config:
                self.config["morphology"] = bool(config["morphology"])
            if "morph_kernel_size" in config:
                k = int(config["morph_kernel_size"])
                if k >= 1:
                    self.config["morph_kernel_size"] = k
            if "adaptive_thresholding" in config:
                self.config["adaptive_thresholding"] = bool(config["adaptive_thresholding"])
            if "contrast_normalization" in config:
                self.config["contrast_normalization"] = bool(config["contrast_normalization"])
            return True
        except Exception as e:
            self.logger.error(f"[Preprocess GPU] set_config error: {e}")
            return False
