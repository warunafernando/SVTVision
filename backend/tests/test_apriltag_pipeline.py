"""Tests for AprilTag pipeline: build, process frame, FPS, and API (status/start/stop)."""

import numpy as np
import pytest
from pathlib import Path

from plana.services.logging_service import LoggingService
from plana.adapters.preprocess_adapter import PreprocessAdapter
from plana.adapters.apriltag_detector_adapter import AprilTagDetectorAdapter
from plana.domain.vision_pipeline import VisionPipeline
from plana.domain.camera_service import CameraService, APRILTAG_PIPELINE_LOG
from plana.services.camera_config_service import CameraConfigService


@pytest.fixture
def logger():
    return LoggingService()


@pytest.fixture
def config_dir():
    return Path(__file__).resolve().parent.parent.parent / "config"


def test_apriltag_log_prefix():
    """Logs can be filtered by this prefix."""
    assert APRILTAG_PIPELINE_LOG == "[AprilTag pipeline]"


def test_build_default_apriltag_pipeline(logger):
    """Building default pipeline (preprocess + detect + overlay) succeeds."""
    pre = PreprocessAdapter(logger)
    tag = AprilTagDetectorAdapter(logger, family="tag36h11")
    pipe = VisionPipeline(pre, tag, logger)
    assert pipe is not None
    assert pipe.frames_processed == 0


def test_apriltag_pipeline_process_frame(logger):
    """Process one frame through pipeline; all stages produce output."""
    pre = PreprocessAdapter(logger)
    tag = AprilTagDetectorAdapter(logger, family="tag36h11")
    pipe = VisionPipeline(pre, tag, logger)
    frame = np.random.randint(0, 255, (480, 640), dtype=np.uint8)
    out = pipe.process_frame(frame)
    assert "raw" in out
    assert "preprocess" in out
    assert "detect_overlay" in out
    assert "detections" in out
    assert pipe.frames_processed == 1


def test_apriltag_pipeline_metrics_fps(logger):
    """After processing several frames, get_metrics includes fps."""
    pre = PreprocessAdapter(logger)
    tag = AprilTagDetectorAdapter(logger, family="tag36h11")
    pipe = VisionPipeline(pre, tag, logger)
    frame = np.random.randint(0, 255, (480, 640), dtype=np.uint8)
    for _ in range(10):
        pipe.process_frame(frame)
    metrics = pipe.get_metrics()
    assert "fps" in metrics
    assert "frames_processed" in metrics
    assert metrics["frames_processed"] == 10


def test_camera_service_apriltag_status_and_start_stop(logger, config_dir):
    """get_apriltag_status, start_apriltag_pipeline, stop_apriltag_pipeline with no cameras."""
    cc = CameraConfigService(config_dir, logger)
    svc = CameraService(logger, cc)
    status = svc.get_apriltag_status()
    assert status["running"] is False
    assert status["cameras"] == []
    r = svc.start_apriltag_pipeline()
    assert r["ok"] is True
    assert r["started"] == []
    r = svc.stop_apriltag_pipeline()
    assert r["ok"] is True
    assert r["stopped"] == []
