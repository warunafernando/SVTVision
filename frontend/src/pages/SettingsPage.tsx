import React, { useState, useEffect } from 'react';
import { fetchCameras, fetchCameraControls } from '../utils/cameraApi';
import { API_BASE } from '../utils/config';
import { Camera } from '../types';
import '../styles/SettingsPage.css';

interface CameraSettings {
  resolution?: {
    format: string;
    width: number;
    height: number;
    fps: number;
  };
  [key: string]: any;
}

const SettingsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'camera' | 'global' | 'logging' | 'retention'>('camera');
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [selectedCameraId, setSelectedCameraId] = useState<string>('');
  const [cameraSettings, setCameraSettings] = useState<CameraSettings>({});
  const [cameraControls, setCameraControls] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    loadCameras();
  }, []);

  useEffect(() => {
    if (selectedCameraId) {
      loadCameraSettings();
    } else {
      setCameraSettings({});
      setCameraControls([]);
    }
  }, [selectedCameraId]);

  const loadCameras = async () => {
    try {
      const cameraList = await fetchCameras();
      setCameras(cameraList);
      if (cameraList.length > 0 && !selectedCameraId) {
        setSelectedCameraId(cameraList[0].id);
      }
    } catch (err) {
      console.error('Failed to load cameras:', err);
    }
  };

  const loadCameraSettings = async () => {
    if (!selectedCameraId) return;
    
    setLoading(true);
    setMessage(null);
    try {
      // Load saved settings
      const settingsResponse = await fetch(`${API_BASE}/cameras/${selectedCameraId}/settings`);
      if (settingsResponse.ok) {
        const settingsData = await settingsResponse.json();
        setCameraSettings(settingsData.requested || {});
      }

      // Load available controls
      const controls = await fetchCameraControls(selectedCameraId);
      setCameraControls(controls);
    } catch (err) {
      console.error('Failed to load camera settings:', err);
      setMessage({ type: 'error', text: 'Failed to load camera settings' });
    } finally {
      setLoading(false);
    }
  };

  const saveCameraSettings = async () => {
    if (!selectedCameraId) return;

    setSaving(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/cameras/${selectedCameraId}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cameraSettings),
      });

      if (response.ok) {
        setMessage({ type: 'success', text: 'Camera settings saved successfully!' });
        // Reload settings to get updated values
        await loadCameraSettings();
      } else {
        throw new Error('Failed to save settings');
      }
    } catch (err) {
      console.error('Failed to save camera settings:', err);
      setMessage({ type: 'error', text: 'Failed to save camera settings' });
    } finally {
      setSaving(false);
    }
  };

  const handleSettingChange = (key: string, value: any) => {
    setCameraSettings(prev => ({
      ...prev,
      [key]: value,
    }));
  };

  const handleControlChange = (controlId: string, value: number) => {
    setCameraSettings(prev => ({
      ...prev,
      [controlId]: value,
    }));
  };

  const tabs = [
    { id: 'camera' as const, label: 'Camera Settings' },
    { id: 'global' as const, label: 'Global Configuration' },
    { id: 'logging' as const, label: 'Logging' },
    { id: 'retention' as const, label: 'Retention' },
  ];

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h2>Settings</h2>
      </div>
      
      <div className="settings-tabs">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`settings-tab ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="settings-content">
        {activeTab === 'camera' && (
          <div className="camera-settings-tab">
            <div className="settings-section">
              <h3>Camera Selection</h3>
              <div className="form-group">
                <label>Select Camera:</label>
                <select
                  className="select"
                  value={selectedCameraId}
                  onChange={(e) => setSelectedCameraId(e.target.value)}
                  disabled={loading}
                >
                  <option value="">Select a camera</option>
                  {cameras.map(camera => {
                    const displayName = camera.custom_name || camera.name || camera.id;
                    return (
                      <option key={camera.id} value={camera.id}>
                        {displayName}
                      </option>
                    );
                  })}
                </select>
              </div>
            </div>

            {selectedCameraId && (
              <>
                <div className="settings-section">
                  <div className="settings-section-header">
                    <h3>Camera Settings</h3>
                    <button
                      className="button button-primary"
                      onClick={loadCameraSettings}
                      disabled={loading}
                    >
                      {loading ? 'Loading...' : 'Refresh Settings'}
                    </button>
                  </div>

                  {message && (
                    <div className={`settings-message ${message.type}`}>
                      {message.text}
                    </div>
                  )}

                  {loading ? (
                    <p className="loading-text">Loading camera settings...</p>
                  ) : (
                    <>
                      {/* Resolution Settings */}
                      {cameraSettings.resolution && (
                        <div className="form-group">
                          <label>Resolution:</label>
                          <div className="resolution-display">
                            {cameraSettings.resolution.width} x {cameraSettings.resolution.height} @ {cameraSettings.resolution.fps} fps ({cameraSettings.resolution.format})
                          </div>
                          <p className="settings-hint">
                            Resolution settings are managed from the Camera Controls pane
                          </p>
                        </div>
                      )}

                      {/* Camera Controls */}
                      {cameraControls.length > 0 && (
                        <div className="controls-group">
                          <h4>Camera Controls</h4>
                          {cameraControls.map(control => {
                            const controlId = control.name.match(/^(\w+)\s+/)?.[1] || control.name;
                            const displayName = controlId.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                            const currentValue = cameraSettings[controlId] ?? control.current ?? control.default ?? 0;
                            const isBoolean = control.name.includes('(bool)');

                            return (
                              <div key={control.name} className="form-group">
                                <label>{displayName}:</label>
                                {isBoolean ? (
                                  <div className="control-input-group">
                                    <label className="switch">
                                      <input
                                        type="checkbox"
                                        checked={currentValue === 1}
                                        onChange={(e) => handleControlChange(controlId, e.target.checked ? 1 : 0)}
                                      />
                                      <span className="slider-toggle"></span>
                                    </label>
                                    <span className="control-value">{currentValue === 1 ? 'On' : 'Off'}</span>
                                  </div>
                                ) : (
                                  <div className="control-input-group">
                                    <input
                                      type="range"
                                      min={control.min ?? 0}
                                      max={control.max ?? 100}
                                      step={control.step ?? 1}
                                      value={currentValue}
                                      onChange={(e) => handleControlChange(controlId, parseFloat(e.target.value))}
                                      className="slider"
                                    />
                                    <span className="control-value">{currentValue}</span>
                                  </div>
                                )}
                                {control.min !== undefined && control.max !== undefined && (
                                  <div className="control-range">
                                    Min: {control.min} | Max: {control.max} | Default: {control.default ?? 'N/A'}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {cameraControls.length === 0 && !loading && (
                        <p className="settings-hint">No camera controls available. Make sure the camera is connected.</p>
                      )}

                      <div className="settings-actions">
                        <button
                          className="button button-primary"
                          onClick={saveCameraSettings}
                          disabled={saving || loading}
                        >
                          {saving ? 'Saving...' : 'Save Settings'}
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </>
            )}

            {!selectedCameraId && (
              <div className="settings-section">
                <p className="settings-hint">Please select a camera to view and edit its settings.</p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'global' && (
          <div className="settings-section">
            <h3>Global Configuration</h3>
            <p className="coming-soon">Global configuration settings coming soon</p>
          </div>
        )}

        {activeTab === 'logging' && (
          <div className="settings-section">
            <h3>Logging</h3>
            <p className="coming-soon">Logging configuration coming soon</p>
          </div>
        )}

        {activeTab === 'retention' && (
          <div className="settings-section">
            <h3>Retention</h3>
            <p className="coming-soon">Retention settings coming soon</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default SettingsPage;
