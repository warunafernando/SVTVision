/**
 * Vision Pipeline Editor - SVTVision Pipeline Builder
 * Layout: Palette | Canvas | Properties & Controls / Pipeline Manager
 */

import React, { useState, useCallback, useEffect } from 'react';
import { VPNode, VPEdge } from '../types';
import { getStageAlgorithmSchema, getDefaultConfigForAlgorithm } from '../utils/stageAlgorithmSchemas';
import { fetchPipelineInstances } from '../utils/pipelineApi';
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
  const [runningInstanceIds, setRunningInstanceIds] = useState<string[]>([]);

  const refetchRunningInstances = useCallback(async (optimisticId?: string) => {
    try {
      const list = await fetchPipelineInstances();
      let ids = list.filter((i) => i.state === 'running').map((i) => i.id);
      if (optimisticId && !ids.includes(optimisticId)) ids = [...ids, optimisticId];
      setRunningInstanceIds(ids);
    } catch {
      if (optimisticId) setRunningInstanceIds([optimisticId]);
      else setRunningInstanceIds([]);
    }
  }, []);

  useEffect(() => {
    refetchRunningInstances();
    const interval = setInterval(() => refetchRunningInstances(), 2000);
    return () => clearInterval(interval);
  }, [refetchRunningInstances]);

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
          runningInstanceIds={runningInstanceIds}
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
          runningInstanceIds={runningInstanceIds}
          onNodeConfigChange={handleNodeConfigChange}
          onNodeAlgorithmChange={handleNodeAlgorithmChange}
          onGraphLoad={handleGraphLoad}
          onAlgorithmIdChange={(id, name) => {
            setAlgorithmId(id);
            if (name) setAlgorithmName(name);
          }}
          onPipelineStarted={(instanceId) => {
            queueMicrotask(() => {
              console.log('[Vision Pipeline] onPipelineStarted', { instanceId });
              setRunningInstanceIds((prev) => (prev.includes(instanceId) ? prev : [...prev, instanceId]));
              refetchRunningInstances(instanceId);
            });
          }}
        />
      </div>
    </div>
  );
};

export default VisionPipelinePage;
