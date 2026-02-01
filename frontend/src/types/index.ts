export type HealthStatus = 'OK' | 'WARN' | 'STALE' | 'ERROR';
export type ConnectionStatus = 'connected' | 'reconnecting' | 'disconnected';

export interface DebugTreeNode {
  id: string;
  name: string;
  status: HealthStatus;
  reason: string;
  metrics: {
    fps?: number;
    latency?: number;
    drops?: number;
    lastUpdateAge?: number;
  };
  children?: DebugTreeNode[];
  expanded?: boolean;
}

export interface SystemInfo {
  appName: string;
  buildId: string;
  health: HealthStatus;
  connection: ConnectionStatus;
}

export interface Camera {
  id: string;
  name: string;
  available: boolean;
  custom_name?: string;
  device_path?: string;
  all_devices?: string[];
}

export type Stage = 'raw' | 'preprocess' | 'detect_overlay' | 'pose_overlay';

export interface Detection {
  tagId: number;
  count: number;
  lastSeen: number;
  latency: number;
}

/** Vision Pipeline graph types (Stage 1/2) */
export interface VPNode {
  id: string;
  type: 'source' | 'stage' | 'sink';
  stage_id?: string;
  source_type?: string;
  sink_type?: string;
  name?: string;  // Custom label (e.g. for user-named stages)
  config?: Record<string, unknown>;
  ports?: { inputs: { name: string; type: string }[]; outputs: { name: string; type: string }[] };
}

export interface VPEdge {
  id: string;
  source_node: string;
  source_port: string;
  target_node: string;
  target_port: string;
}

/** Pipeline graph for algorithm save/load */
export interface PipelineGraph {
  name?: string;
  description?: string;
  nodes: VPNode[];
  edges: VPEdge[];
  layout?: Record<string, { x: number; y: number }>;
}

export interface AlgorithmMeta {
  id: string;
  name: string;
}
