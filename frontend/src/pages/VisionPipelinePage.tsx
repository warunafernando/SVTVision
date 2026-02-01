/**
 * Vision Pipeline Editor - SVTVision Pipeline Builder
 * Layout: Palette | Canvas | Properties & Controls / Pipeline Manager
 */

import React, { useState, useCallback } from 'react';
import { VPNode, VPEdge } from '../types';
import { getStageAlgorithmSchema, getDefaultConfigForAlgorithm } from '../utils/stageAlgorithmSchemas';
import Palette from '../components/vp/Palette';
import PipelineCanvas from '../components/vp/PipelineCanvas';
import PropertiesAndControlsPanel from '../components/vp/PropertiesAndControlsPanel';
import '../styles/VisionPipelinePage.css';

const VisionPipelinePage: React.FC = () => {
  const [nodes, setNodes] = useState<VPNode[]>([]);
  const [edges, setEdges] = useState<VPEdge[]>([]);
  const [layout, setLayout] = useState<Record<string, { x: number; y: number }>>({});
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [algorithmId, setAlgorithmId] = useState<string | null>(null);
  const [algorithmName, setAlgorithmName] = useState('Untitled');

  const handleGraphChange = useCallback(
    (newNodes: VPNode[], newEdges: VPEdge[], newLayout: Record<string, { x: number; y: number }>) => {
      setNodes(newNodes);
      setEdges(newEdges);
      setLayout(newLayout || {});
    },
    []
  );

  const handleNodeSelect = useCallback((nodeId: string | null) => {
    setSelectedNodeId(nodeId);
  }, []);

  const handleNodeConfigChange = useCallback((nodeId: string, config: Record<string, unknown>) => {
    setNodes((prev) =>
      prev.map((n) => (n.id === nodeId ? { ...n, config } : n))
    );
  }, []);

  const handleNodeAlgorithmChange = useCallback((nodeId: string, stageId: string, config: Record<string, unknown>) => {
    const schema = getStageAlgorithmSchema(stageId);
    if (!schema) return;
    setNodes((prev) =>
      prev.map((n) =>
        n.id === nodeId
          ? {
              ...n,
              stage_id: stageId,
              name: schema.label,
              ports: schema.ports,
              config,
            }
          : n
      )
    );
  }, []);

  const handleGraphLoad = useCallback(
    (
      newNodes: VPNode[],
      newEdges: VPEdge[],
      newLayout: Record<string, { x: number; y: number }>,
      name: string
    ) => {
      setNodes(newNodes);
      setEdges(newEdges);
      setLayout(newLayout || {});
      setAlgorithmName(name);
      setSelectedNodeId(null);
    },
    []
  );

  const selectedNode = selectedNodeId ? nodes.find((n) => n.id === selectedNodeId) ?? null : null;

  return (
    <div className="vision-pipeline-page">
      <div className="vp-header">
        <h2>SVTVision Pipeline Editor</h2>
        <p className="vp-subtitle">
          Design and run vision processing pipelines (Sources → Stages → Sinks).
        </p>
      </div>
      <div className="vp-content vp-content-three-col">
        <Palette />
        <PipelineCanvas
          nodes={nodes}
          edges={edges}
          layout={layout}
          selectedNodeId={selectedNodeId}
          onGraphChange={handleGraphChange}
          onNodeSelect={handleNodeSelect}
        />
        <PropertiesAndControlsPanel
          selectedNode={selectedNode}
          nodes={nodes}
          edges={edges}
          layout={layout}
          algorithmId={algorithmId}
          algorithmName={algorithmName}
          onNodeConfigChange={handleNodeConfigChange}
          onNodeAlgorithmChange={handleNodeAlgorithmChange}
          onGraphLoad={handleGraphLoad}
          onAlgorithmIdChange={(id, name) => {
            setAlgorithmId(id);
            if (name) setAlgorithmName(name);
          }}
        />
      </div>
    </div>
  );
};

export default VisionPipelinePage;
