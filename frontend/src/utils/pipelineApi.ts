import { API_BASE } from './config';

const LOG_PREFIX = '[Vision Pipeline]';

function log(context: string, ...args: unknown[]): void {
  if (typeof console !== 'undefined') console.log(LOG_PREFIX, context, ...args);
}

function logError(context: string, message: string, err?: unknown): void {
  if (typeof console !== 'undefined') console.error(LOG_PREFIX, context, message, err ?? '');
}

export interface PipelineInstance {
  id: string;
  algorithm_id: string;
  target: string;
  state: 'running' | 'stopped' | 'error';
  metrics?: Record<string, unknown>;
}

export async function fetchPipelineInstances(): Promise<PipelineInstance[]> {
  const response = await fetch(`${API_BASE}/pipelines`, {
    cache: 'no-store',
    headers: { Pragma: 'no-cache', 'Cache-Control': 'no-cache' },
  });
  if (!response.ok) {
    throw new Error(`Failed to fetch pipelines: ${response.statusText}`);
  }
  const data = await response.json();
  const instances = data.instances || [];
  const ids = instances.map((i: PipelineInstance) => i.id);
  log('GET pipelines response', { count: instances.length, ids, raw: data });
  return instances;
}

export async function startPipeline(
  algorithmId: string,
  target: string
): Promise<{ id: string; state: string }> {
  log('POST start pipeline', { algorithmId, target });
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
    const msg = (err as { detail?: string }).detail || `Failed to start pipeline: ${response.statusText}`;
    logError('POST start pipeline', msg);
    throw new Error(msg);
  }
  const result = await response.json();
  log('POST start pipeline response', { id: result?.id, state: result?.state, full: result });
  return result;
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
  log('GET taps', { instanceId });
  const response = await fetch(`${API_BASE}/vp/taps/${instanceId}`);
  if (!response.ok) {
    logError('GET taps', `Failed to fetch taps: ${response.statusText}`);
    throw new Error(`Failed to fetch taps: ${response.statusText}`);
  }
  const data = await response.json();
  const taps = data.taps || {};
  log('GET taps response', { instanceId, tapCount: Object.keys(taps).length });
  return taps;
}
