import React, { useState, useEffect } from 'react';
import ViewerPane from '../components/ViewerPane';
import ControlsPane from '../components/ControlsPane';
import { fetchCameras } from '../utils/cameraApi';
import { Camera } from '../types';
import '../styles/CamerasPage.css';

const CamerasPage: React.FC = () => {
  const [selectedCameraId, setSelectedCameraId] = useState<string>();
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadCameras();
    // Poll every 2 seconds for updates
    const interval = setInterval(loadCameras, 2000);
    return () => clearInterval(interval);
  }, []);

  const loadCameras = async () => {
    try {
      const cameraList = await fetchCameras();
      setCameras(cameraList);
      setError(null);
      
      if (cameraList.length === 0) {
        console.warn('No cameras found');
      }
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message : 'Failed to load cameras';
      console.error('Failed to load cameras:', errorMsg);
      setError(errorMsg);
      setCameras([]);
    }
  };

  const handleCameraOpen = async () => {
    if (!selectedCameraId) {
      setError('No camera selected');
      return;
    }

    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`/api/cameras/${selectedCameraId}/open`, {
        method: 'POST'
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to open camera');
      }
      
      setIsCameraOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to open camera');
      setIsCameraOpen(false);
    } finally {
      setLoading(false);
    }
  };

  const handleCameraClose = async () => {
    if (!selectedCameraId) {
      return;
    }

    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`/api/cameras/${selectedCameraId}/close`, {
        method: 'POST'
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to close camera');
      }
      
      setIsCameraOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to close camera');
    } finally {
      setLoading(false);
    }
  };

  // Auto-select first camera when cameras load
  useEffect(() => {
    if (cameras.length > 0 && !selectedCameraId) {
      setSelectedCameraId(cameras[0].id);
    }
  }, [cameras]); // Only depend on cameras, not selectedCameraId to avoid loops

  // Check camera status when selected
  useEffect(() => {
    if (!selectedCameraId) {
      setIsCameraOpen(false);
      return;
    }

    const checkStatus = async () => {
      try {
        const response = await fetch(`/api/cameras/${selectedCameraId}/status`);
        if (response.ok) {
          const data = await response.json();
          const wasOpen = isCameraOpen;
          const isOpen = data.open || false;
          
          // Always update, even if same, to ensure state is correct
          setIsCameraOpen(isOpen);
          
          // Debug logging
          if (wasOpen !== isOpen) {
            console.log(`Camera ${selectedCameraId} status changed: ${wasOpen} -> ${isOpen}`);
          } else if (!isOpen) {
            // Log when camera is still not open (for debugging auto-start detection)
            console.log(`Camera ${selectedCameraId} status check: open=${isOpen}, response:`, data);
          }
        } else {
          console.warn(`Camera status check failed: ${response.status}`);
        }
      } catch (err) {
        console.error('Error checking camera status:', err);
      }
    };

    // Check immediately and then poll
    checkStatus();
    const interval = setInterval(checkStatus, 1000); // Check every 1 second
    return () => clearInterval(interval);
  }, [selectedCameraId]); // Remove isCameraOpen from dependencies to avoid loops

  return (
    <div className="cameras-page">
      {error && (
        <div className="error-banner">
          {error}
        </div>
      )}
      <div className="cameras-main-content">
        <ViewerPane
          cameras={cameras}
          selectedCameraId={selectedCameraId}
          isCameraOpen={isCameraOpen}
          onCameraSelect={setSelectedCameraId}
        />
        <ControlsPane
          cameraId={selectedCameraId}
          isCameraOpen={isCameraOpen}
          onCameraOpen={handleCameraOpen}
          onCameraClose={handleCameraClose}
          loading={loading}
        />
      </div>
    </div>
  );
};

export default CamerasPage;
