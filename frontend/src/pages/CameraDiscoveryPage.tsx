import React, { useState, useEffect } from 'react';
import { fetchCameras, fetchCameraDetails, fetchCameraCapabilities, fetchCameraControls, CameraDetails, CameraCapabilities, CameraControl } from '../utils/cameraApi';
import { Camera } from '../types';
import '../styles/CameraDiscoveryPage.css';

interface CameraNamingFormProps {
  cameraId: string;
  currentPosition?: string;
  currentSide?: string;
  onSave: (position: string, side?: string) => void;
  onCancel: () => void;
}

const CameraNamingForm: React.FC<CameraNamingFormProps> = ({
  currentPosition,
  currentSide,
  onSave,
  onCancel,
}) => {
  const [position, setPosition] = useState(currentPosition || '');
  const [side, setSide] = useState(currentSide || '');

  const previewName = position
    ? `${position}${side ? `-${side}` : ''}`
    : 'position';

  return (
    <div className="camera-naming-form">
      <h4>Set Camera Name</h4>
      <div className="naming-controls">
        <div className="naming-field">
          <label>Position:</label>
          <select
            value={position}
            onChange={(e) => setPosition(e.target.value)}
            className="select"
          >
            <option value="">Select position</option>
            <option value="front">Front</option>
            <option value="middle">Middle</option>
            <option value="back">Back</option>
          </select>
        </div>
        <div className="naming-field">
          <label>Side (optional):</label>
          <select
            value={side}
            onChange={(e) => setSide(e.target.value)}
            className="select"
          >
            <option value="">None</option>
            <option value="left">Left</option>
            <option value="right">Right</option>
          </select>
        </div>
        <div className="naming-actions">
          <button
            className="button"
            onClick={() => {
              if (position) {
                onSave(position, side || undefined);
              }
            }}
            disabled={!position}
          >
            Save
          </button>
          <button
            className="button button-secondary"
            onClick={onCancel}
          >
            Cancel
          </button>
        </div>
      </div>
      <div className="name-preview">
        Preview: <strong>{previewName}</strong>
      </div>
    </div>
  );
};

const CameraDiscoveryPage: React.FC = () => {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [expandedCameras, setExpandedCameras] = useState<Set<string>>(new Set());
  const [cameraDetails, setCameraDetails] = useState<Map<string, CameraDetails>>(new Map());
  const [cameraCapabilities, setCameraCapabilities] = useState<Map<string, CameraCapabilities>>(new Map());
  const [cameraControls, setCameraControls] = useState<Map<string, CameraControl[]>>(new Map());
  const [cameraNames, setCameraNames] = useState<Map<string, { position: string; side?: string }>>(new Map());
  const [cameraUseCases, setCameraUseCases] = useState<Map<string, string>>(new Map());
  const [editingCamera, setEditingCamera] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadCameras();
    // Poll every 2 seconds for hot-plug detection
    const interval = setInterval(loadCameras, 2000);
    return () => clearInterval(interval);
  }, []);

  const loadCameras = async () => {
    try {
      const cameraList = await fetchCameras();
      setCameras(cameraList);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load cameras');
    }
  };

  const toggleExpand = async (cameraId: string) => {
    const newExpanded = new Set(expandedCameras);
    if (newExpanded.has(cameraId)) {
      newExpanded.delete(cameraId);
    } else {
      newExpanded.add(cameraId);
      // Load details if not already loaded
      if (!cameraDetails.has(cameraId)) {
        setLoading(true);
        try {
          const [details, capabilities, controls] = await Promise.all([
            fetchCameraDetails(cameraId),
            fetchCameraCapabilities(cameraId),
            fetchCameraControls(cameraId),
          ]);
          setCameraDetails(new Map(cameraDetails).set(cameraId, details));
          setCameraCapabilities(new Map(cameraCapabilities).set(cameraId, capabilities));
          setCameraControls(new Map(cameraControls).set(cameraId, controls));
        } catch (err) {
          setError(err instanceof Error ? err.message : 'Failed to load camera details');
        } finally {
          setLoading(false);
        }
      }
    }
    setExpandedCameras(newExpanded);
  };

  useEffect(() => {
    // Load camera names and use cases when cameras are loaded
    const loadCameraConfig = async () => {
      for (const camera of cameras) {
        try {
          // Load camera name
          const nameResponse = await fetch(`/api/cameras/${camera.id}/name`);
          if (nameResponse.ok) {
            const nameConfig = await nameResponse.json();
            if (nameConfig.name) {
              setCameraNames(prev => new Map(prev).set(camera.id, {
                position: nameConfig.position || '',
                side: nameConfig.side || undefined
              }));
            }
          }
          
          // Load camera use case from settings
          const settingsResponse = await fetch(`/api/cameras/${camera.id}/settings`);
          if (settingsResponse.ok) {
            const settingsData = await settingsResponse.json();
            const useCase = settingsData.requested?.use_case || 'apriltag';
            setCameraUseCases(prev => new Map(prev).set(camera.id, useCase));
          }
        } catch (err) {
          // Ignore errors for config loading
        }
      }
    };
    if (cameras.length > 0) {
      loadCameraConfig();
    }
  }, [cameras]);

  const handleSaveCameraName = async (cameraId: string, position: string, side?: string) => {
    try {
      const response = await fetch(`/api/cameras/${cameraId}/name`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ position, side }),
      });
      
      if (!response.ok) {
        throw new Error('Failed to save camera name');
      }
      
      setCameraNames(prev => new Map(prev).set(cameraId, { position, side }));
      setEditingCamera(null);
      
      // Reload cameras to update names
      loadCameras();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save camera name');
    }
  };

  const handleUseCaseChange = async (cameraId: string, useCase: string) => {
    try {
      const response = await fetch(`/api/cameras/${cameraId}/settings`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ use_case: useCase }),
      });
      
      if (!response.ok) {
        throw new Error('Failed to save use case');
      }
      
      setCameraUseCases(prev => new Map(prev).set(cameraId, useCase));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save use case');
    }
  };

  const copyToClipboard = async (cameraId: string) => {
    const details = cameraDetails.get(cameraId);
    const capabilities = cameraCapabilities.get(cameraId);
    const controls = cameraControls.get(cameraId);
    
    const fullData = {
      details,
      capabilities,
      controls,
    };
    
    try {
      await navigator.clipboard.writeText(JSON.stringify(fullData, null, 2));
      alert('Camera data copied to clipboard!');
    } catch (err) {
      alert('Failed to copy to clipboard');
    }
  };

  return (
    <div className="camera-discovery-page">
      <div className="discovery-header">
        <h2>Camera Discovery</h2>
        <button className="button" onClick={loadCameras} disabled={loading}>
          {loading ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {error && <div className="error-message">{error}</div>}

      {cameras.length === 0 ? (
        <div className="no-cameras">
          <p>No cameras found</p>
          <p className="hint">Connect a USB camera and wait a few seconds for it to appear</p>
        </div>
      ) : (
        <div className="camera-list">
          {cameras.map(camera => {
            const isExpanded = expandedCameras.has(camera.id);
            const details = cameraDetails.get(camera.id);
            const capabilities = cameraCapabilities.get(camera.id);
            const controls = cameraControls.get(camera.id);

            const nameConfig = cameraNames.get(camera.id);
            const useCase = cameraUseCases.get(camera.id) || 'apriltag';
            const isEditing = editingCamera === camera.id;
            
            return (
              <div key={camera.id} className="camera-card">
                <div className="camera-header">
                  <span className="expand-icon" onClick={() => toggleExpand(camera.id)}>
                    {isExpanded ? '▼' : '▶'}
                  </span>
                  <span className="camera-name" onClick={() => toggleExpand(camera.id)}>
                    {camera.name}
                  </span>
                  <span className="camera-id">{camera.id}</span>
                  <span className={`camera-status ${camera.available ? 'available' : 'unavailable'}`}>
                    {camera.available ? 'Available' : 'Unavailable'}
                  </span>
                  {!isEditing && (
                    <button
                      className="button button-small"
                      onClick={(e) => {
                        e.stopPropagation();
                        setEditingCamera(camera.id);
                      }}
                    >
                      {nameConfig ? 'Edit Name' : 'Set Name'}
                    </button>
                  )}
                </div>

                {isEditing && (
                  <CameraNamingForm
                    cameraId={camera.id}
                    currentPosition={nameConfig?.position}
                    currentSide={nameConfig?.side}
                    onSave={(position, side) => handleSaveCameraName(camera.id, position, side)}
                    onCancel={() => setEditingCamera(null)}
                  />
                )}

                {isExpanded && details && (
                  <div className="camera-details">
                    <div className="details-section">
                      <h3>Camera Configuration</h3>
                      <div className="details-grid">
                        <div>
                          <label>Use Case:</label>
                          <select
                            value={useCase}
                            onChange={(e) => handleUseCaseChange(camera.id, e.target.value)}
                            className="select"
                            style={{ marginTop: '4px', width: '200px' }}
                          >
                            <option value="apriltag">AprilTag</option>
                            <option value="perception">Perception</option>
                            <option value="object-detection">Object Detection</option>
                          </select>
                        </div>
                      </div>
                    </div>

                    <div className="details-section">
                      <h3>USB Information</h3>
                      {Object.keys(details.usb_info).length === 0 ? (
                        <p className="no-usb-info">No USB information available (may be platform device)</p>
                      ) : (
                        <div className="details-grid">
                          {details.usb_info.usb_version && (
                            <div className="usb-version-highlight">
                              <label>USB Version:</label> 
                              <span className={`usb-badge ${details.usb_info.usb_version.toLowerCase()}`}>
                                {details.usb_info.usb_version}
                              </span>
                            </div>
                          )}
                          {details.usb_info.vid && <div><label>VID:</label> {details.usb_info.vid}</div>}
                          {details.usb_info.pid && <div><label>PID:</label> {details.usb_info.pid}</div>}
                          {details.usb_info.serial && <div><label>Serial:</label> {details.usb_info.serial}</div>}
                          {details.usb_info.bus && <div><label>Bus:</label> {details.usb_info.bus}</div>}
                          {details.usb_info.port_path && <div><label>Port Path:</label> {details.usb_info.port_path}</div>}
                          {details.usb_info.negotiated_speed && (
                            <div><label>Speed:</label> {details.usb_info.negotiated_speed} Mbps</div>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="details-section">
                      <h3>Device Information</h3>
                      <div className="details-grid">
                        <div><label>Device Path:</label> {details.device_path}</div>
                        {details.kernel_info.driver && <div><label>Driver:</label> {details.kernel_info.driver}</div>}
                        {details.host_controller.lspci_entry && (
                          <div><label>Host Controller:</label> {details.host_controller.lspci_entry}</div>
                        )}
                      </div>
                    </div>

                    {capabilities && (
                      <div className="details-section">
                        <h3>Capabilities</h3>
                        {capabilities.formats.length > 0 && (
                          <div>
                            <label>Formats:</label>
                            <div className="formats-list">{capabilities.formats.join(', ')}</div>
                          </div>
                        )}
                        {capabilities.resolutions.length > 0 && (
                          <div>
                            <label>Resolutions & FPS:</label>
                            <div className="resolutions-list">
                              {capabilities.resolutions.map((fmtRes, idx) => (
                                <div key={idx} className="format-group">
                                  <strong>{fmtRes.format}:</strong>
                                  <div className="resolution-grid">
                                    {fmtRes.resolutions.map((r, i) => (
                                      <div key={i} className="resolution-item">
                                        <span className="resolution">
                                          {r.width}x{r.height}
                                        </span>
                                        {r.fps && r.fps.length > 0 && (
                                          <span className="fps-info">
                                            {r.fps.length === 1 
                                              ? `${r.fps[0]} fps`
                                              : `${Math.min(...r.fps)}-${Math.max(...r.fps)} fps`
                                            }
                                          </span>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                        {capabilities.fps_ranges && capabilities.fps_ranges.length > 0 && (
                          <div>
                            <label>FPS Details:</label>
                            <div className="fps-ranges-table">
                              <table>
                                <thead>
                                  <tr>
                                    <th>Format</th>
                                    <th>Resolution</th>
                                    <th>FPS Range</th>
                                    <th>Available FPS</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {capabilities.fps_ranges.map((range, idx) => (
                                    <tr key={idx}>
                                      <td>{range.format}</td>
                                      <td>{range.width}x{range.height}</td>
                                      <td>{range.min_fps}-{range.max_fps} fps</td>
                                      <td>{range.fps.join(', ')}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {controls && controls.length > 0 && (
                      <div className="details-section">
                        <h3>Controls</h3>
                        <table className="controls-table">
                          <thead>
                            <tr>
                              <th>Name</th>
                              <th>Current</th>
                              <th>Min</th>
                              <th>Max</th>
                              <th>Step</th>
                              <th>Default</th>
                            </tr>
                          </thead>
                          <tbody>
                            {controls.map((control, idx) => (
                              <tr key={idx}>
                                <td>{control.name}</td>
                                <td>{control.current ?? '-'}</td>
                                <td>{control.min ?? '-'}</td>
                                <td>{control.max ?? '-'}</td>
                                <td>{control.step ?? '-'}</td>
                                <td>{control.default ?? '-'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    <div className="details-actions">
                      <button
                        className="button button-secondary"
                        onClick={() => copyToClipboard(camera.id)}
                      >
                        Copy Full JSON to Clipboard
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default CameraDiscoveryPage;
