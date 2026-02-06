/**
 * Pipeline Canvas - Drag/drop nodes, move nodes, delete, wire connections
 * StreamTap nodes show live video when pipeline is running.
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { VPNode, VPEdge } from '../../types';
import { getWsBaseUrl } from '../../utils/config';
import { fetchStreamTaps } from '../../utils/pipelineApi';
import { fetchStageRuntimes } from '../../utils/vpApi';
import { getDefaultConfigForAlgorithm } from '../../utils/stageAlgorithmSchemas';
import '../../styles/vp/PipelineCanvas.css';

function genId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 9)}`;
}

interface PipelineCanvasProps {
  nodes: VPNode[];
  edges: VPEdge[];
  layout: Record<string, { x: number; y: number }>;
  selectedNodeId: string | null;
  runningInstanceIds?: string[];
  onGraphChange: (nodes: VPNode[], edges: VPEdge[], layout: Record<string, { x: number; y: number }>) => void;
  onNodeSelect: (nodeId: string | null) => void;
}

const NODE_WIDTH = 105;
const NODE_HEIGHT = 42;
const STREAMTAP_VIDEO_WIDTH = 160;
const STREAMTAP_VIDEO_HEIGHT = 120;
const PORT_SIZE = 11;
/** Distance for Bezier control points so wire leaves/arrives at 90° to port surface */
const EDGE_NORMAL_OFFSET = 48;

/** Inline video for a StreamTap node: connects to tap WebSocket and displays frames. */
const StreamTapNodeVideo: React.FC<{ instanceId: string; tapId: string }> = ({ instanceId, tapId }) => {
  const [frameSrc, setFrameSrc] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    const wsUrl = `${getWsBaseUrl()}/ws/vp/tap/${instanceId}/${encodeURIComponent(tapId)}`;
    const ws = new WebSocket(wsUrl);
    ws.onopen = () => setConnected(true);
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'frame' && data.data) {
          setFrameSrc(`data:image/jpeg;base64,${data.data}`);
        }
      } catch {
        // ignore
      }
    };
    ws.onclose = () => setConnected(false);
    return () => ws.close();
  }, [instanceId, tapId]);
  return (
    <div className="vp-node-streamtap-video">
      {frameSrc ? (
        <img src={frameSrc} alt="StreamTap" />
      ) : (
        <span className="vp-node-streamtap-waiting">{connected ? 'Waiting for frames…' : 'Connecting…'}</span>
      )}
    </div>
  );
};

const PipelineCanvas: React.FC<PipelineCanvasProps> = ({
  nodes,
  edges,
  layout,
  selectedNodeId,
  runningInstanceIds = [],
  onGraphChange,
  onNodeSelect,
}) => {
  const [wireFrom, setWireFrom] = useState<{ nodeId: string; port: string } | null>(null);
  const [dragNode, setDragNode] = useState<{ nodeId: string; startX: number; startY: number } | null>(null);
  const [taps, setTaps] = useState<Record<string, { tap_id: string; attach_point: string }>>({});
  const [stageRuntimes, setStageRuntimes] = useState<Record<string, 'gpu' | 'cpu'>>({});
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchStageRuntimes().then(setStageRuntimes).catch(() => setStageRuntimes({}));
  }, []);

  useEffect(() => {
    if (runningInstanceIds.length === 0) {
      setTaps({});
      return;
    }
    fetchStreamTaps(runningInstanceIds[0])
      .then(setTaps)
      .catch((e) => {
        setTaps({});
        console.warn('[Vision Pipeline] Canvas: failed to load taps for instance', runningInstanceIds[0], e);
      });
  }, [runningInstanceIds.join(',')]);

  const updateGraph = useCallback(
    (newNodes: VPNode[], newEdges: VPEdge[], newLayout?: Record<string, { x: number; y: number }>) => {
      onGraphChange(newNodes, newEdges, newLayout ?? layout);
    },
    [onGraphChange, layout]
  );

  const screenToSvg = useCallback((clientX: number, clientY: number) => {
    const svg = svgRef.current;
    if (svg) {
      const ctm = svg.getScreenCTM();
      if (ctm) {
        const pt = svg.createSVGPoint();
        pt.x = clientX;
        pt.y = clientY;
        const svgPt = pt.matrixTransform(ctm.inverse());
        return { x: svgPt.x, y: svgPt.y };
      }
    }
    const dropzone = containerRef.current || svg?.closest('.vp-canvas-dropzone') as HTMLElement;
    if (dropzone) {
      const rect = dropzone.getBoundingClientRect();
      return { x: clientX - rect.left + (dropzone.scrollLeft || 0), y: clientY - rect.top + (dropzone.scrollTop || 0) };
    }
    return { x: clientX, y: clientY };
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
      const raw = e.dataTransfer?.getData('application/json');
      if (!raw) return;
      try {
        const data = JSON.parse(raw);
        const nodeId = genId('n');
        const defaults = (data.type === 'stage' && data.stage_id)
          ? getDefaultConfigForAlgorithm(data.stage_id)
          : {};
        const node: VPNode = {
          id: nodeId,
          type: data.type || 'stage',
          stage_id: data.stage_id,
          source_type: data.source_type,
          sink_type: data.sink_type,
          name: data.name || data.paletteLabel,
          ports: data.ports || { inputs: [{ name: 'in', type: 'frame' }], outputs: [{ name: 'out', type: 'frame' }] },
          config: Object.keys(defaults).length ? defaults : undefined,
        };
        const svgPt = screenToSvg(e.clientX, e.clientY);
        const x = Math.max(0, svgPt.x - NODE_WIDTH / 2);
        const y = Math.max(0, svgPt.y - NODE_HEIGHT / 2);
        const newLayout = { ...layout, [nodeId]: { x, y } };
        const next = [...nodes, node];
        updateGraph(next, edges, newLayout);
        onNodeSelect(nodeId);
      } catch {
        // ignore parse errors
      }
    },
    [nodes, edges, layout, updateGraph, screenToSvg, onNodeSelect]
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
  }, []);

  const getNodeLabel = (node: VPNode): string => {
    return node.name || node.stage_id || node.source_type || node.sink_type || node.type || node.id;
  };

  const isStreamTapNode = (node: VPNode): boolean =>
    node.type === 'sink' && node.sink_type === 'stream_tap';

  const isStreamTapWithVideo = (node: VPNode): boolean =>
    isStreamTapNode(node) && runningInstanceIds.length > 0;

  const getNodeWidth = (node: VPNode): number =>
    isStreamTapNode(node) ? STREAMTAP_VIDEO_WIDTH : NODE_WIDTH;
  const getNodeHeight = (node: VPNode): number =>
    isStreamTapNode(node) ? STREAMTAP_VIDEO_HEIGHT : NODE_HEIGHT;

  const handleNodeMouseDown = (nodeId: string) => (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    const pos = layout[nodeId] || { x: 0, y: 0 };
    const svgPt = screenToSvg(e.clientX, e.clientY);
    onNodeSelect(nodeId);
    setDragNode({ nodeId, startX: svgPt.x - pos.x, startY: svgPt.y - pos.y });
  };

  const handleNodeMouseUp = () => {
    setDragNode(null);
  };

  const handleNodeMouseMove = useCallback(
    (e: React.MouseEvent) => {
      if (!dragNode) return;
      const svgPt = screenToSvg(e.clientX, e.clientY);
      const x = Math.max(0, svgPt.x - dragNode.startX);
      const y = Math.max(0, svgPt.y - dragNode.startY);
      const newLayout = { ...layout, [dragNode.nodeId]: { x, y } };
      onGraphChange(nodes, edges, newLayout);
    },
    [dragNode, screenToSvg, layout, nodes, edges, onGraphChange]
  );

  useEffect(() => {
    if (!dragNode) return;
    const onMove = (e: MouseEvent) => {
      const svgPt = screenToSvg(e.clientX, e.clientY);
      const x = Math.max(0, svgPt.x - dragNode.startX);
      const y = Math.max(0, svgPt.y - dragNode.startY);
      const newLayout = { ...layout, [dragNode.nodeId]: { x, y } };
      onGraphChange(nodes, edges, newLayout);
    };
    const onUp = () => setDragNode(null);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [dragNode, screenToSvg, nodes, edges, layout, onGraphChange]);

  const handleDeleteNode = useCallback(
    (nodeId: string) => (e: React.MouseEvent) => {
      e.stopPropagation();
      const newNodes = nodes.filter((n) => n.id !== nodeId);
      const newEdges = edges.filter((edge) => edge.source_node !== nodeId && edge.target_node !== nodeId);
      const newLayout = { ...layout };
      delete newLayout[nodeId];
      if (selectedNodeId === nodeId) onNodeSelect(null);
      updateGraph(newNodes, newEdges, newLayout);
    },
    [selectedNodeId, nodes, edges, layout, updateGraph]
  );

  const handleOutputPortClick = (nodeId: string, port: string) => (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    setWireFrom({ nodeId, port });
  };

  const handleInputPortClick = (nodeId: string, port: string) => (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (!wireFrom) return;
    if (wireFrom.nodeId === nodeId && wireFrom.port === port) {
      setWireFrom(null);
      return;
    }
    const filtered = edges.filter(
      (edge) => !(edge.target_node === nodeId && edge.target_port === port)
    );
    const newEdge: VPEdge = {
      id: genId('e'),
      source_node: wireFrom.nodeId,
      source_port: wireFrom.port,
      target_node: nodeId,
      target_port: port,
    };
    const next = [...filtered, newEdge];
    updateGraph(nodes, next, layout);
    setWireFrom(null);
  };

  const deleteSelectedNode = useCallback(() => {
    if (!selectedNodeId) return;
    const nodeId = selectedNodeId;
    const newNodes = nodes.filter((n) => n.id !== nodeId);
    const newEdges = edges.filter((e) => e.source_node !== nodeId && e.target_node !== nodeId);
    const newLayout = { ...layout };
    delete newLayout[nodeId];
    onNodeSelect(null);
    updateGraph(newNodes, newEdges, newLayout);
  }, [selectedNodeId, nodes, edges, layout, updateGraph, onNodeSelect]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Delete' && selectedNodeId) {
        e.preventDefault();
        deleteSelectedNode();
      }
      if (e.key === 'Escape') {
        onNodeSelect(null);
        setWireFrom(null);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [selectedNodeId, deleteSelectedNode]);

  const getPos = (nodeId: string) => layout[nodeId] || { x: 0, y: 0 };

  /** Source and stage: ports on top/bottom middle. Sink: ports on left/right (unchanged). */
  const isSourceOrStage = (n: VPNode) => n.type === 'source' || n.type === 'stage';

  const getPortCoords = (nodeId: string, isOutput: boolean, portIndex: number, node?: VPNode) => {
    const pos = getPos(nodeId);
    const n = node ?? nodes.find((n) => n.id === nodeId);
    const w = n ? getNodeWidth(n) : NODE_WIDTH;
    const h = n ? getNodeHeight(n) : NODE_HEIGHT;
    const ports = isOutput ? (n?.ports?.outputs || []) : (n?.ports?.inputs || []);
    const count = Math.max(1, ports.length);
    if (n && isSourceOrStage(n)) {
      const cx = pos.x + w / 2;
      const cy = isOutput
        ? pos.y + h - PORT_SIZE / 2 - (count - 1 - portIndex) * PORT_SIZE
        : pos.y + PORT_SIZE / 2 + portIndex * PORT_SIZE;
      return { cx, cy };
    }
    const cy = pos.y + h / 2 - (count * PORT_SIZE) / 2 + portIndex * PORT_SIZE + PORT_SIZE / 2;
    const cx = isOutput ? pos.x + w : pos.x;
    return { cx, cy };
  };

  /** Outward normal (dx, dy) from the node at this port: wire leaves output along this, arrives at input from opposite. */
  const getPortNormal = (node: VPNode, isOutput: boolean, _portIndex: number): { dx: number; dy: number } => {
    if (isSourceOrStage(node)) {
      return isOutput ? { dx: 0, dy: 1 } : { dx: 0, dy: -1 }; // output bottom: down; input top: up
    }
    return isOutput ? { dx: 1, dy: 0 } : { dx: -1, dy: 0 };   // sink: output right, input left
  };

  /** Port position relative to node (0,0) for drawing. Source/stage: top/bottom middle; sink: left/right. */
  const getPortPosRel = (node: VPNode, isOutput: boolean, portIndex: number) => {
    const w = getNodeWidth(node);
    const h = getNodeHeight(node);
    const inputs = node.ports?.inputs || [];
    const outputs = node.ports?.outputs || [];
    const count = isOutput ? Math.max(1, outputs.length) : Math.max(1, inputs.length);
    if (isSourceOrStage(node)) {
      const cx = w / 2;
      const cy = isOutput
        ? h - PORT_SIZE / 2 - (count - 1 - portIndex) * PORT_SIZE
        : PORT_SIZE / 2 + portIndex * PORT_SIZE;
      return { cx, cy };
    }
    const cy = h / 2 - (count * PORT_SIZE) / 2 + portIndex * PORT_SIZE + PORT_SIZE / 2;
    const cx = isOutput ? w : 0;
    return { cx, cy };
  };

  return (
    <div className="vp-canvas">
      <div className="vp-canvas-toolbar">
        <span className="vp-canvas-hint">
          {wireFrom ? 'Click input port to connect' : selectedNodeId ? 'Press Delete to remove • Drag to move' : 'Drag nodes • Click output port then input port to wire'}
        </span>
      </div>
      <div
        ref={containerRef}
        className="vp-canvas-dropzone"
        data-testid="vp-canvas-dropzone"
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onMouseMove={handleNodeMouseMove}
        onMouseUp={handleNodeMouseUp}
        onMouseLeave={handleNodeMouseUp}
      >
        {nodes.length === 0 && (
          <div className="vp-canvas-empty-hint-wrap">
            <p className="vp-canvas-empty-hint">Drag nodes from the palette onto the canvas.</p>
          </div>
        )}
        <svg ref={svgRef} className="vp-canvas-svg" viewBox="0 0 800 500" preserveAspectRatio="xMidYMid meet">
          <defs>
            <marker id="vp-arrow" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="var(--status-ok)" />
            </marker>
          </defs>
          {/* Edges */}
          <g className="vp-edges">
            {edges.map((edge) => {
              const srcNode = nodes.find((n) => n.id === edge.source_node);
              const tgtNode = nodes.find((n) => n.id === edge.target_node);
              const outIdx = Math.max(0, srcNode?.ports?.outputs?.findIndex((p) => p.name === edge.source_port) ?? 0);
              const inIdx = Math.max(0, tgtNode?.ports?.inputs?.findIndex((p) => p.name === edge.target_port) ?? 0);
              const srcPort = getPortCoords(edge.source_node, true, outIdx, srcNode ?? undefined);
              const tgtPort = getPortCoords(edge.target_node, false, inIdx, tgtNode ?? undefined);
              const srcNorm = srcNode ? getPortNormal(srcNode, true, outIdx) : { dx: 0, dy: 1 };
              const tgtNorm = tgtNode ? getPortNormal(tgtNode, false, inIdx) : { dx: 0, dy: -1 };
              const k = EDGE_NORMAL_OFFSET;
              const p1x = srcPort.cx + k * srcNorm.dx;
              const p1y = srcPort.cy + k * srcNorm.dy;
              const p2x = tgtPort.cx + k * tgtNorm.dx;
              const p2y = tgtPort.cy + k * tgtNorm.dy;
              return (
                <path
                  key={edge.id}
                  className="vp-edge-path"
                  d={`M ${srcPort.cx} ${srcPort.cy} C ${p1x} ${p1y}, ${p2x} ${p2y}, ${tgtPort.cx} ${tgtPort.cy}`}
                  fill="none"
                  stroke="var(--status-ok)"
                  strokeWidth="2.5"
                  markerEnd="url(#vp-arrow)"
                />
              );
            })}
          </g>
          {/* Nodes */}
          <g className="vp-nodes">
            {nodes.map((node) => {
              const pos = getPos(node.id);
              const label = getNodeLabel(node);
              const inputs = node.ports?.inputs || [];
              const outputs = node.ports?.outputs || [];
              const isSelected = selectedNodeId === node.id;
              const w = getNodeWidth(node);
              const h = getNodeHeight(node);
              const isStreamTap = isStreamTapNode(node);
              const showVideo = isStreamTapWithVideo(node) && runningInstanceIds[0];
              return (
                <g
                  key={node.id}
                  className={`vp-node vp-node-${node.type} ${isStreamTap ? 'vp-node-streamtap-video' : ''} ${isSelected ? 'vp-node-selected' : ''}`}
                  transform={`translate(${pos.x}, ${pos.y})`}
                >
                  <rect
                    width={w}
                    height={h}
                    rx="4"
                    fill="var(--bg-secondary)"
                    stroke={isSelected ? 'var(--status-ok)' : 'var(--border)'}
                    strokeWidth={isSelected ? 2 : 1}
                    onMouseDown={handleNodeMouseDown(node.id)}
                  />
                  {node.type === 'stage' && node.stage_id === 'preprocess_gpu' && (
                    <circle
                      cx={10}
                      cy={10}
                      r={5}
                      fill={stageRuntimes['preprocess_gpu'] === 'gpu' ? '#2563eb' : '#eab308'}
                      stroke="var(--border)"
                      strokeWidth={1}
                      className="vp-node-runtime-dot"
                    />
                  )}
                  <foreignObject
                    x={0}
                    y={0}
                    width={w}
                    height={h}
                    style={{ overflow: 'hidden', pointerEvents: 'none' }}
                  >
                    {isStreamTap ? (
                      <div xmlns="http://www.w3.org/1999/xhtml" className="vp-node-streamtap-wrap">
                        {showVideo ? (
                          <>
                            <StreamTapNodeVideo instanceId={runningInstanceIds[0]} tapId={node.id} />
                            <span className="vp-node-streamtap-label">{label}</span>
                          </>
                        ) : (
                          <span className="vp-node-streamtap-waiting vp-node-streamtap-placeholder">
                            Run pipeline to see video
                          </span>
                        )}
                      </div>
                    ) : (
                      <div
                        xmlns="http://www.w3.org/1999/xhtml"
                        className="vp-node-label"
                        style={{
                          width: '100%',
                          height: '100%',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          padding: '2px 18px 2px 6px',
                          fontSize: '11px',
                          lineHeight: 1.2,
                          textAlign: 'center',
                          wordBreak: 'break-word',
                          overflow: 'hidden',
                          boxSizing: 'border-box',
                          color: 'var(--text-primary)',
                        }}
                      >
                        {label}
                      </div>
                    )}
                  </foreignObject>
                  {/* Delete button */}
                  <g
                    className="vp-node-delete"
                    onClick={handleDeleteNode(node.id)}
                    onMouseDown={(e) => e.stopPropagation()}
                  >
                    <rect x={w - 17} y={2} width={14} height={14} rx="2" fill="var(--status-error)" opacity="0.9" />
                    <text x={w - 10} y={12} textAnchor="middle" fill="white" fontSize="10">×</text>
                  </g>
                  {/* Input ports (source/stage: top middle; sink: left) */}
                  {inputs.map((p, i) => {
                    const { cx: px, cy: py } = getPortPosRel(node, false, i);
                    return (
                      <circle
                        key={`in-${p.name}`}
                        className="vp-port vp-port-input"
                        cx={px}
                        cy={py}
                        r={PORT_SIZE / 2}
                        fill="var(--text-secondary)"
                        stroke="var(--border)"
                        strokeWidth="1"
                        onClick={handleInputPortClick(node.id, p.name)}
                      />
                    );
                  })}
                  {/* Output ports (source/stage: bottom middle; sink: right) */}
                  {outputs.map((p, i) => {
                    const { cx: px, cy: py } = getPortPosRel(node, true, i);
                    return (
                      <circle
                        key={`out-${p.name}`}
                        className="vp-port vp-port-output"
                        cx={px}
                        cy={py}
                        r={PORT_SIZE / 2}
                        fill="var(--status-ok)"
                        stroke="var(--border)"
                        strokeWidth="1"
                        onClick={handleOutputPortClick(node.id, p.name)}
                      />
                    );
                  })}
                </g>
              );
            })}
          </g>
        </svg>
      </div>
    </div>
  );
};

export default PipelineCanvas;
