"""Unit tests for SaveVideo / SaveImage - Stage 8."""

import os
import tempfile
import pytest
import numpy as np
import sys
from pathlib import Path

backend_src = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(backend_src))

from plana.domain.save_sinks import SaveVideoSink, SaveImageSink


@pytest.fixture
def dummy_frame():
    """Create a dummy BGR frame for testing."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for output files."""
    with tempfile.TemporaryDirectory() as d:
        yield d


def test_save_video_opens_on_first_frame(dummy_frame, temp_dir):
    """SaveVideoSink opens writer on first push_frame."""
    path = os.path.join(temp_dir, "out.mp4")
    sink = SaveVideoSink(sink_id="sv1", attach_point="n1", output_path=path, fps=30.0)
    
    sink.push_frame(dummy_frame)
    sink.push_frame(dummy_frame)
    
    assert os.path.isfile(path)
    assert sink.get_metrics()["frame_count"] == 2
    sink.close()
    assert sink.get_metrics()["frame_count"] == 2


def test_save_video_close_releases_writer(dummy_frame, temp_dir):
    """SaveVideoSink.close() releases writer."""
    path = os.path.join(temp_dir, "out.mp4")
    sink = SaveVideoSink(sink_id="sv1", attach_point="n1", output_path=path, fps=30.0)
    sink.push_frame(dummy_frame)
    sink.close()
    
    metrics = sink.get_metrics()
    assert metrics["is_open"] is False
    assert metrics["frame_count"] == 1


def test_save_video_file_validation(dummy_frame, temp_dir):
    """SaveVideoSink produces a valid video file (readable)."""
    path = os.path.join(temp_dir, "out.mp4")
    sink = SaveVideoSink(sink_id="sv1", attach_point="n1", output_path=path, fps=30.0)
    
    for _ in range(5):
        sink.push_frame(dummy_frame)
    sink.close()
    
    assert os.path.isfile(path)
    assert os.path.getsize(path) > 0
    
    import cv2
    cap = cv2.VideoCapture(path)
    assert cap.isOpened()
    ret, frame = cap.read()
    assert ret is True
    assert frame is not None
    assert frame.shape == (480, 640, 3)
    cap.release()


def test_save_image_overwrite(dummy_frame, temp_dir):
    """SaveImageSink overwrite mode writes single file."""
    path = os.path.join(temp_dir, "out.jpg")
    sink = SaveImageSink(sink_id="si1", attach_point="n1", output_path=path, mode="overwrite")
    
    sink.push_frame(dummy_frame)
    sink.push_frame(dummy_frame)
    
    assert os.path.isfile(path)
    assert sink.get_metrics()["frame_count"] == 2
    assert sink.get_metrics()["mode"] == "overwrite"


def test_save_image_sequence(dummy_frame, temp_dir):
    """SaveImageSink sequence mode writes multiple files."""
    path = os.path.join(temp_dir, "frame.jpg")
    sink = SaveImageSink(sink_id="si1", attach_point="n1", output_path=path, mode="sequence")
    
    sink.push_frame(dummy_frame)
    sink.push_frame(dummy_frame)
    sink.push_frame(dummy_frame)
    
    assert sink.get_metrics()["frame_count"] == 3
    assert sink.get_metrics()["sequence"] == 3
    # frame_00001.jpg, frame_00002.jpg, frame_00003.jpg
    base = Path(path)
    for i in range(1, 4):
        f = base.parent / f"{base.stem}_{i:05d}{base.suffix or '.jpg'}"
        assert f.exists(), f"Expected {f}"


def test_save_image_file_validation(dummy_frame, temp_dir):
    """SaveImageSink produces valid image file (readable)."""
    path = os.path.join(temp_dir, "out.jpg")
    sink = SaveImageSink(sink_id="si1", attach_point="n1", output_path=path)
    sink.push_frame(dummy_frame)
    
    assert os.path.isfile(path)
    assert os.path.getsize(path) > 0
    
    import cv2
    img = cv2.imread(path)
    assert img is not None
    assert img.shape == (480, 640, 3)


def test_save_video_ignores_empty_frame(temp_dir):
    """SaveVideoSink ignores None/empty frame."""
    path = os.path.join(temp_dir, "out.mp4")
    sink = SaveVideoSink(sink_id="sv1", attach_point="n1", output_path=path)
    
    sink.push_frame(None)
    assert sink.get_metrics()["frame_count"] == 0
    sink.push_frame(np.array([]))
    assert sink.get_metrics()["frame_count"] == 0
