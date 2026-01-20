import React, { useState, useEffect, useRef } from 'react';
import { Camera, Stage, Detection } from '../types';
import '../styles/ViewerPane.css';

interface ViewerPaneProps {
  cameras: Camera[];
  selectedCameraId?: string;
  isCameraOpen?: boolean;
  onCameraSelect: (cameraId: string) => void;
}

interface StreamMetrics {
  fps: number;
  drops: number;
  frames_captured: number;
  last_frame_age: number; // in milliseconds
}

const ViewerPane: React.FC<ViewerPaneProps> = ({
  cameras,
  selectedCameraId,
  isCameraOpen = false,
  onCameraSelect,
}) => {
  const [selectedStage, setSelectedStage] = useState<Stage>('raw');
  const [detections] = useState<Detection[]>([]); // Mock data for now
  const [metrics, setMetrics] = useState<StreamMetrics>({
    fps: 0,
    drops: 0,
    frames_captured: 0,
    last_frame_age: 0
  });
  const [streamConnected, setStreamConnected] = useState(false);
  const [hasFrames, setHasFrames] = useState(false);
  
  const imgRef = useRef<HTMLImageElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const stages: { key: Stage; label: string }[] = [
    { key: 'raw', label: 'Raw' },
    { key: 'preprocess', label: 'Preprocess' },
    { key: 'detect_overlay', label: 'Detect Overlay' },
  ];

  // WebSocket connection for video streaming
  useEffect(() => {
    if (!selectedCameraId || !isCameraOpen || selectedStage !== 'raw') {
      // Close WebSocket if camera closed or stage changed
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
        setStreamConnected(false);
        setHasFrames(false);
      }
      return;
    }

    // Connect to WebSocket stream
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/stream?camera=${selectedCameraId}&stage=${selectedStage}`;
    
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log(`WebSocket connected for camera ${selectedCameraId}, stage ${selectedStage}`);
      setStreamConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.type === 'frame' && data.data) {
          // Set hasFrames first (even if imgRef not ready yet)
          setHasFrames(true);
          
          // Decode base64 frame data and set image src
          if (imgRef.current) {
            const frameData = `data:image/jpeg;base64,${data.data}`;
            imgRef.current.src = frameData;
          }
          
          // Update metrics
          if (data.metrics) {
            setMetrics({
              fps: data.metrics.fps || 0,
              drops: data.metrics.frames_dropped || data.metrics.drops || 0,
              frames_captured: data.metrics.frames_captured || 0,
              last_frame_age: data.metrics.last_frame_age || 0
            });
          }
        } else if (data.type === 'no_frame') {
          setHasFrames(false); // Reset when no frames
        } else {
          console.log('WebSocket: Unexpected message type:', data.type);
        }
      } catch (err) {
        console.error('Error parsing WebSocket message:', err, event.data);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setStreamConnected(false);
    };

    ws.onclose = () => {
      setStreamConnected(false);
    };

    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, [selectedCameraId, isCameraOpen, selectedStage]);

  const shouldShowPlaceholder = !(selectedCameraId && isCameraOpen && selectedStage === 'raw' && streamConnected && hasFrames);

  return (
    <div className="viewer-pane">
      <div className="viewer-header">
        <div className="viewer-header-left">
          <select
            className="camera-selector"
            value={selectedCameraId || ''}
            onChange={(e) => onCameraSelect(e.target.value)}
          >
            <option value="">Select Camera</option>
            {cameras && cameras.length > 0 ? (
              cameras.map(camera => {
                // Use custom_name if available, otherwise use name, otherwise use id
                const displayName = camera.custom_name || camera.name || camera.id;
                return (
                  <option key={camera.id} value={camera.id}>
                    {displayName}
                  </option>
                );
              })
            ) : (
              <option value="" disabled>No cameras available</option>
            )}
          </select>
          <div className="viewer-stats-inline">
            <span className={`stat ${streamConnected ? 'connected' : 'disconnected'}`}>
              {streamConnected ? '●' : '○'} Stream
            </span>
            <span className="stat">FPS: {(metrics.fps || 0).toFixed(1)}</span>
            <span className="stat">Drops: {metrics.drops}</span>
            <span className="stat">
              Last: {metrics.last_frame_age !== undefined ? `${metrics.last_frame_age}ms` : 'N/A'}
            </span>
          </div>
        </div>
      </div>

      <div className="viewer-tabs">
        {stages.map(stage => (
          <button
            key={stage.key}
            className={`viewer-tab ${selectedStage === stage.key ? 'active' : ''}`}
            onClick={() => setSelectedStage(stage.key)}
            disabled={stage.key !== 'raw' && selectedStage === stage.key}
          >
            {stage.label}
          </button>
        ))}
      </div>

      <div className="viewer-content">
        {/* Placeholder - ALWAYS render with content */}
        {!(selectedCameraId && isCameraOpen && selectedStage === 'raw' && streamConnected && hasFrames) && (
          <div className="viewer-placeholder">
            {selectedCameraId && isCameraOpen ? (
              !streamConnected ? (
                <>
                  <p>Connecting to stream...</p>
                  <p className="viewer-note">Camera: {selectedCameraId}</p>
                  <p className="viewer-note">Stage: {selectedStage}</p>
                </>
              ) : selectedStage !== 'raw' ? (
                <p>{selectedStage} view coming soon</p>
              ) : (
                <p>Stream connected - waiting for frames...</p>
              )
            ) : selectedCameraId ? (
              <>
                <p>Camera selected: {cameras.find(c => c.id === selectedCameraId)?.custom_name || cameras.find(c => c.id === selectedCameraId)?.name || selectedCameraId}</p>
                <p className="viewer-note">Click "Open Camera" to start streaming</p>
              </>
            ) : cameras.length > 0 ? (
              <>
                <p>Select a camera from the dropdown above</p>
                <p className="viewer-note">Available: {cameras.length} camera(s)</p>
              </>
            ) : (
              <>
                <p>No cameras available</p>
                <p className="viewer-note">Connect a camera and wait a few seconds</p>
              </>
            )}
          </div>
        )}
        {/* Always render image element (hidden when no frames) so imgRef is always available */}
        <img
          ref={imgRef}
          className="viewer-stream"
          alt={`Camera ${selectedCameraId || 'none'} - ${selectedStage}`}
          style={{ 
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            objectFit: 'contain',
            zIndex: hasFrames ? 200 : -1, // Hidden when no frames
            display: (selectedCameraId && isCameraOpen && selectedStage === 'raw' && streamConnected && hasFrames) ? 'block' : 'none'
          }}
          onLoad={() => {
            // Ensure hasFrames is set when image loads successfully
            if (!hasFrames) setHasFrames(true);
          }}
        />
      </div>

      <div className="detections-table">
        <div className="detections-header">
          <h4>Detections</h4>
        </div>
        <table>
          <thead>
            <tr>
              <th>Tag ID</th>
              <th>Count</th>
              <th>Last Seen</th>
              <th>Latency</th>
            </tr>
          </thead>
          <tbody>
            {detections.length === 0 ? (
              <tr>
                <td colSpan={4} className="no-detections">
                  No detections
                </td>
              </tr>
            ) : (
              detections.map((detection, index) => (
                <tr key={index}>
                  <td>{detection.tagId}</td>
                  <td>{detection.count}</td>
                  <td>{detection.lastSeen}ms ago</td>
                  <td>{detection.latency}ms</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default ViewerPane;
