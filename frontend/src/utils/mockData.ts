import { DebugTreeNode, SystemInfo, Camera } from '../types';

export const mockSystemInfo: SystemInfo = {
  appName: 'PlanA',
  buildId: '2024.01.20-dev',
  health: 'OK',
  connection: 'connected',
};

export const mockDebugTreeNodes: DebugTreeNode[] = [
  {
    id: 'root',
    name: 'System',
    status: 'OK',
    reason: 'All systems operational',
    metrics: {
      fps: 30.0,
      latency: 16,
    },
    children: [
      {
        id: 'camera_manager',
        name: 'Camera Manager',
        status: 'OK',
        reason: 'Running',
        metrics: {
          fps: 30.0,
          latency: 2,
          drops: 0,
          lastUpdateAge: 16,
        },
        children: [
          {
            id: 'camera_discovery',
            name: 'Camera Discovery',
            status: 'OK',
            reason: '2 cameras found',
            metrics: {
              lastUpdateAge: 1000,
            },
          },
          {
            id: 'camera_capture',
            name: 'Camera Capture',
            status: 'OK',
            reason: 'Streaming',
            metrics: {
              fps: 30.0,
              latency: 1,
              drops: 0,
              lastUpdateAge: 16,
            },
          },
        ],
      },
      {
        id: 'vision_pipeline',
        name: 'Vision Pipeline',
        status: 'WARN',
        reason: 'No camera open',
        metrics: {
          fps: 0.0,
          latency: 0,
          lastUpdateAge: 5000,
        },
        children: [
          {
            id: 'preprocess',
            name: 'Preprocess',
            status: 'STALE',
            reason: 'No input',
            metrics: {
              fps: 0.0,
              lastUpdateAge: 5000,
            },
          },
          {
            id: 'detection',
            name: 'Tag Detection',
            status: 'STALE',
            reason: 'No input',
            metrics: {
              fps: 0.0,
              latency: 0,
              lastUpdateAge: 5000,
            },
          },
        ],
      },
      {
        id: 'webserver',
        name: 'Web Server',
        status: 'OK',
        reason: 'Listening on :8080',
        metrics: {
          lastUpdateAge: 0,
        },
      },
    ],
  },
];

export const mockCameras: Camera[] = [
  { id: 'cam1', name: 'USB Camera 1', available: true },
  { id: 'cam2', name: 'USB Camera 2', available: true },
];
