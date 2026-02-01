"""Unit tests for Pipeline Builder - Stage 6."""

import pytest
import sys
from pathlib import Path

backend_src = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(backend_src))

from plana.domain.pipeline_builder import build_pipeline_from_plan_with_nodes
from plana.domain.runtime_compiler import compile_graph
from plana.services.logging_service import LoggingService


def _node(id_: str, type_: str, **kw):
    return {"id": id_, "type": type_, **kw}


def _edge(id_: str, src: str, tgt: str):
    return {"id": id_, "source_node": src, "source_port": "frame", "target_node": tgt, "target_port": "frame"}


@pytest.fixture
def logger():
    return LoggingService()


def test_build_apriltag_pipeline(logger):
    """Build pipeline from source → preprocess → detect → overlay → svt_output."""
    nodes = [
        _node("n1", "source", source_type="camera"),
        _node("n2", "stage", stage_id="preprocess_cpu"),
        _node("n3", "stage", stage_id="detect_apriltag_cpu"),
        _node("n4", "stage", stage_id="overlay_cpu"),
        _node("n5", "sink", sink_type="svt_output"),
    ]
    edges = [
        _edge("e1", "n1", "n2"),
        _edge("e2", "n2", "n3"),
        _edge("e3", "n3", "n4"),
        _edge("e4", "n4", "n5"),
    ]
    plan = compile_graph(nodes, edges)
    pipeline = build_pipeline_from_plan_with_nodes(plan, nodes, logger)
    assert pipeline is not None
    assert len(pipeline._stages) == 3  # preprocess, detect, overlay
    assert pipeline._stages[0].name == "preprocess"
    assert pipeline._stages[1].name == "detect"
    assert pipeline._stages[2].name == "detect_overlay"


def test_build_preprocess_only(logger):
    """Build pipeline with just preprocess → svt_output (minimal)."""
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
    pipeline = build_pipeline_from_plan_with_nodes(plan, nodes, logger)
    assert pipeline is not None
    assert len(pipeline._stages) == 1
    assert pipeline._stages[0].name == "preprocess"


def test_build_with_config(logger):
    """Build pipeline with node config applied to preprocess."""
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
    plan.node_configs["n2"] = {"blur_kernel_size": 5, "adaptive_block_size": 21}
    pipeline = build_pipeline_from_plan_with_nodes(plan, nodes, logger)
    assert pipeline is not None
    assert len(pipeline._stages) == 1
