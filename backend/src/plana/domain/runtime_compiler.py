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


def _nodes_reachable_from(outgoing: Dict[str, List[tuple]], start: str) -> Set[str]:
    """BFS: set of node ids reachable from start."""
    reachable: Set[str] = {start}
    queue: List[str] = [start]
    while queue:
        node = queue.pop(0)
        for (nxt, _, _) in outgoing.get(node, []):
            if nxt not in reachable:
                reachable.add(nxt)
                queue.append(nxt)
    return reachable


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

    # 2. Find source and SVTVisionOutput (or allow StreamTap-only)
    sources = graph.get_sources()
    if not sources:
        raise GraphValidationError("No source node found", ["Graph must have exactly one source"])
    source = sources[0]

    svt_sink = _find_svt_output(graph)
    outgoing = _outgoing_edges(graph)

    if svt_sink is not None:
        # 3a. Main path: source → ... → SVTVisionOutput
        path = _find_path_dfs(graph, source.id, svt_sink.id, outgoing, set(), [])
        if path is None:
            raise GraphValidationError(
                "No path from source to SVTVisionOutput",
                ["SVTVisionOutput must be reachable from the source node"],
            )
        main_path = path
    else:
        # 3b. No SVTVisionOutput: allow graph if source (possibly via stages) feeds a side tap (e.g. CameraSource → Preprocess → StreamTap)
        reachable = _nodes_reachable_from(outgoing, source.id)
        side_tap_edges = [
            e for e in graph.edges
            if e.source_node in reachable
            and graph.get_node(e.target_node) is not None
            and getattr(graph.get_node(e.target_node), "sink_type", None) in SIDE_TAP_SINK_TYPES
        ]
        if not side_tap_edges:
            raise GraphValidationError(
                "No SVTVisionOutput sink found",
                ["Graph must have an SVTVisionOutput sink or a path from the source to at least one StreamTap/SaveVideo/SaveImage"],
            )
        # Main path = longest path from source to any node that feeds a side tap
        attach_points = {e.source_node for e in side_tap_edges}
        best_path: List[str] = [source.id]
        for ap in attach_points:
            p = _find_path_dfs(graph, source.id, ap, outgoing, set(), [])
            if p is not None and len(p) > len(best_path):
                best_path = p
        main_path = best_path

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

    # 5. Collect node configs for all nodes (include every node so pipeline_builder can apply settings)
    node_configs: Dict[str, Dict[str, Any]] = {}
    for n in graph.nodes:
        node_configs[n.id] = dict(n.config) if n.config is not None else {}

    return ExecutionPlan(
        main_path=main_path,
        side_taps=side_taps,
        node_configs=node_configs,
    )
