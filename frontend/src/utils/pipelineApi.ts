import { API_BASE } from './config';

export interface PipelineInstance {
  id: string;
  algorithm_id: string;
  target: string;
  state: 'running' | 'stopped' | 'error';
  metrics?: Record<string, unknown>;
}

export async function fetchPipelineInstances(): Promise<PipelineInstance[]> {
  const response = await fetch(`${API_BASE}/pipelines`);
  if (!response.ok) {
    throw new Error(`Failed to fetch pipelines: ${response.statusText}`);
  }
  const data = await response.json();
  return data.instances || [];
}

export async function startPipeline(
  algorithmId: string,
  target: string
): Promise<{ id: string; state: string }> {
  const response = await fetch(`${API_BASE}/pipelines`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      algorithm_id: algorithmId,
      target,
    }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to start pipeline: ${response.statusText}`);
  }
  return response.json();
}

export async function stopPipeline(instanceId: string): Promise<{ id: string; state: string }> {
  const response = await fetch(`${API_BASE}/pipelines/${instanceId}/stop`, {
    method: 'POST',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to stop pipeline: ${response.statusText}`);
  }
  return response.json();
}

/** List StreamTaps for a running pipeline instance (Stage 7). */
export async function fetchStreamTaps(instanceId: string): Promise<Record<string, { tap_id: string; attach_point: string; frame_count?: number; has_frame?: boolean }>> {
  const response = await fetch(`${API_BASE}/vp/taps/${instanceId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch taps: ${response.statusText}`);
  }
  const data = await response.json();
  return data.taps || {};
}
