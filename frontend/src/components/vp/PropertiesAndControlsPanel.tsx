/**
 * Properties & Controls / Pipeline Manager - Right panel per mockup
 * Node properties, pipeline controls, load/save, running instances
 */

import React, { useState, useCallback, useMemo, useRef } from 'react';
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
  stopAllPipelines,
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
  const fileInputRef = useRef<HTMLInputElement>(null);
  const directoryInputRef = useRef<HTMLInputElement>(null);

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

  const isFileSource = useMemo(() => {
    const sources = nodes.filter(
      (n) => n.type === 'source' && (n.source_type === 'video_file' || n.source_type === 'image_file')
    );
    if (sources.length !== 1) return false;
    const path = (sources[0].config?.path as string) || (sources[0].config?.location as string) || '';
    return path.trim().length > 0;
  }, [nodes]);

  const handleRunPipeline = async () => {
    const hasGraph = nodes.length > 0;
    if (!hasGraph) {
      setRunError('Add at least one node to the graph, then Run.');
      return;
    }
    const target = isFileSource ? 'file' : (selectedRunCameraId || cameras[0]?.id);
    if (!target) {
      setRunError('Select a camera to run on, or use a VideoFile/ImageFile source with Location set.');
      return;
    }
    setLoading(true);
    setRunError(null);
    try {
      console.log('[Vision Pipeline] Run started', { target, algorithmId: algorithmId ?? '(unsaved)', nodes: nodes.length });
      const result = await startPipeline(target, {
        algorithmId: algorithmId ?? undefined,
        nodes,
        edges,
      });
      loadInstances(result?.id ? { id: result.id, algorithm_id: algorithmId ?? 'pipeline', target } : undefined);
      if (result?.id) onPipelineStarted?.(result.id);
      console.log('[Vision Pipeline] Run succeeded', { target, instanceId: result?.id });
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

  const handleStopAll = async () => {
    setLoading(true);
    try {
      await stopAllPipelines();
      loadInstances();
    } catch (e) {
      console.error('[Vision Pipeline] Stop all failed', e);
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

  // Instance currently running for the selected camera (for Run → Stop button toggle)
  const runningInstanceForSelectedCamera = useMemo(
    () => displayInstances.find((inst) => inst.target === selectedRunCameraId && inst.state === 'running'),
    [displayInstances, selectedRunCameraId]
  );
  // When source is video file, instance id is file:xxx
  const runningInstanceForFile = useMemo(
    () => displayInstances.find((inst) => String(inst.id).startsWith('file:') && inst.state === 'running'),
    [displayInstances]
  );
  const runningInstance = runningInstanceForFile ?? runningInstanceForSelectedCamera;

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

  const handleDeleteAllPipelines = async () => {
    if (algorithms.length === 0) return;
    if (!window.confirm(`Delete all ${algorithms.length} saved pipeline(s)?`)) return;
    setLoading(true);
    setSaveError(null);
    const ids = algorithms.map((a) => a.id);
    try {
      for (const id of ids) {
        try {
          await deleteAlgorithm(id);
        } catch (err) {
          console.error('[Vision Pipeline] Delete all: failed for', id, err);
        }
      }
      loadAlgorithms();
      if (algorithmId && ids.includes(algorithmId)) {
        onAlgorithmIdChange?.(null);
        onGraphLoad?.([], [], {}, 'Untitled');
        setSaveName('Untitled');
      }
      setSelectedPipelineId('');
      console.log('[Vision Pipeline] Delete all succeeded', { count: ids.length });
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Delete all failed';
      setSaveError(msg);
      console.error('[Vision Pipeline] Delete all failed', msg, err);
    } finally {
      setLoading(false);
    }
  };

  const handleConfigChange = (key: string, value: unknown) => {
    if (!selectedNode) return;
    const config = { ...(selectedNode.config || {}), [key]: value };
    onNodeConfigChange?.(selectedNode.id, config);
  };

  const openFilePicker = (accept: string) => {
    if (!fileInputRef.current) return;
    fileInputRef.current.accept = accept;
    fileInputRef.current.value = '';
    fileInputRef.current.click();
  };

  const DEFAULT_OUTPUT_FOLDER = '/home/svt/Documents';

  const randomOutputFilename = (ext: 'mp4' | 'jpg') => {
    const base = `output_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    return `${base}.${ext}`;
  };

  const openDirectoryPicker = async () => {
    if (!selectedNode) return;
    const w = window as Window & { showDirectoryPicker?: () => Promise<FileSystemDirectoryHandle> };
    if (typeof w.showDirectoryPicker === 'function') {
      try {
        const handle = await w.showDirectoryPicker();
        const handlePath = (handle as FileSystemDirectoryHandle & { path?: string }).path;
        const dirPath = handlePath ?? DEFAULT_OUTPUT_FOLDER;
        const isSink = selectedNode.sink_type === 'save_video' || selectedNode.sink_type === 'save_image';
        const sep = dirPath.includes('\\') ? '\\' : '/';
        const path = isSink
          ? dirPath + sep + randomOutputFilename(selectedNode.sink_type === 'save_video' ? 'mp4' : 'jpg')
          : dirPath;
        handleConfigChange('path', path);
      } catch (err) {
        if ((err as Error).name !== 'AbortError') console.warn('[Vision Pipeline] showDirectoryPicker failed', err);
      }
      return;
    }
    if (directoryInputRef.current) {
      directoryInputRef.current.value = '';
      directoryInputRef.current.click();
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && selectedNode) {
      const path = (file as File & { path?: string }).path ?? file.name;
      handleConfigChange('path', path);
    }
    e.target.value = '';
  };

  const handleDirectorySelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const input = e.target;
    const files = input.files;
    if (!files?.length || !selectedNode) {
      setTimeout(() => { input.value = ''; }, 0);
      return;
    }
    const file = files[0] as File & { path?: string; webkitRelativePath?: string };
    let dirPath = '';
    if (file.path) {
      dirPath = file.path.replace(/[/\\][^/\\]*$/, '');
    } else if (file.webkitRelativePath) {
      const parts = file.webkitRelativePath.split('/');
      parts.pop();
      dirPath = parts.join('/');
    }
    if (!dirPath) {
      dirPath = DEFAULT_OUTPUT_FOLDER;
    }
    const isSink = selectedNode.sink_type === 'save_video' || selectedNode.sink_type === 'save_image';
    const sep = dirPath.includes('\\') ? '\\' : '/';
    const path = isSink
      ? dirPath + sep + randomOutputFilename(selectedNode.sink_type === 'save_video' ? 'mp4' : 'jpg')
      : dirPath;
    handleConfigChange('path', path);
    setTimeout(() => { input.value = ''; }, 0);
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
      <input
        ref={fileInputRef}
        type="file"
        className="vp-props-file-hidden"
        onChange={handleFileSelect}
        aria-hidden="true"
        tabIndex={-1}
      />
      <input
        id="vp-directory-picker"
        ref={directoryInputRef}
        type="file"
        className="vp-props-file-hidden"
        onChange={handleDirectorySelect}
        aria-hidden="true"
        tabIndex={-1}
        webkitdirectory="true"
      />
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
            {selectedNode.type === 'source' && selectedNode.source_type === 'camera' && (
              <div className="vp-props-row">
                <span className="vp-props-label">Camera:</span>
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
            {selectedNode.type === 'source' && (selectedNode.source_type === 'video_file' || selectedNode.source_type === 'image_file') && (
              <div className="vp-props-row">
                <span className="vp-props-label">Location:</span>
                <div className="vp-props-location-row">
                  <input
                    type="text"
                    className="vp-props-input vp-props-location-input"
                    value={(selectedNode.config?.path as string) || ''}
                    onChange={(e) => handleConfigChange('path', e.target.value)}
                    placeholder="/home/svt/Documents/ (File or Folder to pick)"
                  />
                  <button
                    type="button"
                    className="vp-props-btn vp-props-btn-browse"
                    onClick={() => openFilePicker(selectedNode.source_type === 'video_file' ? 'video/*,.mp4,.avi,.mov' : 'image/*,.jpg,.jpeg,.png,.bmp')}
                    title="Browse for file"
                  >
                    File
                  </button>
                  <button
                    type="button"
                    className="vp-props-btn vp-props-btn-browse"
                    onClick={openDirectoryPicker}
                    title="Browse for folder"
                  >
                    Folder
                  </button>
                </div>
              </div>
            )}
            {selectedNode.type === 'sink' && (selectedNode.sink_type === 'save_video' || selectedNode.sink_type === 'save_image') && (
              <div className="vp-props-row">
                <span className="vp-props-label">Location:</span>
                <div className="vp-props-location-row">
                  <input
                    type="text"
                    className="vp-props-input vp-props-location-input"
                    value={(selectedNode.config?.path as string) || (selectedNode.config?.output_path as string) || ''}
                    onChange={(e) => handleConfigChange('path', e.target.value)}
                    placeholder="/home/svt/Documents/ (random filename from File/Folder)"
                  />
                  <button
                    type="button"
                    className="vp-props-btn vp-props-btn-browse"
                    onClick={() => openFilePicker(selectedNode.sink_type === 'save_video' ? '.mp4,video/mp4' : '.jpg,.jpeg,.png,image/jpeg,image/png')}
                    title="Browse for file"
                  >
                    File
                  </button>
                  <button
                    type="button"
                    className="vp-props-btn vp-props-btn-browse"
                    onClick={openDirectoryPicker}
                    title="Select folder (uses Select Folder dialog when supported)"
                  >
                    Folder
                  </button>
                </div>
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
            className={`vp-props-btn ${runningInstance ? 'vp-props-btn-danger' : 'vp-props-btn-primary'}`}
            onClick={runningInstance ? () => handleStop(runningInstance.id) : handleRunPipeline}
            disabled={
              loading ||
              (!!runningInstance ? false : nodes.length === 0) ||
              (!runningInstance && !isFileSource && (!cameras.length || !selectedRunCameraId))
            }
            title={runningInstance ? 'Stop pipeline' : isFileSource ? 'Run pipeline from file' : 'Run pipeline on selected camera'}
          >
            {runningInstance ? 'Stop Pipeline' : 'Run Pipeline'}
          </button>
        </div>
        {nodes.length === 0 && (
          <p className="vp-props-hint">Add nodes to the graph, then Run Pipeline. Saving is optional.</p>
        )}
        {nodes.length > 0 && !cameras.length && !isFileSource && (
          <p className="vp-props-hint">No cameras available. Add or connect a camera from the Cameras page, or use a VideoFile/ImageFile source with Location set.</p>
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
          <button
            type="button"
            className="vp-props-btn vp-props-btn-small"
            onClick={handleDeleteAllPipelines}
            disabled={loading || algorithms.length === 0}
            title="Delete all saved pipelines"
          >
            Delete all
          </button>
        </div>
        {algorithms.length === 0 && (
          <p className="vp-props-empty">No saved pipelines</p>
        )}
      </div>

      {/* Running Pipelines */}
      <div className="vp-props-section">
        <div className="vp-props-section-header">
          <h4 className="vp-props-section-title">Running Pipelines</h4>
          {displayInstances.length > 0 && (
            <button
              type="button"
              className="vp-props-btn vp-props-btn-small vp-props-btn-close"
              onClick={handleStopAll}
              disabled={loading}
              title="Remove all pipelines"
            >
              Remove all
            </button>
          )}
        </div>
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
        {displayInstances.length > 0 && (
          <p className="vp-props-hint">Click <strong>View tap</strong> to see live video. Add a <strong>StreamTap</strong> sink to the graph to see video in the node and in View tap alongside SaveVideo.</p>
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
