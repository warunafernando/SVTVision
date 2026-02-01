/**
 * Pipeline Canvas - Drag/drop nodes, move nodes, delete, wire connections
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { VPNode, VPEdge } from '../../types';
import '../../styles/vp/PipelineCanvas.css';

function genId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 9)}`;
}

interface PipelineCanvasProps {
  nodes: VPNode[];
  edges: VPEdge[];
  layout: Record<string, { x: number; y: number }>;
  selectedNodeId: string | null;
  onGraphChange: (nodes: VPNode[], edges: VPEdge[], layout: Record<string, { x: number; y: number }>) => void;
  onNodeSelect: (nodeId: string | null) => void;
}

const NODE_WIDTH = 105;   /* 75% of 140 */
const NODE_HEIGHT = 42;   /* 75% of 56 */
const PORT_SIZE = 11;     /* 75% of 14 */

const PipelineCanvas: React.FC<PipelineCanvasProps> = ({
  nodes,
  edges,
  layout,
  selectedNodeId,
  onGraphChange,
  onNodeSelect,
}) => {
  const [wireFrom, setWireFrom] = useState<{ nodeId: string; port: string } | null>(null);
  const [dragNode, setDragNode] = useState<{ nodeId: string; startX: number; startY: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

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
        const node: VPNode = {
          id: nodeId,
          type: data.type || 'stage',
          stage_id: data.stage_id,
          source_type: data.source_type,
          sink_type: data.sink_type,
          name: data.name || data.paletteLabel,
          ports: data.ports || { inputs: [{ name: 'in', type: 'frame' }], outputs: [{ name: 'out', type: 'frame' }] },
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
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedNodeId) {
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

  const getPortCoords = (nodeId: string, isOutput: boolean, portIndex: number) => {
    const pos = getPos(nodeId);
    const node = nodes.find((n) => n.id === nodeId);
    const ports = isOutput ? (node?.ports?.outputs || []) : (node?.ports?.inputs || []);
    const count = Math.max(1, ports.length);
    const cy = pos.y + NODE_HEIGHT / 2 - (count * PORT_SIZE) / 2 + portIndex * PORT_SIZE + PORT_SIZE / 2;
    const cx = isOutput ? pos.x + NODE_WIDTH : pos.x;
    return { cx, cy };
  };

  return (
    <div className="vp-canvas">
      <div className="vp-canvas-toolbar">
        <span className="vp-canvas-hint">
          {wireFrom ? 'Click input port (left side) to connect' : selectedNodeId ? 'Press Delete to remove • Drag to move' : 'Drag nodes • Click output (right) then input (left) to wire'}
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
              const src = getPos(edge.source_node);
              const tgt = getPos(edge.target_node);
              const srcNode = nodes.find((n) => n.id === edge.source_node);
              const outIdx = srcNode?.ports?.outputs?.findIndex((p) => p.name === edge.source_port) ?? 0;
              const tgtNode = nodes.find((n) => n.id === edge.target_node);
              const inIdx = tgtNode?.ports?.inputs?.findIndex((p) => p.name === edge.target_port) ?? 0;
              const srcPort = getPortCoords(edge.source_node, true, Math.max(0, outIdx));
              const tgtPort = getPortCoords(edge.target_node, false, Math.max(0, inIdx));
              const midX = (srcPort.cx + tgtPort.cx) / 2;
              return (
                <path
                  key={edge.id}
                  className="vp-edge-path"
                  d={`M ${srcPort.cx} ${srcPort.cy} C ${midX} ${srcPort.cy}, ${midX} ${tgtPort.cy}, ${tgtPort.cx} ${tgtPort.cy}`}
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
              return (
                <g
                  key={node.id}
                  className={`vp-node vp-node-${node.type} ${isSelected ? 'vp-node-selected' : ''}`}
                  transform={`translate(${pos.x}, ${pos.y})`}
                >
                  <rect
                    width={NODE_WIDTH}
                    height={NODE_HEIGHT}
                    rx="4"
                    fill="var(--bg-secondary)"
                    stroke={isSelected ? 'var(--status-ok)' : 'var(--border)'}
                    strokeWidth={isSelected ? 2 : 1}
                    onMouseDown={handleNodeMouseDown(node.id)}
                  />
                  <foreignObject
                    x={0}
                    y={0}
                    width={NODE_WIDTH}
                    height={NODE_HEIGHT}
                    style={{ overflow: 'hidden', pointerEvents: 'none' }}
                  >
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
                  </foreignObject>
                  {/* Delete button */}
                  <g
                    className="vp-node-delete"
                    onClick={handleDeleteNode(node.id)}
                    onMouseDown={(e) => e.stopPropagation()}
                  >
                    <rect x={NODE_WIDTH - 17} y={2} width={14} height={14} rx="2" fill="var(--status-error)" opacity="0.9" />
                    <text x={NODE_WIDTH - 10} y={12} textAnchor="middle" fill="white" fontSize="10">×</text>
                  </g>
                  {/* Input ports */}
                  {inputs.map((p, i) => (
                    <circle
                      key={`in-${p.name}`}
                      className="vp-port vp-port-input"
                      cx={0}
                      cy={NODE_HEIGHT / 2 - (inputs.length * PORT_SIZE) / 2 + i * PORT_SIZE + PORT_SIZE / 2}
                      r={PORT_SIZE / 2}
                      fill="var(--text-secondary)"
                      stroke="var(--border)"
                      strokeWidth="1"
                      onClick={handleInputPortClick(node.id, p.name)}
                    />
                  ))}
                  {/* Output ports */}
                  {outputs.map((p, i) => (
                    <circle
                      key={`out-${p.name}`}
                      className="vp-port vp-port-output"
                      cx={NODE_WIDTH}
                      cy={NODE_HEIGHT / 2 - (outputs.length * PORT_SIZE) / 2 + i * PORT_SIZE + PORT_SIZE / 2}
                      r={PORT_SIZE / 2}
                      fill="var(--status-ok)"
                      stroke="var(--border)"
                      strokeWidth="1"
                      onClick={handleOutputPortClick(node.id, p.name)}
                    />
                  ))}
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
