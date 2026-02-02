/**
 * Properties & Controls / Pipeline Manager - Right panel per mockup
 * Node properties, pipeline controls, load/save, running instances
 */

import React, { useState, useCallback, useMemo } from 'react';
import { VPNode, VPEdge } from '../../types';
import { validateGraph } from '../../utils/vpApi';
import {
  createAlgorithm,
  updateAlgorithm,
  fetchAlgorithm,
  fetchAlgorithms,
  deleteAlgorithm,
  AlgorithmMeta,
} from '../../utils/algorithmApi';
import {
  fetchPipelineInstances,
  startPipeline,
  stopPipeline,
  PipelineInstance,
} from '../../utils/pipelineApi';
import StreamTapViewer from './StreamTapViewer';
import { fetchCameras } from '../../utils/cameraApi';
import { Camera } from '../../types';
import {
  getAllStageAlgorithmSchemas,
  getStageAlgorithmSchema,
  getDefaultConfigForAlgorithm,
  StageVariableSchema,
} from '../../utils/stageAlgorithmSchemas';
import '../../styles/vp/PropertiesAndControlsPanel.css';

interface PropertiesAndControlsPanelProps {
  selectedNode: VPNode | null;
  nodes: VPNode[];
  edges: VPEdge[];
  layout: Record<string, { x: number; y: number }>;
  algorithmId: string | null;
  algorithmName: string;
  onNodeConfigChange?: (nodeId: string, config: Record<string, unknown>) => void;
  onNodeAlgorithmChange?: (nodeId: string, stageId: string, config: Record<string, unknown>) => void;
  onGraphLoad?: (nodes: VPNode[], edges: VPEdge[], layout: Record<string, { x: number; y: number }>, name: string) => void;
  onAlgorithmIdChange?: (id: string | null, name?: string) => void;
  /** Page's running instance ids (from refetch + optimistic); merged into display so panel shows instance even when API returns []. */
  runningInstanceIds?: string[];
  /** Called after a pipeline is successfully started with the new instance id. */
  onPipelineStarted?: (instanceId: string) => void;
}

const PropertiesAndControlsPanel: React.FC<PropertiesAndControlsPanelProps> = ({
  selectedNode,
  nodes,
  edges,
  layout,
  algorithmId,
  algorithmName,
  onNodeConfigChange,
  onNodeAlgorithmChange,
  onGraphLoad,
  onAlgorithmIdChange,
  runningInstanceIds = [],
  onPipelineStarted,
}) => {
  const [validateStatus, setValidateStatus] = useState<{ valid?: boolean; errors?: string[] } | null>(null);
  const [saveName, setSaveName] = useState(algorithmName || 'Untitled');
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [instances, setInstances] = useState<PipelineInstance[]>([]);
  const [algorithms, setAlgorithms] = useState<AlgorithmMeta[]>([]);
  const [streamTapViewerInstanceId, setStreamTapViewerInstanceId] = useState<string | null>(null);
  const [selectedRunCameraId, setSelectedRunCameraId] = useState<string>('');

  const loadCameras = async () => {
    try {
      const list = await fetchCameras();
      setCameras(list);
      setSelectedRunCameraId((prev) => {
        if (!prev && list.length > 0) return list[0].id;
        if (prev && !list.some((c) => c.id === prev)) return list[0]?.id ?? '';
        return prev;
      });
    } catch (e) {
      setCameras([]);
      console.warn('[Vision Pipeline] Load cameras failed', e);
    }
  };

  const loadInstances = async (optimistic?: { id: string; algorithm_id: string; target: string }) => {
    try {
      const list = await fetchPipelineInstances();
      if (list.length > 0) {
        setInstances(list);
      } else if (optimistic) {
        setInstances([{ ...optimistic, state: 'running' as const }]);
      } else {
        setInstances([]);
      }
    } catch (e) {
      if (optimistic) setInstances([{ ...optimistic, state: 'running' as const }]);
      else setInstances([]);
      console.warn('[Vision Pipeline] Load instances failed', e);
    }
  };

  const loadAlgorithms = async () => {
    try {
      const list = await fetchAlgorithms();
      setAlgorithms(list);
    } catch (e) {
      setAlgorithms([]);
      console.warn('[Vision Pipeline] Load algorithms failed', e);
    }
  };

  React.useEffect(() => {
    loadCameras();
    loadInstances();
    loadAlgorithms();
    const interval = setInterval(() => {
      loadInstances();
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  React.useEffect(() => {
    setSaveName(algorithmName || 'Untitled');
  }, [algorithmName]);

  React.useEffect(() => {
    if (algorithmId && algorithms.some((a) => a.id === algorithmId)) {
      setSelectedPipelineId(algorithmId);
    }
  }, [algorithmId, algorithms]);

  const handleValidate = async () => {
    setLoading(true);
    setValidateStatus(null);
    try {
      const result = await validateGraph(nodes, edges);
      setValidateStatus({ valid: result.valid, errors: result.errors || [] });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Validation failed';
      setValidateStatus({ valid: false, errors: [msg] });
      console.error('[Vision Pipeline] Validate failed', msg, err);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveAlgorithm = async () => {
    setLoading(true);
    setSaveError(null);
    setRunError(null);
    setSaveSuccess(false);
    try {
      // Merge default algorithm config into stage nodes so variables are saved per algorithm
      const nodesToSave = nodes.map((n) => {
        if (n.type !== 'stage' || !n.stage_id) return n;
        const defaults = getDefaultConfigForAlgorithm(n.stage_id);
        const merged = { ...defaults, ...(n.config || {}) };
        return { ...n, config: merged };
      });
      const graph = { name: saveName.trim() || 'Untitled', nodes: nodesToSave, edges, layout };
      console.log('[Vision Pipeline] Save started', {
        algorithmId: algorithmId ?? '(new)',
        name: graph.name,
        nodeCount: nodes.length,
        edgeCount: edges.length,
      });
      if (algorithmId) {
        await updateAlgorithm(algorithmId, graph);
        onAlgorithmIdChange?.(algorithmId, saveName.trim() || 'Untitled');
        console.log('[Vision Pipeline] Save succeeded (update)', { id: algorithmId });
      } else {
        const created = await createAlgorithm(graph);
        onAlgorithmIdChange?.(created.id, created.name);
        console.log('[Vision Pipeline] Save succeeded (create)', { id: created.id, name: created.name });
      }
      setSaveSuccess(true);
      loadAlgorithms();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Save failed';
      setSaveError(msg);
      console.error('[Vision Pipeline] Save failed', { error: msg, err });
    } finally {
      setLoading(false);
    }
  };

  const handleLoadPipeline = async (id: string) => {
    setLoading(true);
    setSaveError(null);
    try {
      const alg = await fetchAlgorithm(id);
      onGraphLoad?.(
        alg.nodes || [],
        alg.edges || [],
        alg.layout || {},
        alg.name || 'Untitled'
      );
      onAlgorithmIdChange?.(id, alg.name || 'Untitled');
      setSaveName(alg.name || 'Untitled');
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'Load failed');
    } finally {
      setLoading(false);
    }
  };

  const handleRunPipeline = async () => {
    if (!algorithmId) return;
    const cam = selectedRunCameraId || cameras[0]?.id;
    if (!cam) return;
    setLoading(true);
    setRunError(null);
    try {
      console.log('[Vision Pipeline] Run started', { algorithmId, camera: cam });
      const result = await startPipeline(algorithmId, cam);
      loadInstances(result?.id ? { id: result.id, algorithm_id: algorithmId, target: cam } : undefined);
      if (result?.id) onPipelineStarted?.(result.id);
      console.log('[Vision Pipeline] Run succeeded', { algorithmId, camera: cam, instanceId: result?.id });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to start pipeline';
      setRunError(msg);
      console.error('[Vision Pipeline] Run failed', msg, err);
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async (instanceId: string) => {
    setLoading(true);
    try {
      await stopPipeline(instanceId);
      loadInstances();
    } finally {
      setLoading(false);
    }
  };

  const [selectedPipelineId, setSelectedPipelineId] = useState<string>('');

  // Merge API instances with page's runningInstanceIds so we show the just-started instance even when GET returns []
  const displayInstances = useMemo(() => {
    const byId = new Map(instances.map((i) => [i.id, i]));
    for (const id of runningInstanceIds) {
      if (!byId.has(id)) byId.set(id, { id, algorithm_id: 'pipeline', target: id, state: 'running' as const });
    }
    return [...byId.values()];
  }, [instances, runningInstanceIds]);

  const handleDeletePipeline = async (id: string) => {
    if (!id) return;
    if (!window.confirm(`Delete pipeline "${algorithms.find((a) => a.id === id)?.name ?? id}"?`)) return;
    setLoading(true);
    setSaveError(null);
    try {
      await deleteAlgorithm(id);
      loadAlgorithms();
      if (algorithmId === id) {
        onAlgorithmIdChange?.(null);
        onGraphLoad?.([], [], {}, 'Untitled');
        setSaveName('Untitled');
      }
      setSelectedPipelineId('');
      console.log('[Vision Pipeline] Delete succeeded', { id });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Delete failed';
      setSaveError(msg);
      console.error('[Vision Pipeline] Delete failed', msg, err);
    } finally {
      setLoading(false);
    }
  };

  const handleConfigChange = (key: string, value: unknown) => {
    if (!selectedNode) return;
    const config = { ...(selectedNode.config || {}), [key]: value };
    onNodeConfigChange?.(selectedNode.id, config);
  };

  const getNodeLabel = (node: VPNode): string => {
    return node.name || node.stage_id || node.source_type || node.sink_type || node.type || node.id;
  };

  const StageVariables: React.FC<{
    schema: { variables: StageVariableSchema[] };
    config: Record<string, unknown>;
    onConfigChange: (key: string, value: unknown) => void;
  }> = ({ schema, config, onConfigChange }) => {
    if (schema.variables.length === 0) return null;
    return (
      <div className="vp-props-config">
        <span className="vp-props-section-title" style={{ marginTop: 8, marginBottom: 6, display: 'block' }}>
          Variables (saved per algorithm)
        </span>
        {schema.variables.map((v) => (
          <div key={v.key} className="vp-props-row">
            <span className="vp-props-label">{v.label}:</span>
            {v.type === 'number' && (
              <input
                type="number"
                className="vp-props-input"
                value={Number(config[v.key] ?? v.default)}
                min={v.min}
                max={v.max}
                onChange={(e) => {
                  const n = e.target.valueAsNumber;
                  onConfigChange(v.key, Number.isNaN(n) ? v.default : n);
                }}
              />
            )}
            {v.type === 'select' && (
              <select
                className="vp-props-select"
                value={String(config[v.key] ?? v.default)}
                onChange={(e) => onConfigChange(v.key, e.target.value)}
              >
                {v.options?.map((o) => (
                  <option key={String(o.value)} value={String(o.value)}>{o.label}</option>
                ))}
              </select>
            )}
            {v.type === 'boolean' && (
              <input
                type="checkbox"
                checked={Boolean(config[v.key] ?? v.default)}
                onChange={(e) => onConfigChange(v.key, e.target.checked)}
              />
            )}
            {v.type === 'text' && (
              <input
                type="text"
                className="vp-props-input"
                value={String(config[v.key] ?? v.default)}
                onChange={(e) => onConfigChange(v.key, e.target.value)}
              />
            )}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="vp-props-panel">
      <div className="vp-props-scroll">
        <div className="vp-props-header">
          <h3 className="vp-props-title">Properties & Controls</h3>
        </div>
        {/* Node Properties */}
      <div className="vp-props-section">
        <h4 className="vp-props-section-title">Node Properties</h4>
        {selectedNode ? (
          <div className="vp-props-node">
            <div className="vp-props-row">
              <span className="vp-props-label">Type:</span>
              <span className="vp-props-value">{getNodeLabel(selectedNode)}</span>
            </div>
            <div className="vp-props-row">
              <span className="vp-props-label">ID:</span>
              <span className="vp-props-value">{selectedNode.id}</span>
            </div>
            {selectedNode.type === 'source' && (
              <div className="vp-props-row">
                <span className="vp-props-label">Config:</span>
                <select
                  className="vp-props-select"
                  value={(selectedNode.config?.camera_id as string) || ''}
                  onChange={(e) => handleConfigChange('camera_id', e.target.value)}
                >
                  <option value="">Select camera</option>
                  {cameras.map((c) => (
                    <option key={c.id} value={c.id}>{c.custom_name || c.name || c.id}</option>
                  ))}
                </select>
              </div>
            )}
            {selectedNode.type === 'stage' && (
              <>
                <div className="vp-props-row">
                  <span className="vp-props-label">Algorithm:</span>
                  <select
                    className="vp-props-select"
                    value={selectedNode.stage_id || ''}
                    onChange={(e) => {
                      const newStageId = e.target.value;
                      if (!newStageId || !onNodeAlgorithmChange) return;
                      const defaults = getDefaultConfigForAlgorithm(newStageId);
                      onNodeAlgorithmChange(selectedNode.id, newStageId, defaults);
                    }}
                  >
                    <option value="">Select algorithm...</option>
                    {getAllStageAlgorithmSchemas().map((s) => (
                      <option key={s.id} value={s.id}>{s.label}</option>
                    ))}
                  </select>
                </div>
                {(selectedNode.stage_id && getStageAlgorithmSchema(selectedNode.stage_id)) && (
                  <StageVariables
                    schema={getStageAlgorithmSchema(selectedNode.stage_id)!}
                    config={selectedNode.config || {}}
                    onConfigChange={handleConfigChange}
                  />
                )}
              </>
            )}
          </div>
        ) : (
          <p className="vp-props-empty">Select a node on the canvas</p>
        )}
      </div>

      {/* Pipeline Controls */}
      <div className="vp-props-section">
        <h4 className="vp-props-section-title">Pipeline Controls</h4>
        <button
          type="button"
          className="vp-props-btn vp-props-btn-secondary"
          onClick={handleValidate}
          disabled={loading}
        >
          Validate Graph
        </button>
        {validateStatus && (
          <div className={`vp-props-validate vp-props-validate-${validateStatus.valid ? 'ok' : 'error'}`}>
            {validateStatus.valid ? 'Valid' : (validateStatus.errors || []).join(', ')}
          </div>
        )}
        <div className="vp-props-run-row">
          <select
            className="vp-props-select vp-props-run-camera"
            value={selectedRunCameraId}
            onChange={(e) => setSelectedRunCameraId(e.target.value)}
            disabled={loading || cameras.length === 0}
            title="Camera to run pipeline on"
          >
            <option value="">Select camera...</option>
            {cameras.map((c) => (
              <option key={c.id} value={c.id}>
                {c.custom_name || c.name || c.id}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="vp-props-btn vp-props-btn-primary"
            onClick={handleRunPipeline}
            disabled={loading || !algorithmId || !cameras.length || !selectedRunCameraId}
          >
            Run Pipeline
          </button>
        </div>
        {!algorithmId && (
          <p className="vp-props-hint">Save the pipeline first (name + Save Algorithm), then Run Pipeline.</p>
        )}
        {algorithmId && !cameras.length && (
          <p className="vp-props-hint">No cameras available. Add or connect a camera from the Cameras page.</p>
        )}
        {runError && <div className="vp-props-error">{runError}</div>}
        <div className="vp-props-save-row">
          <input
            type="text"
            className="vp-props-save-input"
            value={saveName}
            onChange={(e) => setSaveName(e.target.value)}
            placeholder="Algorithm name"
          />
          <button
            type="button"
            className="vp-props-btn vp-props-btn-secondary"
            onClick={handleSaveAlgorithm}
            disabled={loading}
          >
            Save Algorithm
          </button>
        </div>
        {saveError && <div className="vp-props-error">{saveError}</div>}
        {saveSuccess && <div className="vp-props-success">Saved</div>}
      </div>

      {/* Pipeline Manager */}
      <div className="vp-props-section">
        <h4 className="vp-props-section-title">Pipeline Manager</h4>
        <div className="vp-props-pipeline-dropdown-row">
          <select
            className="vp-props-pipeline-select"
            value={selectedPipelineId}
            onChange={(e) => setSelectedPipelineId(e.target.value)}
            disabled={loading}
          >
            <option value="">Select pipeline...</option>
            {algorithms.map((alg) => (
              <option key={alg.id} value={alg.id}>
                {alg.name}
              </option>
            ))}
          </select>
        </div>
        <div className="vp-props-pipeline-actions">
          <button
            type="button"
            className="vp-props-btn vp-props-btn-small"
            onClick={() => loadAlgorithms()}
            disabled={loading}
            title="Refresh list"
          >
            Refresh
          </button>
          <button
            type="button"
            className="vp-props-btn vp-props-btn-small"
            onClick={() => selectedPipelineId && handleLoadPipeline(selectedPipelineId)}
            disabled={loading || !selectedPipelineId}
          >
            Load
          </button>
          <button
            type="button"
            className="vp-props-btn vp-props-btn-small"
            onClick={() => selectedPipelineId && handleDeletePipeline(selectedPipelineId)}
            disabled={loading || !selectedPipelineId}
          >
            Delete
          </button>
        </div>
        {algorithms.length === 0 && (
          <p className="vp-props-empty">No saved pipelines</p>
        )}
      </div>

      {/* Running Pipelines */}
      <div className="vp-props-section">
        <h4 className="vp-props-section-title">Running Pipelines</h4>
        {displayInstances.length === 0 ? (
          <p className="vp-props-empty">No pipelines running</p>
        ) : (
          <ul className="vp-props-instance-list">
            {displayInstances.map((inst) => (
              <li key={inst.id} className="vp-props-instance-item">
                <span className="vp-props-instance-name">
                  {inst.algorithm_id} → {inst.target}
                </span>
                <button
                  type="button"
                  className="vp-props-btn vp-props-btn-small"
                  onClick={() => setStreamTapViewerInstanceId(inst.id)}
                  disabled={loading}
                  title="View StreamTap output"
                >
                  View tap
                </button>
                <button
                  type="button"
                  className="vp-props-btn vp-props-btn-small vp-props-btn-close"
                  onClick={() => handleStop(inst.id)}
                  disabled={loading}
                  title="Close pipeline"
                  aria-label="Close pipeline"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
        {streamTapViewerInstanceId && (
          <StreamTapViewer
            instanceId={streamTapViewerInstanceId}
            onClose={() => setStreamTapViewerInstanceId(null)}
          />
        )}
      </div>
      </div>
    </div>
  );
};

export default PropertiesAndControlsPanel;
