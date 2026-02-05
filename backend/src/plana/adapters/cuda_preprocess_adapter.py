"""GPU-accelerated preprocessing adapter (OpenCV CUDA when available, else CPU fallback)."""

import cv2
import numpy as np
from typing import Optional, Dict, Any
from ..ports.preprocess_port import PreprocessPort
from ..services.logging_service import LoggingService


def _cuda_available() -> bool:
    """True if OpenCV was built with CUDA and a device is available."""
    try:
        if not hasattr(cv2, "cuda"):
            return False
        return getattr(cv2.cuda, "getCudaEnabledDeviceCount", lambda: 0)() > 0
    except Exception:
        return False


class CudaPreprocessAdapter(PreprocessPort):
    """Preprocess on GPU when OpenCV CUDA is available, otherwise same as CPU PreprocessAdapter."""

    def __init__(self, logger: LoggingService):
        self.logger = logger
        self._cuda = _cuda_available()
        if self._cuda:
            self.logger.info("[Preprocess GPU] Using OpenCV CUDA")
        else:
            self.logger.info("[Preprocess GPU] CUDA not available, using CPU fallback")
        self.config = {
            "blur_kernel_size": 3,
            "threshold_type": "adaptive",
            "adaptive_method": cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            "adaptive_threshold_type": cv2.THRESH_BINARY,
            "adaptive_block_size": 15,
            "adaptive_c": 3,
            "binary_threshold": 127,
            "morphology": False,
            "morph_kernel_size": 3,
        }

    def preprocess(self, frame: np.ndarray) -> Optional[np.ndarray]:
        if self._cuda:
            out = self._preprocess_gpu(frame)
            if out is not None:
                return out
        return self._preprocess_cpu(frame)

    def _preprocess_gpu(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Run preprocessing on GPU when CUDA APIs exist; otherwise None (caller uses CPU)."""
        try:
            cuda = cv2.cuda
            if len(frame.shape) == 3:
                gpu_in = cuda.GpuMat()
                gpu_in.upload(frame)
                gpu_gray = cuda.cvtColor(gpu_in, cv2.COLOR_BGR2GRAY)
            else:
                gpu_gray = cuda.GpuMat()
                gpu_gray.upload(frame)

            blur_size = min(31, max(0, self.config["blur_kernel_size"]))
            if blur_size > 0 and blur_size % 2 == 1:
                gpu_blur = cuda.createGaussianFilter(
                    cv2.CV_8UC1, cv2.CV_8UC1, (blur_size, blur_size), 0, 0
                )
                gpu_blurred = cuda.GpuMat()
                gpu_blur.apply(gpu_gray, gpu_blurred)
            else:
                gpu_blurred = gpu_gray

            blurred = gpu_blurred.download()
            if self.config["threshold_type"] == "adaptive":
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
            self.logger.debug(f"[Preprocess GPU] GPU path failed: {e}, using CPU")
            return None

    def _preprocess_cpu(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Same logic as PreprocessAdapter (CPU)."""
        try:
            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame.copy()

            blur_size = self.config["blur_kernel_size"]
            if blur_size > 0 and blur_size % 2 == 1:
                blurred = cv2.GaussianBlur(gray, (blur_size, blur_size), 0)
            else:
                blurred = gray

            if self.config["threshold_type"] == "adaptive":
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
            return True
        except Exception as e:
            self.logger.error(f"[Preprocess GPU] set_config error: {e}")
            return False
