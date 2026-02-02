import React, { useState, useEffect, useRef, useCallback } from 'react';
import { fetchCameraCapabilities, CameraCapabilities, fetchCameraControls, CameraControl } from '../utils/cameraApi';
import { API_BASE } from '../utils/config';
import '../styles/ControlsPane.css';

interface ControlsPaneProps {
  cameraId?: string;
  isCameraOpen: boolean;
  onCameraOpen: () => void;
  onCameraClose: () => void;
  loading?: boolean;
}

interface ResolutionFpsOption {
  format: string;
  width: number;
  height: number;
  fps: number;
  label: string;
  value: string;
}

const ControlsPane: React.FC<ControlsPaneProps> = ({
  cameraId,
  isCameraOpen,
  onCameraOpen,
  onCameraClose,
  loading = false,
}) => {
  const [resolutionFpsOptions, setResolutionFpsOptions] = useState<ResolutionFpsOption[]>([]);
  const [selectedResolutionFps, setSelectedResolutionFps] = useState<string>('');
  const [useCase, setUseCase] = useState<string>('stream_only');
  const [cameraControls, setCameraControls] = useState<CameraControl[]>([]);
  const [controlValues, setControlValues] = useState<Record<string, number>>({});
  const [loadingCapabilities, setLoadingCapabilities] = useState(false);
  const [actualSettings, setActualSettings] = useState<{width?: number; height?: number; fps?: number; format?: string}>({});
  const [verificationStatus, setVerificationStatus] = useState<string>('');
  const applyControlTimeoutRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // Cleanup all timeouts on unmount
  useEffect(() => {
    return () => {
      Object.values(applyControlTimeoutRef.current).forEach(timeout => {
        clearTimeout(timeout);
      });
    };
  }, []);

  // Load capabilities and saved resolution/FPS when camera changes
  useEffect(() => {
    if (!cameraId) {
      setResolutionFpsOptions([]);
      setSelectedResolutionFps('');
      setUseCase('stream_only');
      return;
    }

    const loadCapabilitiesAndSettings = async () => {
      setLoadingCapabilities(true);
      try {
        // Load capabilities
        const capabilities: CameraCapabilities = await fetchCameraCapabilities(cameraId);
        
        // Build combined resolution/FPS options
        const options: ResolutionFpsOption[] = [];
        for (const fmtGroup of capabilities.resolutions) {
          for (const res of fmtGroup.resolutions) {
            if (res.fps && res.fps.length > 0) {
              // Create option for each FPS value
              for (const fps of res.fps) {
                const value = `${fmtGroup.format}:${res.width}x${res.height}:${fps}`;
                const label = `${res.width}x${res.height} @ ${fps} fps (${fmtGroup.format})`;
                options.push({
                  format: fmtGroup.format,
                  width: res.width,
                  height: res.height,
                  fps: fps,
                  label,
                  value
                });
              }
            } else {
              // No FPS info, create single option with default 30fps
              const value = `${fmtGroup.format}:${res.width}x${res.height}:30`;
              const label = `${res.width}x${res.height} @ 30 fps (${fmtGroup.format})`;
              options.push({
                format: fmtGroup.format,
                width: res.width,
                height: res.height,
                fps: 30,
                label,
                value
              });
            }
          }
        }
        
        // Sort by resolution (area) and FPS
        options.sort((a, b) => {
          const areaA = a.width * a.height;
          const areaB = b.width * b.height;
          if (areaA !== areaB) return areaB - areaA; // Larger first
          return b.fps - a.fps; // Higher FPS first
        });
        
        setResolutionFpsOptions(options);
        
        // Load saved resolution/FPS and use_case from settings endpoint (same as Discovery tab)
        try {
          const settingsResponse = await fetch(`${API_BASE}/cameras/${cameraId}/settings`);
          if (settingsResponse.ok) {
            const settingsData = await settingsResponse.json();
            const requested = settingsData.requested || {};
            const savedRes = requested.resolution;
            if (savedRes && savedRes.format && savedRes.width && savedRes.height && savedRes.fps) {
              const savedValue = `${savedRes.format}:${savedRes.width}x${savedRes.height}:${savedRes.fps}`;
              const optionExists = options.find(opt => opt.value === savedValue);
              if (optionExists) {
                setSelectedResolutionFps(savedValue);
              } else if (options.length > 0) {
                setSelectedResolutionFps(options[0].value);
              }
            } else if (options.length > 0) {
              setSelectedResolutionFps(options[0].value);
            }
            const savedUseCase = requested.use_case;
            if (savedUseCase === 'apriltag' || savedUseCase === 'stream_only' || savedUseCase === 'vision_pipeline') {
              setUseCase(savedUseCase);
            }
          } else if (options.length > 0) {
            setSelectedResolutionFps(options[0].value);
          }
        } catch (err) {
          if (options.length > 0) {
            setSelectedResolutionFps(options[0].value);
          }
        }
      } catch (err) {
        console.error('Failed to load camera capabilities:', err);
        setResolutionFpsOptions([]);
      } finally {
        setLoadingCapabilities(false);
      }
    };

    loadCapabilitiesAndSettings();
    
    // Load camera controls and saved settings
    const loadControls = async () => {
      try {
        // Load saved settings FIRST (before controls) to ensure they're available
        let savedSettings: Record<string, any> = {};
        try {
          const settingsResponse = await fetch(`${API_BASE}/cameras/${cameraId}/settings`);
          if (settingsResponse.ok) {
            const settingsData = await settingsResponse.json();
            savedSettings = settingsData.requested || {};
            console.log(`📥 [SETTINGS] Loaded saved settings for camera ${cameraId}:`, savedSettings);
            const savedControlKeys = Object.keys(savedSettings).filter(k => k !== 'resolution');
            console.log(`   📋 [SETTINGS] Saved control keys:`, savedControlKeys);
          } else {
            console.log(`⚠️ [SETTINGS] No saved settings for camera ${cameraId} (response not ok: ${settingsResponse.status})`);
          }
        } catch (err) {
          console.warn('❌ [SETTINGS] Failed to load saved settings:', err);
        }
        
        // Load controls from camera
        const controls = await fetchCameraControls(cameraId);
        console.log(`📦 [CONTROLS] Loaded ${controls.length} controls from camera`);
        setCameraControls(controls);
        
        // Initialize control values: use saved settings first, fallback to current camera values
        const values: Record<string, number> = {};
        controls.forEach(control => {
          // Extract control ID from name (e.g., "brightness" from "brightness 0x00980900 (int)")
          // Handle both formats: "brightness 0x00980900 (int)" and just "brightness"
          let controlId: string;
          const nameMatch = control.name.match(/^(\w+)\s+/);
          if (nameMatch) {
            controlId = nameMatch[1]; // Extract just the name part
          } else {
            controlId = control.name; // Use full name if no match
          }
          
          console.log(`   🔍 [CONTROLS] Processing control: "${control.name}" → ID: "${controlId}"`);
          
          // Check if we have a saved value for this control ID
          if (savedSettings.hasOwnProperty(controlId)) {
            // Convert to number if needed (could be string from JSON)
            const savedValue = typeof savedSettings[controlId] === 'number' 
              ? savedSettings[controlId] 
              : Number(savedSettings[controlId]);
            
            // Use the full control.name as the key (for consistency with how controls are rendered)
            values[control.name] = savedValue;
            console.log(`   ✅ [CONTROLS] Using saved value for "${controlId}": ${savedValue} (saved in settings)`);
          } else {
            // Fallback to current camera value
            if (control.current !== undefined) {
              values[control.name] = control.current;
              console.log(`   ⚠️ [CONTROLS] Using current camera value for "${controlId}": ${control.current} (no saved setting)`);
            } else {
              console.log(`   ⚠️ [CONTROLS] No value available for "${controlId}" (no saved setting, no current value)`);
            }
          }
        });
        
        console.log(`📋 [FINAL] Control values loaded for camera ${cameraId}:`, values);
        console.log(`   Total controls initialized: ${Object.keys(values).length}`);
        setControlValues(values);
      } catch (err) {
        console.error('❌ [ERROR] Failed to load camera controls:', err);
        setCameraControls([]);
      }
    };
    
    loadControls();
  }, [cameraId]);

  // Poll for actual settings when camera is open
  useEffect(() => {
    if (!cameraId || !isCameraOpen) {
      setActualSettings({});
      setVerificationStatus('');
      return;
    }

    const pollSettings = async () => {
      try {
        const response = await fetch(`${API_BASE}/cameras/${cameraId}/settings`);
        if (response.ok) {
          const data = await response.json();
          const actual = data.actual || {};
          setActualSettings(actual);
          
          // Verify against requested settings
          const requested = data.requested?.resolution;
          if (requested && actual.width && actual.height && actual.fps) {
            const widthMatch = actual.width === requested.width;
            const heightMatch = actual.height === requested.height;
            const fpsMatch = Math.abs(actual.fps - requested.fps) < 1.0;
            const formatMatch = actual.format === requested.format;
            
            if (widthMatch && heightMatch && fpsMatch && formatMatch) {
              setVerificationStatus('verified');
            } else {
              setVerificationStatus('mismatch');
            }
          } else {
            setVerificationStatus('');
          }
        }
      } catch (err) {
        // Ignore errors
      }
    };

    pollSettings();
    const interval = setInterval(pollSettings, 2000);
    return () => clearInterval(interval);
  }, [cameraId, isCameraOpen]);

  const handleResolutionFpsChange = async (value: string) => {
    setSelectedResolutionFps(value);
    const option = resolutionFpsOptions.find(opt => opt.value === value);
    if (option && cameraId) {
      try {
        await fetch(`${API_BASE}/cameras/${cameraId}/resolution`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            format: option.format,
            width: option.width,
            height: option.height,
            fps: option.fps
          })
        });
      } catch (err) {
        console.error('Failed to save resolution/FPS:', err);
      }
    }
  };

  // Apply control setting immediately (with debouncing)
  const applyControlSetting = async (controlName: string, value: number) => {
    if (!cameraId || !isCameraOpen) {
      return;
    }

    // Clear existing timeout for this control
    if (applyControlTimeoutRef.current[controlName]) {
      clearTimeout(applyControlTimeoutRef.current[controlName]);
    }

    // Debounce: wait 100ms after last change before applying
    applyControlTimeoutRef.current[controlName] = setTimeout(async () => {
      try {
        // Extract control ID from name (e.g., "brightness" from "brightness 0x00980900 (int)")
        const nameMatch = controlName.match(/^(\w+)\s+/);
        const controlId = nameMatch ? nameMatch[1] : controlName;
        
        const payload: Record<string, any> = {};
        payload[controlId] = value;

        const response = await fetch(`${API_BASE}/cameras/${cameraId}/controls`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (!response.ok) {
          console.error(`Failed to apply control ${controlName}`);
        } else {
          // Save to settings for persistence (via backend)
          const settingsResponse = await fetch(`${API_BASE}/cameras/${cameraId}/settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ [controlId]: value })
          });
          // Don't fail if settings save fails, just log
          if (!settingsResponse.ok) {
            console.warn(`Failed to save control ${controlId} to settings`);
          }
        }
      } catch (err) {
        console.error(`Failed to apply control ${controlName}:`, err);
      }
    }, 100);
  };

  // Reset all controls to default values
  const handleResetToDefaults = async () => {
    if (!cameraId || !isCameraOpen) {
      return;
    }

    try {
      // Build payload with all default values
      const payload: Record<string, any> = {};
      const newValues: Record<string, number> = {};

      cameraControls.forEach(control => {
        if (control.default !== undefined) {
          const nameMatch = control.name.match(/^(\w+)\s+/);
          const controlId = nameMatch ? nameMatch[1] : control.name;
          payload[controlId] = control.default;
          newValues[control.name] = control.default;
        }
      });

      if (Object.keys(payload).length === 0) {
        console.warn('No default values available for controls');
        return;
      }

      // Apply all defaults
      const response = await fetch(`${API_BASE}/cameras/${cameraId}/controls`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        throw new Error('Failed to reset controls to default');
      }

      // Update local state
      setControlValues(prev => ({ ...prev, ...newValues }));

      // Save to settings
      await fetch(`${API_BASE}/cameras/${cameraId}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      console.log('Controls reset to default values');
    } catch (err) {
      console.error('Failed to reset controls to default:', err);
    }
  };

  const currentOption = resolutionFpsOptions.find(opt => opt.value === selectedResolutionFps);

  return (
    <div className="controls-pane">
      <div className="controls-header">
        <h3>Camera Controls</h3>
      </div>

      <div className="controls-content">
        {!cameraId ? (
          <div className="controls-placeholder">
            <p>Select a camera to configure</p>
          </div>
        ) : (
          <>
            <div className="control-group controls-button-row">
              <button
                className={`button button-half ${isCameraOpen ? 'button-danger' : 'button-primary'}`}
                onClick={isCameraOpen ? onCameraClose : onCameraOpen}
                disabled={loading || !cameraId}
              >
                {loading ? '...' : (isCameraOpen ? 'Close' : 'Open')}
              </button>
              {isCameraOpen && cameraControls.length > 0 && (
                <button
                  className="button button-half button-secondary"
                  onClick={handleResetToDefaults}
                  disabled={loading}
                >
                  Reset
                </button>
              )}
            </div>

            <div className="control-group">
              <label>Use case</label>
              <select
                className="select"
                value={useCase}
                onChange={(e) => handleUseCaseChange(e.target.value)}
                disabled={isCameraOpen}
                title="AprilTag = Y-plane/grayscale. Set before opening."
              >
                <option value="apriltag">AprilTag (Y-plane)</option>
                <option value="stream_only">Stream only</option>
                <option value="vision_pipeline">Vision pipeline</option>
              </select>
              {isCameraOpen && (
                <div className="control-hint">Close camera to change use case</div>
              )}
            </div>

            <div className="control-group">
              <label>Resolution & FPS</label>
              {loadingCapabilities ? (
                <div className="loading-text">Loading capabilities...</div>
              ) : resolutionFpsOptions.length === 0 ? (
                <div className="no-options-text">No resolution/FPS options available</div>
              ) : (
                <select
                  className="select"
                  value={selectedResolutionFps}
                  onChange={(e) => handleResolutionFpsChange(e.target.value)}
                  disabled={isCameraOpen}
                >
                  {resolutionFpsOptions.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              )}
            </div>

            {/* Dynamically render all camera controls */}
            {cameraControls.map((control) => {
              // Extract control name (e.g., "brightness" from "brightness 0x00980900 (int)")
              const nameMatch = control.name.match(/^(\w+)\s+/);
              const displayName = nameMatch ? nameMatch[1].replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) : control.name;
              const controlType = control.name.includes('(bool)') ? 'bool' : 
                                  control.name.includes('(menu)') ? 'menu' : 'int';
              const currentValue = controlValues[control.name] ?? control.current ?? 0;

              if (controlType === 'bool') {
                return (
                  <div key={control.name} className="control-group">
                    <label>{displayName}</label>
                    <div className="control-input-group">
                      <label className="switch">
                        <input
                          type="checkbox"
                          checked={currentValue === 1}
                          onChange={(e) => {
                            const newValue = e.target.checked ? 1 : 0;
                            setControlValues({ ...controlValues, [control.name]: newValue });
                            applyControlSetting(control.name, newValue);
                          }}
                          disabled={!isCameraOpen}
                        />
                        <span className="slider-toggle"></span>
                      </label>
                      <span className="control-value">{currentValue === 1 ? 'On' : 'Off'}</span>
                    </div>
                  </div>
                );
              } else if (controlType === 'menu') {
                // For menu types, create dropdown if max is reasonable (e.g., < 10)
                if (control.max !== undefined && control.max < 10) {
                  const options = [];
                  for (let i = control.min ?? 0; i <= control.max; i++) {
                    options.push(i);
                  }
                  return (
                    <div key={control.name} className="control-group">
                      <label>{displayName}</label>
                      <select
                        className="select"
                        value={currentValue}
                        onChange={(e) => {
                          const newValue = parseInt(e.target.value);
                          setControlValues({ ...controlValues, [control.name]: newValue });
                          applyControlSetting(control.name, newValue);
                        }}
                        disabled={!isCameraOpen}
                      >
                        {options.map(opt => (
                          <option key={opt} value={opt}>{opt}</option>
                        ))}
                      </select>
                    </div>
                  );
                }
              }

              // Default: render as slider for int controls
              if (control.min !== undefined && control.max !== undefined) {
                const step = control.step ?? 1;
                return (
                  <div key={control.name} className="control-group">
                    <label>{displayName}</label>
                    <div className="control-input-group">
                      <input
                        type="range"
                        min={control.min}
                        max={control.max}
                        step={step}
                        value={currentValue}
                        onChange={(e) => {
                          const newValue = parseFloat(e.target.value);
                          setControlValues({ ...controlValues, [control.name]: newValue });
                          applyControlSetting(control.name, newValue);
                        }}
                        className="slider"
                        disabled={!isCameraOpen}
                      />
                      <span className="control-value">{currentValue}</span>
                    </div>
                  </div>
                );
              }

              return null;
            })}

            <div className="control-group verify-status">
              <div className="verify-header">Verify Status</div>
              <div className="verify-row">
                <span>Requested:</span>
                <span>
                  {currentOption 
                    ? `${currentOption.width}x${currentOption.height} @ ${currentOption.fps.toFixed(1)} fps (${currentOption.format})`
                    : 'Not set'}
                </span>
              </div>
              <div className="verify-row">
                <span>Actual:</span>
                <span className={verificationStatus === 'verified' ? 'status-ok' : verificationStatus === 'mismatch' ? 'status-warn' : ''}>
                  {actualSettings.width && actualSettings.height && actualSettings.fps
                    ? `${actualSettings.width}x${actualSettings.height} @ ${actualSettings.fps.toFixed(1)} fps${actualSettings.format ? ` (${actualSettings.format})` : ''}`
                    : isCameraOpen ? 'Reading...' : 'Camera not open'}
                </span>
              </div>
              {verificationStatus === 'verified' && (
                <div className="verify-status-indicator status-ok">
                  ✓ Settings verified
                </div>
              )}
              {verificationStatus === 'mismatch' && (
                <div className="verify-status-indicator status-warn">
                  ⚠ Settings mismatch
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default ControlsPane;
