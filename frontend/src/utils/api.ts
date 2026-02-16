import { SystemInfo, DebugTreeNode } from '../types';
import { API_BASE } from './config';

export async function requestRestart(): Promise<{ ok: boolean }> {
  const response = await fetch(`${API_BASE}/system/restart`, { method: 'POST' });
  if (!response.ok) {
    throw new Error(`Restart failed: ${response.statusText}`);
  }
  return response.json();
}

export async function fetchSystemInfo(): Promise<SystemInfo> {
  const response = await fetch(`${API_BASE}/system`);
  if (!response.ok) {
    throw new Error(`Failed to fetch system info: ${response.statusText}`);
  }
  const data = await response.json();
  return {
    appName: data.appName || 'SVTVision',
    buildId: data.buildId || 'unknown',
    health: data.health || 'OK',
    connection: data.connection || 'connected',
  };
}

export interface AprilTagStatus {
  running: boolean;
  cameras: string[];
  metrics?: {
    fps?: number;
    frames_processed?: number;
    latest_detections_count?: number;
    stage_timings_ms?: Record<string, number>;
    stage_total_ms?: number;
    /** Number of quad candidates decoded (count, not ms). */
    detect_num_quads?: number;
  };
  /** Camera target FPS (e.g. 50); pipeline FPS may be lower when using CPU detection. */
  target_fps?: number;
}

export interface AprilTagSettings {
  quad_decimate: number;
  nthreads: number;
}

export async function fetchAprilTagStatus(): Promise<AprilTagStatus> {
  const response = await fetch(`${API_BASE}/apriltag/status`);
  if (!response.ok) throw new Error(`AprilTag status failed: ${response.statusText}`);
  return response.json();
}

export async function startAprilTagPipeline(): Promise<{ ok: boolean; started: string[] }> {
  const response = await fetch(`${API_BASE}/apriltag/start`, { method: 'POST' });
  if (!response.ok) throw new Error(`AprilTag start failed: ${response.statusText}`);
  return response.json();
}

export async function stopAprilTagPipeline(): Promise<{ ok: boolean; stopped: string[] }> {
  const response = await fetch(`${API_BASE}/apriltag/stop`, { method: 'POST' });
  if (!response.ok) throw new Error(`AprilTag stop failed: ${response.statusText}`);
  return response.json();
}

export async function fetchAprilTagSettings(): Promise<AprilTagSettings> {
  const response = await fetch(`${API_BASE}/apriltag/settings`);
  if (!response.ok) throw new Error(`AprilTag settings failed: ${response.statusText}`);
  return response.json();
}

export async function applyAprilTagSettings(settings: Partial<AprilTagSettings>): Promise<{ ok: boolean; applied: string[] }> {
  const response = await fetch(`${API_BASE}/apriltag/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  if (!response.ok) throw new Error(`Apply AprilTag settings failed: ${response.statusText}`);
  return response.json();
}

/** URL for composite debug frame image (both cameras) for a pipeline step. */
export function getAprilTagDebugFrameUrl(step: string): string {
  return `${API_BASE}/apriltag/debug-frame?step=${encodeURIComponent(step)}`;
}

export async function fetchDebugTree(): Promise<DebugTreeNode[]> {
  const response = await fetch(`${API_BASE}/debug/tree`);
  if (!response.ok) {
    throw new Error(`Failed to fetch debug tree: ${response.statusText}`);
  }
  const data = await response.json();
  
  // Convert single root node to array
  return [convertNode(data)];
}

function convertNode(node: any): DebugTreeNode {
  return {
    id: node.id,
    name: node.name,
    status: node.status,
    reason: node.reason || '',
    metrics: node.metrics || {},
    children: node.children ? node.children.map(convertNode) : [],
  };
}
