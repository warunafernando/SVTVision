"""Unit tests for StreamTap - Stage 7."""

import pytest
import numpy as np
import sys
from pathlib import Path

backend_src = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(backend_src))

from plana.domain.stream_tap import StreamTap, StreamTapRegistry


@pytest.fixture
def dummy_frame():
    """Create a dummy frame for testing."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


def test_stream_tap_push_and_get(dummy_frame):
    """Test pushing and getting frames from StreamTap."""
    tap = StreamTap(tap_id="tap1", attach_point="node1")
    
    # Initially no frame
    assert tap.get_frame() is None
    assert tap.get_jpeg() is None
    
    # Push a frame
    tap.push_frame(dummy_frame)
    
    # Now should have a frame
    frame = tap.get_frame()
    assert frame is not None
    assert frame.frame.shape == (480, 640, 3)
    assert frame.timestamp > 0


def test_stream_tap_jpeg_encoding(dummy_frame):
    """Test JPEG encoding of frames."""
    tap = StreamTap(tap_id="tap1", attach_point="node1")
    tap.push_frame(dummy_frame)
    
    jpeg = tap.get_jpeg()
    assert jpeg is not None
    assert len(jpeg) > 0
    # JPEG magic bytes
    assert jpeg[:2] == b'\xff\xd8'


def test_stream_tap_metrics(dummy_frame):
    """Test StreamTap metrics."""
    tap = StreamTap(tap_id="tap1", attach_point="node1")
    
    metrics = tap.get_metrics()
    assert metrics["tap_id"] == "tap1"
    assert metrics["attach_point"] == "node1"
    assert metrics["frame_count"] == 0
    assert metrics["has_frame"] is False
    assert "fps" in metrics
    assert metrics["fps"] == 0.0

    tap.push_frame(dummy_frame)
    metrics = tap.get_metrics()
    assert metrics["frame_count"] == 1
    assert metrics["has_frame"] is True
    assert "fps" in metrics


def test_stream_tap_registry_register_and_get():
    """Test registering and getting StreamTaps from registry."""
    registry = StreamTapRegistry()
    tap1 = StreamTap(tap_id="tap1", attach_point="node1")
    tap2 = StreamTap(tap_id="tap2", attach_point="node2")
    
    registry.register_tap("instance1", tap1)
    registry.register_tap("instance1", tap2)
    
    assert registry.get_tap("instance1", "tap1") is tap1
    assert registry.get_tap("instance1", "tap2") is tap2
    assert registry.get_tap("instance1", "tap3") is None
    assert registry.get_tap("instance2", "tap1") is None


def test_stream_tap_registry_unregister():
    """Test unregistering taps from registry."""
    registry = StreamTapRegistry()
    tap1 = StreamTap(tap_id="tap1", attach_point="node1")
    
    registry.register_tap("instance1", tap1)
    assert registry.get_tap("instance1", "tap1") is tap1
    
    registry.unregister_instance("instance1")
    assert registry.get_tap("instance1", "tap1") is None


def test_stream_tap_registry_list_taps():
    """Test listing taps for an instance."""
    registry = StreamTapRegistry()
    tap1 = StreamTap(tap_id="tap1", attach_point="node1")
    tap2 = StreamTap(tap_id="tap2", attach_point="node2")
    
    registry.register_tap("instance1", tap1)
    registry.register_tap("instance1", tap2)
    
    taps = registry.list_taps("instance1")
    assert len(taps) == 2
    assert "tap1" in taps
    assert "tap2" in taps


def test_stream_tap_thread_safety(dummy_frame):
    """Test thread safety of StreamTap."""
    import threading
    
    tap = StreamTap(tap_id="tap1", attach_point="node1")
    errors = []
    
    def pusher():
        for _ in range(100):
            try:
                tap.push_frame(dummy_frame)
            except Exception as e:
                errors.append(e)
    
    def reader():
        for _ in range(100):
            try:
                tap.get_frame()
                tap.get_jpeg()
            except Exception as e:
                errors.append(e)
    
    threads = [
        threading.Thread(target=pusher),
        threading.Thread(target=reader),
        threading.Thread(target=pusher),
        threading.Thread(target=reader),
    ]
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    assert len(errors) == 0, f"Thread safety errors: {errors}"
