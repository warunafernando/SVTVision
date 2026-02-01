import { PipelineGraph, AlgorithmMeta } from '../types';
import { API_BASE } from './config';
const LOG_PREFIX = '[Vision Pipeline]';

function log(group: string, ...args: unknown[]): void {
  const prefix = `${LOG_PREFIX} ${group}`;
  if (typeof console !== 'undefined') {
    console.groupCollapsed(prefix);
    console.log(prefix, ...args); // Include prefix so GUI console can filter by "Vision Pipeline"
    console.groupEnd();
  }
}

export async function fetchAlgorithms(): Promise<AlgorithmMeta[]> {
  const url = `${API_BASE}/algorithms`;
  log('GET algorithms', { url });
  const response = await fetch(url);
  log('GET algorithms response', { url, status: response.status, statusText: response.statusText });
  if (!response.ok) {
    throw new Error(`Failed to fetch algorithms: ${response.statusText}`);
  }
  const data = await response.json();
  return data.algorithms || [];
}

export async function fetchAlgorithm(id: string): Promise<PipelineGraph & { id: string; updated_at: string }> {
  const url = `${API_BASE}/algorithms/${id}`;
  log('GET algorithm', { url, id });
  const response = await fetch(url);
  log('GET algorithm response', { url, status: response.status });
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('Algorithm not found');
    }
    throw new Error(`Failed to fetch algorithm: ${response.statusText}`);
  }
  return response.json();
}

export async function createAlgorithm(graph: Partial<PipelineGraph>): Promise<{ id: string; name: string }> {
  const url = `${API_BASE}/algorithms`;
  const payload = {
    name: graph.name || 'Untitled',
    description: graph.description || '',
    nodes: graph.nodes || [],
    edges: graph.edges || [],
    layout: graph.layout || {},
  };
  log('POST create algorithm', { url, method: 'POST', payload });
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const bodyText = await response.text();
  log('POST create algorithm response', {
    url,
    method: 'POST',
    status: response.status,
    statusText: response.statusText,
    body: bodyText,
  });
  if (!response.ok) {
    const err = (() => {
      try {
        return JSON.parse(bodyText);
      } catch {
        return {};
      }
    })();
    throw new Error(err.detail || `Failed to create algorithm: ${response.status} ${response.statusText}`);
  }
  return JSON.parse(bodyText);
}

export async function updateAlgorithm(
  id: string,
  graph: Partial<PipelineGraph>
): Promise<{ id: string; name: string }> {
  const url = `${API_BASE}/algorithms/${id}`;
  const payload = {
    name: graph.name,
    description: graph.description,
    nodes: graph.nodes,
    edges: graph.edges,
    layout: graph.layout,
  };
  log('PUT update algorithm', { url, method: 'PUT', id, payload });
  const response = await fetch(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const bodyText = await response.text();
  log('PUT update algorithm response', {
    url,
    method: 'PUT',
    status: response.status,
    statusText: response.statusText,
    body: bodyText,
  });
  if (!response.ok) {
    const err = (() => {
      try {
        return JSON.parse(bodyText);
      } catch {
        return {};
      }
    })();
    throw new Error(err.detail || `Failed to update algorithm: ${response.status} ${response.statusText}`);
  }
  return JSON.parse(bodyText);
}

export async function deleteAlgorithm(id: string): Promise<void> {
  const url = `${API_BASE}/algorithms/${id}`;
  log('DELETE algorithm', { url, method: 'DELETE', id });
  const response = await fetch(url, {
    method: 'DELETE',
  });
  log('DELETE algorithm response', { url, status: response.status, statusText: response.statusText });
  if (!response.ok) {
    const bodyText = await response.text();
    const err = (() => {
      try {
        return JSON.parse(bodyText);
      } catch {
        return {};
      }
    })();
    throw new Error(err.detail || `Failed to delete algorithm: ${response.statusText}`);
  }
}
