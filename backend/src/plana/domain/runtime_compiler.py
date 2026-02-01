"""
Runtime Compiler - Stage 5.
Compiles a validated pipeline graph into an execution plan:
- Main path: Source → ... → SVTVisionOutput
- Side taps: StreamTap, SaveVideo, SaveImage attached to main path nodes.
"""

from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field

from .graph_model import PipelineGraph, GraphNode, GraphEdge, validate_graph, GraphValidationError


@dataclass
class SideTap:
    """A side tap (StreamTap, SaveVideo, SaveImage) attached to a main path node."""

    node_id: str
    sink_type: str  # stream_tap | save_video | save_image
    attach_point: str  # main path node_id whose output feeds this sink
    source_port: str
    target_port: str


@dataclass
class ExecutionPlan:
    """Compiled execution plan: main path + side taps."""

    main_path: List[str]  # ordered node_ids from source to SVTVisionOutput
    side_taps: List[SideTap] = field(default_factory=list)
    node_configs: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "main_path": self.main_path,
            "side_taps": [
                {
                    "node_id": st.node_id,
                    "sink_type": st.sink_type,
                    "attach_point": st.attach_point,
                    "source_port": st.source_port,
                    "target_port": st.target_port,
                }
                for st in self.side_taps
            ],
            "node_configs": self.node_configs,
        }


# Sink types that are "side taps" (not the primary SVTVisionOutput)
SIDE_TAP_SINK_TYPES = {"stream_tap", "save_video", "save_image"}


def _outgoing_edges(graph: PipelineGraph) -> Dict[str, List[tuple]]:
    """Map node_id -> [(target_node_id, source_port, target_port), ...]."""
    out: Dict[str, List[tuple]] = {n.id: [] for n in graph.nodes}
    for e in graph.edges:
        if e.source_node in out:
            out[e.source_node].append((e.target_node, e.source_port, e.target_port))
    return out


def _incoming_edges(graph: PipelineGraph) -> Dict[str, List[tuple]]:
    """Map node_id -> [(source_node_id, source_port, target_port), ...]."""
    inc: Dict[str, List[tuple]] = {n.id: [] for n in graph.nodes}
    for e in graph.edges:
        if e.target_node in inc:
            inc[e.target_node].append((e.source_node, e.source_port, e.target_port))
    return inc


def _find_svt_output(graph: PipelineGraph) -> Optional[GraphNode]:
    """Find the SVTVisionOutput sink (required terminal)."""
    for n in graph.get_sinks():
        if n.sink_type == "svt_output":
            return n
    return None


def _find_path_dfs(
    graph: PipelineGraph,
    start: str,
    target: str,
    outgoing: Dict[str, List[tuple]],
    visited: Set[str],
    path: List[str],
) -> Optional[List[str]]:
    """DFS to find path from start to target. Returns path if found."""
    if start == target:
        return path + [start]
    if start in visited:
        return None
    visited.add(start)
    for (nxt, _, _) in outgoing.get(start, []):
        result = _find_path_dfs(graph, nxt, target, outgoing, visited.copy(), path + [start])
        if result is not None:
            return result
    return None


def compile_graph(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> ExecutionPlan:
    """
    Compile a pipeline graph into an execution plan.
    1. Validate graph (DAG, single-source, single-input-per-port)
    2. Extract main path: Source → ... → SVTVisionOutput
    3. Extract side taps: StreamTap, SaveVideo, SaveImage

    Raises GraphValidationError if graph is invalid.
    """
    # Build PipelineGraph from raw dicts
    graph_nodes = [
        GraphNode(
            id=n.get("id", ""),
            type=n.get("type", "stage"),
            stage_id=n.get("stage_id"),
            source_type=n.get("source_type"),
            sink_type=n.get("sink_type"),
            config=n.get("config"),
            ports=n.get("ports"),
        )
        for n in nodes
    ]
    graph_edges = [
        GraphEdge(
            id=e.get("id", ""),
            source_node=e.get("source_node", ""),
            source_port=e.get("source_port", ""),
            target_node=e.get("target_node", ""),
            target_port=e.get("target_port", ""),
        )
        for e in edges
    ]
    graph = PipelineGraph(nodes=graph_nodes, edges=graph_edges)

    # 1. Validate
    validate_graph(graph)

    # 2. Find source and SVTVisionOutput
    sources = graph.get_sources()
    if not sources:
        raise GraphValidationError("No source node found", ["Graph must have exactly one source"])
    source = sources[0]

    svt_sink = _find_svt_output(graph)
    if svt_sink is None:
        raise GraphValidationError(
            "No SVTVisionOutput sink found",
            ["Graph must have an SVTVisionOutput sink (required terminal)"],
        )

    # 3. Find main path (source → ... → svt_output)
    outgoing = _outgoing_edges(graph)
    path = _find_path_dfs(graph, source.id, svt_sink.id, outgoing, set(), [])
    if path is None:
        raise GraphValidationError(
            "No path from source to SVTVisionOutput",
            ["SVTVisionOutput must be reachable from the source node"],
        )
    main_path = path

    main_path_set: Set[str] = set(main_path)

    # 4. Extract side taps
    side_taps: List[SideTap] = []
    for e in graph.edges:
        target_node = graph.get_node(e.target_node)
        if target_node is None:
            continue
        sink_type = getattr(target_node, "sink_type", None) or target_node.sink_type
        if sink_type not in SIDE_TAP_SINK_TYPES:
            continue
        # This edge feeds a side-tap sink. Attach point is the source (must be on main path)
        if e.source_node in main_path_set:
            side_taps.append(
                SideTap(
                    node_id=e.target_node,
                    sink_type=sink_type,
                    attach_point=e.source_node,
                    source_port=e.source_port,
                    target_port=e.target_port,
                )
            )

    # 5. Collect node configs for all nodes
    node_configs: Dict[str, Dict[str, Any]] = {}
    for n in graph.nodes:
        if n.config is not None:
            node_configs[n.id] = dict(n.config)

    return ExecutionPlan(
        main_path=main_path,
        side_taps=side_taps,
        node_configs=node_configs,
    )
