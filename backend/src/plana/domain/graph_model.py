"""
Graph Model for Vision Pipeline - Stage 1.

Data structures and validation:
- DAG (directed acyclic graph) validation
- Single-source validation (exactly one source, all reachable)
"""

from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field


@dataclass
class GraphNode:
    """A node in the pipeline graph."""
    id: str
    type: str  # "source" | "stage" | "sink"
    stage_id: Optional[str] = None
    source_type: Optional[str] = None
    sink_type: Optional[str] = None
    config: Optional[Dict] = None
    ports: Optional[Dict] = None


@dataclass
class GraphEdge:
    """An edge (wire) between nodes."""
    id: str
    source_node: str
    source_port: str
    target_node: str
    target_port: str


@dataclass
class PipelineGraph:
    """Pipeline graph: nodes and edges."""
    nodes: List[GraphNode] = field(default_factory=list)
    edges: List[GraphEdge] = field(default_factory=list)
    layout: Optional[Dict[str, Dict[str, float]]] = None
    name: Optional[str] = None

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        """Get node by id."""
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def get_sources(self) -> List[GraphNode]:
        """Get all source nodes."""
        return [n for n in self.nodes if n.type == "source"]

    def get_sinks(self) -> List[GraphNode]:
        """Get all sink nodes."""
        return [n for n in self.nodes if n.type == "sink"]

    def _outgoing(self) -> Dict[str, List[str]]:
        """Map node_id -> list of target node_ids (outgoing edges)."""
        out: Dict[str, List[str]] = {n.id: [] for n in self.nodes}
        for e in self.edges:
            if e.source_node in out:
                out[e.source_node].append(e.target_node)
        return out

    def _incoming(self) -> Dict[str, List[str]]:
        """Map node_id -> list of source node_ids (incoming edges)."""
        inc: Dict[str, List[str]] = {n.id: [] for n in self.nodes}
        for e in self.edges:
            if e.target_node in inc:
                inc[e.target_node].append(e.source_node)
        return inc


class GraphValidationError(Exception):
    """Raised when graph validation fails."""
    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or [message]


def validate_dag(graph: PipelineGraph) -> Tuple[bool, List[str]]:
    """
    Validate that the graph is a DAG (no cycles).
    Returns (valid, list of error messages).
    """
    errors: List[str] = []
    node_ids = {n.id for n in graph.nodes}
    outgoing = graph._outgoing()

    # DFS to detect cycles
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {nid: WHITE for nid in node_ids}
    path: List[str] = []

    def dfs(nid: str) -> bool:
        if color[nid] == GRAY:
            errors.append(f"Cycle detected involving node {nid}")
            return False
        if color[nid] == BLACK:
            return True
        color[nid] = GRAY
        path.append(nid)
        for target in outgoing.get(nid, []):
            if target in node_ids and not dfs(target):
                return False
        path.pop()
        color[nid] = BLACK
        return True

    for nid in node_ids:
        if color[nid] == WHITE and not dfs(nid):
            return False, errors

    return True, []


def validate_single_source(graph: PipelineGraph) -> Tuple[bool, List[str]]:
    """
    Validate single-source: exactly one source, all nodes reachable from it.
    Returns (valid, list of error messages).
    """
    errors: List[str] = []
    sources = graph.get_sources()

    if len(sources) == 0:
        errors.append("Graph must have exactly one source node (CameraSource, VideoFileSource, or ImageFileSource)")
        return False, errors
    if len(sources) > 1:
        errors.append(f"Graph must have exactly one source; found {len(sources)}: {[s.id for s in sources]}")
        return False, errors

    # BFS from source to check reachability
    node_ids = {n.id for n in graph.nodes}
    outgoing = graph._outgoing()
    reachable: Set[str] = set()
    queue = [sources[0].id]
    while queue:
        nid = queue.pop(0)
        if nid in reachable:
            continue
        reachable.add(nid)
        for target in outgoing.get(nid, []):
            if target in node_ids and target not in reachable:
                queue.append(target)

    unreachable = node_ids - reachable
    if unreachable:
        errors.append(f"Unreachable nodes from source: {unreachable}")
        return False, errors

    return True, []


def validate_single_input_per_port(graph: PipelineGraph) -> Tuple[bool, List[str]]:
    """
    Validate that each input port has at most one incoming edge.
    Returns (valid, list of error messages).
    """
    errors: List[str] = []
    port_inputs: Dict[Tuple[str, str], int] = {}  # (node_id, port) -> count

    for e in graph.edges:
        key = (e.target_node, e.target_port)
        port_inputs[key] = port_inputs.get(key, 0) + 1

    for (node_id, port), count in port_inputs.items():
        if count > 1:
            errors.append(f"Node {node_id} input port '{port}' has {count} inputs (max 1)")
    return (len(errors) == 0, errors)


def validate_graph(graph: PipelineGraph) -> None:
    """
    Full graph validation: DAG + single-source + single-input-per-port.
    Raises GraphValidationError if invalid.
    """
    all_errors: List[str] = []

    ok, errs = validate_dag(graph)
    if not ok:
        all_errors.extend(errs)

    ok, errs = validate_single_source(graph)
    if not ok:
        all_errors.extend(errs)

    ok, errs = validate_single_input_per_port(graph)
    if not ok:
        all_errors.extend(errs)

    if all_errors:
        raise GraphValidationError("Graph validation failed", all_errors)
