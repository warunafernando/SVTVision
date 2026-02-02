"""Unit tests for Runtime Compiler - Stage 5."""

import pytest
import sys
from pathlib import Path

backend_src = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(backend_src))

from plana.domain.runtime_compiler import compile_graph, ExecutionPlan, SideTap
from plana.domain.graph_model import GraphValidationError


def _node(id_: str, type_: str, **kw):
    return {"id": id_, "type": type_, **kw}


def _edge(id_: str, src: str, tgt: str, src_port="frame", tgt_port="frame"):
    return {
        "id": id_,
        "source_node": src,
        "source_port": src_port,
        "target_node": tgt,
        "target_port": tgt_port,
    }


def test_compile_simple_linear():
    """Simple linear: source → stage → svt_output."""
    nodes = [
        _node("n1", "source", source_type="camera"),
        _node("n2", "stage", stage_id="preprocess_cpu"),
        _node("n3", "sink", sink_type="svt_output"),
    ]
    edges = [
        _edge("e1", "n1", "n2"),
        _edge("e2", "n2", "n3"),
    ]
    plan = compile_graph(nodes, edges)
    assert plan.main_path == ["n1", "n2", "n3"]
    assert plan.side_taps == []


def test_compile_with_side_tap():
    """Main path + StreamTap side tap."""
    nodes = [
        _node("n1", "source", source_type="camera"),
        _node("n2", "stage", stage_id="preprocess_cpu"),
        _node("n3", "stage", stage_id="detect_apriltag_cpu"),
        _node("n4", "sink", sink_type="svt_output"),
        _node("n5", "sink", sink_type="stream_tap"),
    ]
    edges = [
        _edge("e1", "n1", "n2"),
        _edge("e2", "n2", "n3"),
        _edge("e3", "n3", "n4"),
        _edge("e4", "n2", "n5"),  # side tap from preprocess
    ]
    plan = compile_graph(nodes, edges)
    assert plan.main_path == ["n1", "n2", "n3", "n4"]
    assert len(plan.side_taps) == 1
    assert plan.side_taps[0].node_id == "n5"
    assert plan.side_taps[0].sink_type == "stream_tap"
    assert plan.side_taps[0].attach_point == "n2"


def test_compile_requires_svt_output():
    """Graph without SVTVisionOutput and without any side tap from source raises."""
    nodes = [
        _node("n1", "source", source_type="camera"),
        _node("n2", "sink", sink_type="stream_tap"),
    ]
    edges = []  # no edge: source not connected to stream_tap, so no side_taps_from_source
    with pytest.raises(GraphValidationError) as exc_info:
        compile_graph(nodes, edges)
    assert exc_info.value.errors


def test_compile_source_to_stream_tap_only():
    """Graph with only CameraSource → StreamTap compiles (no SVTVisionOutput required)."""
    nodes = [
        _node("n1", "source", source_type="camera"),
        _node("n2", "sink", sink_type="stream_tap"),
    ]
    edges = [_edge("e1", "n1", "n2")]
    plan = compile_graph(nodes, edges)
    assert plan.main_path == ["n1"]
    assert len(plan.side_taps) == 1
    assert plan.side_taps[0].node_id == "n2"
    assert plan.side_taps[0].sink_type == "stream_tap"
    assert plan.side_taps[0].attach_point == "n1"


def test_compile_requires_single_source():
    """Graph with two sources raises."""
    nodes = [
        _node("n1", "source", source_type="camera"),
        _node("n2", "source", source_type="video_file"),
        _node("n3", "sink", sink_type="svt_output"),
    ]
    edges = [
        _edge("e1", "n1", "n3"),
        _edge("e2", "n2", "n3"),
    ]
    with pytest.raises(GraphValidationError):
        compile_graph(nodes, edges)


def test_compile_multiple_side_taps():
    """Multiple side taps (StreamTap, SaveVideo) from different points."""
    nodes = [
        _node("n1", "source", source_type="camera"),
        _node("n2", "stage", stage_id="preprocess_cpu"),
        _node("n3", "stage", stage_id="detect_apriltag_cpu"),
        _node("n4", "sink", sink_type="svt_output"),
        _node("n5", "sink", sink_type="stream_tap"),
        _node("n6", "sink", sink_type="save_video"),
    ]
    edges = [
        _edge("e1", "n1", "n2"),
        _edge("e2", "n2", "n3"),
        _edge("e3", "n3", "n4"),
        _edge("e4", "n2", "n5"),
        _edge("e5", "n3", "n6"),
    ]
    plan = compile_graph(nodes, edges)
    assert plan.main_path == ["n1", "n2", "n3", "n4"]
    assert len(plan.side_taps) == 2
    sink_ids = {st.node_id for st in plan.side_taps}
    assert sink_ids == {"n5", "n6"}
    attach_points = {st.node_id: st.attach_point for st in plan.side_taps}
    assert attach_points["n5"] == "n2"
    assert attach_points["n6"] == "n3"


def test_compile_plan_to_dict():
    """ExecutionPlan.to_dict returns serializable structure."""
    plan = ExecutionPlan(
        main_path=["n1", "n2", "n3"],
        side_taps=[
            SideTap(node_id="n5", sink_type="stream_tap", attach_point="n2", source_port="frame", target_port="frame"),
        ],
        node_configs={"n2": {"blur_kernel_size": 5}},
    )
    d = plan.to_dict()
    assert d["main_path"] == ["n1", "n2", "n3"]
    assert len(d["side_taps"]) == 1
    assert d["side_taps"][0]["node_id"] == "n5"
    assert d["side_taps"][0]["attach_point"] == "n2"
    assert d["node_configs"]["n2"]["blur_kernel_size"] == 5
