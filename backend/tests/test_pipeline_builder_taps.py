"""Unit tests for Pipeline Builder with StreamTaps - Stage 7."""

import pytest
import sys
from pathlib import Path

backend_src = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(backend_src))

from plana.domain.pipeline_builder import build_pipeline_with_taps
from plana.domain.runtime_compiler import compile_graph
from plana.services.logging_service import LoggingService


def _node(id_: str, type_: str, **kw):
    return {"id": id_, "type": type_, **kw}


def _edge(id_: str, src: str, src_port: str, tgt: str, tgt_port: str):
    return {
        "id": id_,
        "source_node": src,
        "source_port": src_port,
        "target_node": tgt,
        "target_port": tgt_port,
    }


@pytest.fixture
def logger():
    return LoggingService()


def test_build_with_stream_tap(logger):
    """Build pipeline with a StreamTap attached to preprocess stage."""
    nodes = [
        _node("n1", "source", source_type="camera"),
        _node("n2", "stage", stage_id="preprocess_cpu"),
        _node("n3", "stage", stage_id="detect_apriltag_cpu"),
        _node("n4", "sink", sink_type="svt_output"),
        _node("tap1", "sink", sink_type="stream_tap"),  # StreamTap
    ]
    edges = [
        _edge("e1", "n1", "frame", "n2", "frame"),
        _edge("e2", "n2", "frame", "n3", "frame"),
        _edge("e3", "n3", "frame", "n4", "frame"),
        _edge("e4", "n2", "frame", "tap1", "frame"),  # StreamTap attached to preprocess output
    ]
    
    plan = compile_graph(nodes, edges)
    assert len(plan.side_taps) == 1
    assert plan.side_taps[0].sink_type == "stream_tap"
    assert plan.side_taps[0].attach_point == "n2"  # preprocess node
    
    result = build_pipeline_with_taps(plan, nodes, logger)
    assert result is not None
    pipeline, stream_taps, save_sinks = result
    
    assert len(stream_taps) == 1
    assert stream_taps[0].tap_id == "tap1"
    assert stream_taps[0].attach_point == "n2"
    assert len(save_sinks) == 0


def test_build_with_multiple_stream_taps(logger):
    """Build pipeline with multiple StreamTaps."""
    nodes = [
        _node("n1", "source", source_type="camera"),
        _node("n2", "stage", stage_id="preprocess_cpu"),
        _node("n3", "stage", stage_id="detect_apriltag_cpu"),
        _node("n4", "stage", stage_id="overlay_cpu"),
        _node("n5", "sink", sink_type="svt_output"),
        _node("tap1", "sink", sink_type="stream_tap"),
        _node("tap2", "sink", sink_type="stream_tap"),
    ]
    edges = [
        _edge("e1", "n1", "frame", "n2", "frame"),
        _edge("e2", "n2", "frame", "n3", "frame"),
        _edge("e3", "n3", "frame", "n4", "frame"),
        _edge("e4", "n4", "frame", "n5", "frame"),
        _edge("e5", "n2", "frame", "tap1", "frame"),  # After preprocess
        _edge("e6", "n4", "frame", "tap2", "frame"),  # After overlay
    ]
    
    plan = compile_graph(nodes, edges)
    assert len(plan.side_taps) == 2
    
    result = build_pipeline_with_taps(plan, nodes, logger)
    assert result is not None
    pipeline, stream_taps, save_sinks = result
    
    assert len(stream_taps) == 2
    assert len(save_sinks) == 0
    tap_ids = {t.tap_id for t in stream_taps}
    assert "tap1" in tap_ids
    assert "tap2" in tap_ids


def test_build_no_stream_taps(logger):
    """Build pipeline without StreamTaps: a preview tap is auto-added so user can see video."""
    nodes = [
        _node("n1", "source", source_type="camera"),
        _node("n2", "stage", stage_id="preprocess_cpu"),
        _node("n3", "sink", sink_type="svt_output"),
    ]
    edges = [
        _edge("e1", "n1", "frame", "n2", "frame"),
        _edge("e2", "n2", "frame", "n3", "frame"),
    ]
    
    plan = compile_graph(nodes, edges)
    assert len(plan.side_taps) == 0
    
    result = build_pipeline_with_taps(plan, nodes, logger)
    assert result is not None
    pipeline, stream_taps, save_sinks = result
    
    assert len(stream_taps) == 1
    assert stream_taps[0].tap_id == "preview"
    assert stream_taps[0].attach_point == "n1"
    assert len(save_sinks) == 0


def test_build_with_save_video_and_save_image(logger, tmp_path):
    """Build pipeline with SaveVideo and SaveImage side taps (Stage 8)."""
    nodes = [
        _node("n1", "source", source_type="camera"),
        _node("n2", "stage", stage_id="preprocess_cpu"),
        _node("n3", "stage", stage_id="detect_apriltag_cpu"),
        _node("n4", "stage", stage_id="overlay_cpu"),
        _node("n5", "sink", sink_type="svt_output"),
        _node("sv1", "sink", sink_type="save_video"),
        _node("si1", "sink", sink_type="save_image"),
    ]
    edges = [
        _edge("e1", "n1", "frame", "n2", "frame"),
        _edge("e2", "n2", "frame", "n3", "frame"),
        _edge("e3", "n3", "frame", "n4", "frame"),
        _edge("e4", "n4", "frame", "n5", "frame"),
        _edge("e5", "n2", "frame", "sv1", "frame"),
        _edge("e6", "n4", "frame", "si1", "frame"),
    ]
    plan = compile_graph(nodes, edges)
    plan.node_configs["sv1"] = {"path": str(tmp_path / "out.mp4"), "fps": 30.0}
    plan.node_configs["si1"] = {"path": str(tmp_path / "frame.jpg"), "mode": "overwrite"}
    
    result = build_pipeline_with_taps(plan, nodes, logger)
    assert result is not None
    pipeline, stream_taps, save_sinks = result
    
    assert len(stream_taps) == 1
    assert stream_taps[0].tap_id == "preview"
    assert len(save_sinks) == 2
    sink_ids = {s.sink_id for s in save_sinks}
    assert "sv1" in sink_ids
    assert "si1" in sink_ids
    for s in save_sinks:
        s.close()


def test_build_source_to_stream_tap_only(logger):
    """Build pipeline with only CameraSource → StreamTap (no SVTVisionOutput, no stages)."""
    nodes = [
        _node("n1", "source", source_type="camera"),
        _node("tap1", "sink", sink_type="stream_tap"),
    ]
    edges = [_edge("e1", "n1", "frame", "tap1", "frame")]
    plan = compile_graph(nodes, edges)
    result = build_pipeline_with_taps(plan, nodes, logger)
    assert result is not None
    pipeline, stream_taps, save_sinks = result
    assert len(stream_taps) == 1
    assert stream_taps[0].tap_id == "tap1"
    assert stream_taps[0].attach_point == "n1"
    assert len(save_sinks) == 0
    # Pipeline has no stages but has __source__ taps; process_frame should push raw to tap
    import numpy as np
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    out = pipeline.process_frame(frame)
    assert "raw" in out


def test_build_source_to_save_video_and_stream_tap(logger, tmp_path):
    """Build pipeline CameraSource → SaveVideo + StreamTap (no stages); both get frames, no preview added."""
    import numpy as np
    nodes = [
        _node("n1", "source", source_type="camera"),
        _node("sv1", "sink", sink_type="save_video"),
        _node("tap1", "sink", sink_type="stream_tap"),
    ]
    edges = [
        _edge("e1", "n1", "frame", "sv1", "frame"),
        _edge("e2", "n1", "frame", "tap1", "frame"),
    ]
    plan = compile_graph(nodes, edges)
    plan.node_configs["sv1"] = {"path": str(tmp_path / "out.mp4"), "fps": 30.0}
    result = build_pipeline_with_taps(plan, nodes, logger)
    assert result is not None
    pipeline, stream_taps, save_sinks = result
    assert len(stream_taps) == 1
    assert stream_taps[0].tap_id == "tap1"
    assert stream_taps[0].attach_point == "n1"
    assert len(save_sinks) == 1
    assert save_sinks[0].sink_id == "sv1"
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    pipeline.process_frame(frame)
    pipeline.process_frame(frame)
    for s in save_sinks:
        s.close()
    assert (tmp_path / "out.mp4").exists()
    assert (tmp_path / "out.mp4").stat().st_size > 0


def test_build_source_to_save_video_and_save_image_writes_files(logger, tmp_path):
    """Build pipeline CameraSource → SaveVideo + SaveImage (no stages); process_frame writes files."""
    import numpy as np
    nodes = [
        _node("n1", "source", source_type="camera"),
        _node("sv1", "sink", sink_type="save_video"),
        _node("si1", "sink", sink_type="save_image"),
    ]
    edges = [
        _edge("e1", "n1", "frame", "sv1", "frame"),
        _edge("e2", "n1", "frame", "si1", "frame"),
    ]
    plan = compile_graph(nodes, edges)
    plan.node_configs["sv1"] = {"path": str(tmp_path / "out.mp4"), "fps": 30.0}
    plan.node_configs["si1"] = {"path": str(tmp_path / "frame.jpg"), "mode": "overwrite"}
    result = build_pipeline_with_taps(plan, nodes, logger)
    assert result is not None
    pipeline, stream_taps, save_sinks = result
    assert len(stream_taps) == 1
    assert stream_taps[0].tap_id == "preview"
    assert len(save_sinks) == 2
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    pipeline.process_frame(frame)
    pipeline.process_frame(frame)
    for s in save_sinks:
        s.close()
    assert (tmp_path / "out.mp4").exists()
    assert (tmp_path / "frame.jpg").exists()
    assert (tmp_path / "out.mp4").stat().st_size > 0
    assert (tmp_path / "frame.jpg").stat().st_size > 0
