/**
 * API base URL for backend. Same machine: use current origin (window.location.origin + '/api').
 * Set VITE_API_BASE (e.g. http://192.168.68.84:8080) when frontend and backend are on different hosts/ports.
 */
const envBase = typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_BASE;
const baseUrl = (envBase && String(envBase).trim()) ? String(envBase).replace(/\/$/, '') : '';
const sameOrigin = typeof window !== 'undefined' ? window.location.origin + '/api' : '/api';
export const API_BASE = baseUrl ? baseUrl + '/api' : sameOrigin;
/** WebSocket origin (e.g. ws://192.168.68.84:8080) when VITE_API_BASE is set; else empty = use current host */
export const WS_ORIGIN = baseUrl ? baseUrl.replace(/^http/, 'ws') : '';
