import { VPNode, VPEdge } from '../types';

import { API_BASE } from './config';

/** Stage/source/sink from backend StageRegistry (palette discovery) */
export interface VPStageMeta {
  id: string;
  name: string;
  label?: string;
  type: 'stage' | 'source' | 'sink';
  stage_id?: string;
  source_type?: string;
  sink_type?: string;
  execution_type?: string;
  ports: { inputs: { name: string; type: string }[]; outputs: { name: string; type: string }[] };
  settings_schema?: unknown[];
}

export interface VPStagesResponse {
  stages: VPStageMeta[];
  sources: VPStageMeta[];
  sinks: VPStageMeta[];
}

export async function fetchVPStages(): Promise<VPStagesResponse> {
  const response = await fetch(`${API_BASE}/vp/stages`);
  if (!response.ok) {
    throw new Error(`Failed to fetch stages: ${response.statusText}`);
  }
  return response.json();
}

/** Stage 9: Add a custom stage (plugin-based). Palette auto-updates on next fetch. */
export async function addVPStage(stage: {
  id: string;
  name?: string;
  label?: string;
  type: 'stage';
  ports: { inputs: { name: string; type: string }[]; outputs: { name: string; type: string }[] };
  settings_schema?: unknown[];
}): Promise<{ ok: boolean; id: string }> {
  const response = await fetch(`${API_BASE}/vp/stages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(stage),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `Failed to add stage: ${response.statusText}`);
  }
  return response.json();
}

/** Stage 9: Remove a custom stage. Only custom stages can be removed. */
export async function removeVPStage(stageId: string): Promise<{ ok: boolean; id: string }> {
  const response = await fetch(`${API_BASE}/vp/stages/${encodeURIComponent(stageId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `Failed to remove stage: ${response.statusText}`);
  }
  return response.json();
}

export interface ValidateResult {
  valid: boolean;
  errors?: string[];
}

export async function validateGraph(
  nodes: VPNode[],
  edges: VPEdge[]
): Promise<ValidateResult> {
  const response = await fetch(`${API_BASE}/vp/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nodes, edges }),
  });
  if (!response.ok) {
    throw new Error(`Failed to validate: ${response.statusText}`);
  }
  return response.json();
}
