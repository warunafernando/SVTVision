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
