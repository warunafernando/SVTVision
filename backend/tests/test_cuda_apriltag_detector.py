"""CUDA AprilTag detector tests.

These tests are skip-safe when the native CUDA module is not built/installed.
"""

import numpy as np
import pytest

from plana.services.logging_service import LoggingService
from plana.adapters.preprocess_adapter import PreprocessAdapter
from plana.domain.vision_pipeline import VisionPipeline
from plana.domain.apriltag_timed_stages import (
    ApriltagTimedPreprocessStage,
    ApriltagTimedDetectStage,
    ApriltagTimedOverlayStage,
)
from plana.domain.apriltag_pipeline_metrics_proxy import ApriltagPipelineMetricsProxy


def _native_cuda_module_available() -> bool:
    try:
        from plana.adapters import _cuda_apriltag  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _native_cuda_module_available(), reason="CUDA native module not built")
def test_cuda_detector_pipeline_metrics_keys_present():
    """When CUDA detector is used, stage_timings_ms includes detect.gpu_stage_ms etc."""
    from plana.adapters.cuda_apriltag_detector_adapter import CudaAprilTagDetectorAdapter

    logger = LoggingService()
    pre = PreprocessAdapter(logger)
    tag = CudaAprilTagDetectorAdapter(logger, family="tag36h11")

    stages = [
        ApriltagTimedPreprocessStage(pre),
        ApriltagTimedDetectStage(tag),
        ApriltagTimedOverlayStage(tag),
    ]
    pipe = VisionPipeline(pre, tag, logger, stages=stages)
    proxy = ApriltagPipelineMetricsProxy(pipe, tag)

    frame = np.random.randint(0, 255, (480, 640), dtype=np.uint8)
    proxy.process_frame(frame)
    metrics = proxy.get_metrics()

    stage_timings = metrics.get("stage_timings_ms") or {}
    assert "detect.gpu_stage_ms" in stage_timings
    assert "detect.cpu_decode_ms" in stage_timings
    assert "detect.detector_total_ms" in stage_timings

