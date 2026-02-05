/**
 * Node Palette - Sources, Stages, Sinks + New Stage (save with name)
 * Fetches stages from StageRegistry API (GET /api/vp/stages); falls back to built-in if API unavailable.
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { VPNode } from '../../types';
import { fetchVPStages, addVPStage, removeVPStage } from '../../utils/vpApi';
import '../../styles/vp/Palette.css';

export interface PaletteItem {
  id: string;
  type: 'source' | 'stage' | 'sink';
  label: string;
  stage_id?: string;
  source_type?: string;
  sink_type?: string;
  ports: { inputs: { name: string; type: string }[]; outputs: { name: string; type: string }[] };
  /** Stage 9: true if stage is custom (plugin-added), from server or local */
  custom?: boolean;
}

const CUSTOM_STAGES_KEY = 'vp_custom_stages';

function loadCustomStages(): PaletteItem[] {
  try {
    const raw = localStorage.getItem(CUSTOM_STAGES_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveCustomStages(stages: PaletteItem[]) {
  localStorage.setItem(CUSTOM_STAGES_KEY, JSON.stringify(stages));
}

/** Fallback when StageRegistry API is unavailable */
const FALLBACK_ITEMS: PaletteItem[] = [
  { id: 'src_camera', type: 'source', label: 'CameraSource', source_type: 'camera', ports: { inputs: [], outputs: [{ name: 'frame', type: 'frame' }] } },
  { id: 'src_video', type: 'source', label: 'VideoFileSource', source_type: 'video_file', ports: { inputs: [], outputs: [{ name: 'frame', type: 'frame' }] } },
  { id: 'src_image', type: 'source', label: 'ImageFileSource', source_type: 'image_file', ports: { inputs: [], outputs: [{ name: 'frame', type: 'frame' }] } },
  { id: 'stage_preprocess', type: 'stage', label: 'Preprocess (CPU)', stage_id: 'preprocess_cpu', ports: { inputs: [{ name: 'frame', type: 'frame' }], outputs: [{ name: 'frame', type: 'frame' }] } },
  { id: 'stage_preprocess_gpu', type: 'stage', label: 'Preprocess (GPU)', stage_id: 'preprocess_gpu', ports: { inputs: [{ name: 'frame', type: 'frame' }], outputs: [{ name: 'frame', type: 'frame' }] } },
  { id: 'stage_detect', type: 'stage', label: 'AprilTag Detect (CPU)', stage_id: 'detect_apriltag_cpu', ports: { inputs: [{ name: 'frame', type: 'frame' }], outputs: [{ name: 'frame', type: 'frame' }, { name: 'detections', type: 'detections' }] } },
  { id: 'stage_overlay', type: 'stage', label: 'overlay', stage_id: 'overlay_cpu', ports: { inputs: [{ name: 'frame', type: 'frame' }, { name: 'detections', type: 'detections' }], outputs: [{ name: 'frame', type: 'frame' }] } },
  { id: 'sink_stream', type: 'sink', label: 'StreamTap', sink_type: 'stream_tap', ports: { inputs: [{ name: 'frame', type: 'frame' }], outputs: [{ name: 'frame', type: 'frame' }] } },
  { id: 'sink_video', type: 'sink', label: 'SaveVideo', sink_type: 'save_video', ports: { inputs: [{ name: 'frame', type: 'frame' }], outputs: [{ name: 'frame', type: 'frame' }] } },
  { id: 'sink_image', type: 'sink', label: 'SaveImage', sink_type: 'save_image', ports: { inputs: [{ name: 'frame', type: 'frame' }], outputs: [{ name: 'frame', type: 'frame' }] } },
  { id: 'sink_output', type: 'sink', label: 'SVTVisionOutput', sink_type: 'svt_output', ports: { inputs: [{ name: 'frame', type: 'frame' }], outputs: [] } },
];

interface PaletteProps {
  onNodeDragStart?: (item: PaletteItem) => void;
}

function apiToPaletteItem(meta: { id: string; name: string; label?: string; type: string; stage_id?: string; source_type?: string; sink_type?: string; ports: { inputs: { name: string; type: string }[]; outputs: { name: string; type: string }[] } }): PaletteItem {
  const type = meta.type as 'source' | 'stage' | 'sink';
  const label = meta.label || meta.name;
  if (type === 'source') {
    return {
      id: `src_${meta.id}`,
      type: 'source',
      label,
      source_type: meta.source_type ?? meta.id,
      ports: meta.ports,
    };
  }
  if (type === 'sink') {
    return {
      id: `sink_${meta.id}`,
      type: 'sink',
      label,
      sink_type: meta.sink_type ?? meta.id,
      ports: meta.ports,
    };
  }
  return {
    id: meta.id,
    type: 'stage',
    label,
    stage_id: meta.stage_id ?? meta.id,
    ports: meta.ports,
    custom: meta.custom,
  };
}

const loadRegistryItems = (): Promise<PaletteItem[] | null> =>
  fetchVPStages()
    .then((data) => {
      const items: PaletteItem[] = [];
      (data.sources || []).forEach((s) => items.push(apiToPaletteItem({ ...s, type: 'source' })));
      (data.stages || []).forEach((s) => items.push(apiToPaletteItem({ ...s, type: 'stage' })));
      (data.sinks || []).forEach((s) => items.push(apiToPaletteItem({ ...s, type: 'sink' })));
      return items;
    })
    .catch(() => null);

const Palette: React.FC<PaletteProps> = ({ onNodeDragStart }) => {
  const [registryItems, setRegistryItems] = useState<PaletteItem[] | null>(null);
  const [customStages, setCustomStages] = useState<PaletteItem[]>(loadCustomStages);
  const [showNewStageModal, setShowNewStageModal] = useState(false);
  const [newStageName, setNewStageName] = useState('');
  const [refreshing, setRefreshing] = useState(false);

  const doRefresh = useCallback(() => {
    setRefreshing(true);
    loadRegistryItems()
      .then((items) => {
        setRegistryItems(items);
      })
      .finally(() => setRefreshing(false));
  }, []);
  const refreshRef = useRef(doRefresh);
  refreshRef.current = doRefresh;

  useEffect(() => {
    loadRegistryItems().then(setRegistryItems);
  }, []);

  const handleDragStart = useCallback((e: React.DragEvent, item: PaletteItem) => {
    const node: VPNode = {
      id: '',
      type: item.type,
      stage_id: item.stage_id,
      source_type: item.source_type,
      sink_type: item.sink_type,
      name: item.label,
      ports: item.ports,
    };
    e.dataTransfer.setData('application/json', JSON.stringify({ ...node, paletteLabel: item.label }));
    e.dataTransfer.effectAllowed = 'copy';
    onNodeDragStart?.(item);
  }, [onNodeDragStart]);

  const handleSaveNewStage = useCallback(() => {
    const name = newStageName.trim();
    if (!name) return;
    const stageId = `custom_${name.toLowerCase().replace(/\s+/g, '_')}`;
    const stageDef = {
      id: stageId,
      name,
      label: name,
      type: 'stage' as const,
      ports: { inputs: [{ name: 'frame', type: 'frame' }], outputs: [{ name: 'frame', type: 'frame' }] },
    };
    addVPStage(stageDef)
      .then(() => {
        setNewStageName('');
        setShowNewStageModal(false);
        refreshRef.current();
      })
      .catch(() => {
        const item: PaletteItem = { ...stageDef, custom: true };
        const next = [...customStages, item];
        setCustomStages(next);
        saveCustomStages(next);
        setNewStageName('');
        setShowNewStageModal(false);
      });
  }, [newStageName, customStages]);

  const handleDeleteCustomStage = useCallback(
    (e: React.MouseEvent, item: PaletteItem) => {
      e.stopPropagation();
      e.preventDefault();
      if (!window.confirm(`Delete stage "${item.label}"?`)) return;
      const stageId = item.stage_id ?? item.id;
      if (item.custom) {
        removeVPStage(stageId)
          .then(() => refreshRef.current())
          .catch(() => {});
        return;
      }
      if (item.id.startsWith('custom_')) {
        const next = customStages.filter((s) => s.id !== item.id);
        setCustomStages(next);
        saveCustomStages(next);
      }
    },
    [customStages]
  );

  const baseItems = registryItems && registryItems.length > 0 ? registryItems : FALLBACK_ITEMS;
  const sources = baseItems.filter((i) => i.type === 'source');
  const stagesFromRegistry = baseItems.filter((i) => i.type === 'stage');
  const stages = [
    ...stagesFromRegistry,
    ...customStages.filter((c) => !stagesFromRegistry.some((s) => (s.stage_id ?? s.id) === (c.stage_id ?? c.id))),
  ];
  const sinks = baseItems.filter((i) => i.type === 'sink');

  const renderSection = (title: string, items: PaletteItem[]) => (
    <div className="vp-palette-section">
      <h4 className="vp-palette-section-title">{title}</h4>
      <ul className="vp-palette-list">
        {items.map((item) => (
          <li
            key={item.id}
            className="vp-palette-item"
            draggable
            onDragStart={(e) => handleDragStart(e, item)}
          >
            {item.label}
          </li>
        ))}
      </ul>
    </div>
  );

  return (
    <div className="vp-palette">
      <div className="vp-palette-header">
        <h3 className="vp-palette-title">Node Palette</h3>
        <button
          type="button"
          className="vp-palette-refresh"
          onClick={() => refreshRef.current()}
          disabled={refreshing}
          title="Refresh palette"
        >
          {refreshing ? '…' : '↻'}
        </button>
      </div>
      <div className="vp-palette-scroll">
      {renderSection('Sources', sources)}
      <div className="vp-palette-section">
        <h4 className="vp-palette-section-title">Stages</h4>
        <ul className="vp-palette-list">
          {stages.map((item) => (
            <li
              key={item.id}
              className="vp-palette-item"
              draggable
              onDragStart={(e) => handleDragStart(e, item)}
            >
              <span className="vp-palette-item-label">{item.label}</span>
              {(item.custom || item.id.startsWith('custom_')) && (
                <button
                  type="button"
                  className="vp-palette-item-delete"
                  onClick={(e) => handleDeleteCustomStage(e, item)}
                  onMouseDown={(e) => e.stopPropagation()}
                  title="Delete stage"
                >
                  ×
                </button>
              )}
            </li>
          ))}
        </ul>
        <button
          type="button"
          className="vp-palette-new-stage"
          onClick={() => setShowNewStageModal(true)}
        >
          + New Stage
        </button>
      </div>
      {renderSection('Sinks', sinks)}
      </div>

      {showNewStageModal && (
        <div className="vp-modal-overlay" onClick={() => setShowNewStageModal(false)}>
          <div className="vp-modal" onClick={(e) => e.stopPropagation()}>
            <h4 className="vp-modal-title">New Stage</h4>
            <p className="vp-modal-desc">Add a custom stage and save it with a name.</p>
            <input
              type="text"
              className="vp-modal-input"
              placeholder="Stage name (e.g. MyFilter)"
              value={newStageName}
              onChange={(e) => setNewStageName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSaveNewStage()}
            />
            <div className="vp-modal-actions">
              <button type="button" className="vp-modal-btn vp-modal-cancel" onClick={() => setShowNewStageModal(false)}>
                Cancel
              </button>
              <button type="button" className="vp-modal-btn vp-modal-save" onClick={handleSaveNewStage} disabled={!newStageName.trim()}>
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Palette;
export { FALLBACK_ITEMS as BUILTIN_ITEMS };
