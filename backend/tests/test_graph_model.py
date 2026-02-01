"""Unit tests for Graph Model - Stage 1."""

import pytest
from plana.domain.graph_model import (
    PipelineGraph,
    GraphNode,
    GraphEdge,
    validate_dag,
    validate_single_source,
    validate_single_input_per_port,
    validate_graph,
    GraphValidationError,
)


def _make_graph(nodes: list, edges: list) -> PipelineGraph:
    """Helper to build graph from simple specs."""
    nlist = []
    for n in nodes:
        if isinstance(n, tuple):
            nid, ntype = n[0], n[1]
            nlist.append(GraphNode(id=nid, type=ntype))
        else:
            nlist.append(n)
    elist = []
    for e in edges:
        if isinstance(e, tuple):
            eid, src, srcp, tgt, tgtp = e[0], e[1], e[2], e[3], e[4]
            elist.append(GraphEdge(id=eid, source_node=src, source_port=srcp, target_node=tgt, target_port=tgtp))
        else:
            elist.append(e)
    return PipelineGraph(nodes=nlist, edges=elist)


def test_valid_dag_passes():
    """Valid DAG (linear chain) passes DAG validation."""
    g = _make_graph(
        [("n1", "source"), ("n2", "stage"), ("n3", "sink")],
        [("e1", "n1", "out", "n2", "in"), ("e2", "n2", "out", "n3", "in")],
    )
    ok, errs = validate_dag(g)
    assert ok is True
    assert len(errs) == 0


def test_cycle_detected():
    """Graph with cycle fails DAG validation."""
    g = _make_graph(
        [("n1", "source"), ("n2", "stage"), ("n3", "stage")],
        [
            ("e1", "n1", "out", "n2", "in"),
            ("e2", "n2", "out", "n3", "in"),
            ("e3", "n3", "out", "n2", "in"),  # cycle n2->n3->n2
        ],
    )
    ok, errs = validate_dag(g)
    assert ok is False
    assert len(errs) > 0
    assert "cycle" in errs[0].lower()


def test_single_source_valid():
    """Graph with exactly one source and all reachable passes."""
    g = _make_graph(
        [("n1", "source"), ("n2", "stage"), ("n3", "sink")],
        [("e1", "n1", "out", "n2", "in"), ("e2", "n2", "out", "n3", "in")],
    )
    ok, errs = validate_single_source(g)
    assert ok is True
    assert len(errs) == 0


def test_no_source_fails():
    """Graph with no source fails single-source validation."""
    g = _make_graph(
        [("n1", "stage"), ("n2", "sink")],
        [("e1", "n1", "out", "n2", "in")],
    )
    ok, errs = validate_single_source(g)
    assert ok is False
    assert "source" in errs[0].lower()


def test_multiple_sources_fails():
    """Graph with multiple sources fails single-source validation."""
    g = _make_graph(
        [("n1", "source"), ("n2", "source"), ("n3", "sink")],
        [("e1", "n1", "out", "n3", "in")],
    )
    ok, errs = validate_single_source(g)
    assert ok is False
    assert "one source" in errs[0].lower() or "exactly" in errs[0].lower()


def test_unreachable_node_fails():
    """Graph with unreachable node fails single-source validation."""
    g = _make_graph(
        [("n1", "source"), ("n2", "stage"), ("n3", "sink")],  # n3 not connected
        [("e1", "n1", "out", "n2", "in")],
    )
    ok, errs = validate_single_source(g)
    assert ok is False
    assert "unreachable" in errs[0].lower() or "n3" in errs[0]


def test_single_input_per_port_valid():
    """Graph with one input per port passes."""
    g = _make_graph(
        [("n1", "source"), ("n2", "stage"), ("n3", "sink")],
        [("e1", "n1", "out", "n2", "in"), ("e2", "n2", "out", "n3", "in")],
    )
    ok, errs = validate_single_input_per_port(g)
    assert ok is True


def test_multiple_inputs_same_port_fails():
    """Graph with two edges to same input port fails."""
    g = _make_graph(
        [("n1", "source"), ("n2", "source"), ("n3", "stage")],
        [
            ("e1", "n1", "out", "n3", "in"),
            ("e2", "n2", "out", "n3", "in"),  # two inputs to n3.in
        ],
    )
    ok, errs = validate_single_input_per_port(g)
    assert ok is False
    assert "2 inputs" in errs[0] or "max 1" in errs[0]


def test_validate_graph_valid_passes():
    """Valid graph passes full validation."""
    g = _make_graph(
        [("n1", "source"), ("n2", "stage"), ("n3", "sink")],
        [("e1", "n1", "out", "n2", "in"), ("e2", "n2", "out", "n3", "in")],
    )
    validate_graph(g)  # no exception


def test_validate_graph_invalid_raises():
    """Invalid graph raises GraphValidationError."""
    g = _make_graph(
        [("n1", "stage"), ("n2", "sink")],  # no source
        [("e1", "n1", "out", "n2", "in")],
    )
    with pytest.raises(GraphValidationError) as exc_info:
        validate_graph(g)
    assert len(exc_info.value.errors) > 0
