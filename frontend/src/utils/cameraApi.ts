import { Camera } from '../types';

const API_BASE = '/api';

export interface CameraDetails {
  id: string;
  device_path: string;
  name: string;
  usb_info: {
    vid?: string;
    pid?: string;
    serial?: string;
    bus?: string;
    port_path?: string;
    negotiated_speed?: string;
    usb_version?: string;
  };
  kernel_info: {
    driver?: string;
  };
  host_controller: {
    lspci_entry?: string;
  };
}

export interface CameraCapabilities {
  formats: string[];
  resolutions: Array<{
    format: string;
    resolutions: Array<{ 
      width: number; 
      height: number;
      fps?: number[];
    }>;
  }>;
  fps_ranges?: Array<{ 
    format: string;
    width: number;
    height: number;
    fps: number[];
    min_fps: number;
    max_fps: number;
  }>;
}

export interface CameraControl {
  name: string;
  current?: number;
  min?: number;
  max?: number;
  step?: number;
  default?: number;
}

export async function fetchCameras(): Promise<Camera[]> {
  const response = await fetch(`${API_BASE}/cameras`);
  if (!response.ok) {
    throw new Error(`Failed to fetch cameras: ${response.statusText}`);
  }
  const data = await response.json();
  return data.cameras || [];
}

export async function fetchCameraDetails(cameraId: string): Promise<CameraDetails> {
  const response = await fetch(`${API_BASE}/cameras/${cameraId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch camera details: ${response.statusText}`);
  }
  return await response.json();
}

export async function fetchCameraCapabilities(cameraId: string): Promise<CameraCapabilities> {
  const response = await fetch(`${API_BASE}/cameras/${cameraId}/capabilities`);
  if (!response.ok) {
    throw new Error(`Failed to fetch camera capabilities: ${response.statusText}`);
  }
  return await response.json();
}

export async function fetchCameraControls(cameraId: string): Promise<CameraControl[]> {
  const response = await fetch(`${API_BASE}/cameras/${cameraId}/controls`);
  if (!response.ok) {
    throw new Error(`Failed to fetch camera controls: ${response.statusText}`);
  }
  const data = await response.json();
  return data.controls || [];
}
