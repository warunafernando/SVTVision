import { SystemInfo, DebugTreeNode } from '../types';
import { API_BASE } from './config';

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
