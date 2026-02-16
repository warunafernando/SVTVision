   import React, { useState, useEffect, useCallback } from 'react';
import {
  fetchAprilTagStatus,
  startAprilTagPipeline,
  stopAprilTagPipeline,
  fetchAprilTagSettings,
  applyAprilTagSettings,
  getAprilTagDebugFrameUrl,
  AprilTagStatus,
  AprilTagSettings,
} from '../utils/api';
import '../styles/AprilTagPage.css';

const DEBUG_STEPS = [
  { value: 'raw', label: 'Raw' },
  { value: 'preprocess', label: 'Preprocess' },
  { value: 'detect_overlay', label: 'Detect overlay' },
];

const AprilTagPage: React.FC = () => {
  const [status, setStatus] = useState<AprilTagStatus | null>(null);
  const [settings, setSettings] = useState<AprilTagSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedStep, setSelectedStep] = useState<string>('detect_overlay');
  const [frameTick, setFrameTick] = useState(0);
  const [editQuadDecimate, setEditQuadDecimate] = useState<string>('');
  const [editNthreads, setEditNthreads] = useState<string>('');

  const loadStatus = useCallback(async () => {
    try {
      const data = await fetchAprilTagStatus();
      setStatus(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load status');
      setStatus(null);
    }
  }, []);

  const loadSettings = useCallback(async () => {
    try {
      const data = await fetchAprilTagSettings();
      setSettings(data);
      setEditQuadDecimate(String(data.quad_decimate));
      setEditNthreads(String(data.nthreads));
    } catch {
      // Ignore if settings not available
    }
  }, []);

  useEffect(() => {
    loadStatus();
    loadSettings();
    const interval = setInterval(loadStatus, 2000);
    return () => clearInterval(interval);
  }, [loadStatus, loadSettings]);

  useEffect(() => {
    if (!status?.running) return;
    const t = setInterval(() => setFrameTick((n) => n + 1), 200);
    return () => clearInterval(t);
  }, [status?.running]);

  const handleStart = async () => {
    setLoading(true);
    setError(null);
    try {
      await startAprilTagPipeline();
      await loadStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Start failed');
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    setError(null);
    try {
      await stopAprilTagPipeline();
      await loadStatus();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Stop failed');
    } finally {
      setLoading(false);
    }
  };

  const handleApplySettings = async () => {
    const qd = parseFloat(editQuadDecimate);
    const nt = parseInt(editNthreads, 10);
    if (isNaN(qd) || qd < 0.5 || qd > 4) return;
    if (isNaN(nt) || nt < 1 || nt > 8) return;
    setLoading(true);
    setError(null);
    try {
      await applyAprilTagSettings({ quad_decimate: qd, nthreads: nt });
      await loadSettings();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Apply settings failed');
    } finally {
      setLoading(false);
    }
  };

  const debugFrameUrl = status?.running && status.cameras.length >= 2
    ? getAprilTagDebugFrameUrl(selectedStep) + (frameTick ? `&_t=${frameTick}` : '')
    : '';

  return (
    <div className="apriltag-page">
      <div className="apriltag-header">
        <h2>AprilTag</h2>
      </div>
      <div className="apriltag-content">
        {error && <div className="apriltag-error">{error}</div>}

        <section className="apriltag-controls">
          <div className="apriltag-status">
            <span className="apriltag-status-label">Status:</span>
            <span className={`apriltag-status-value ${status?.running ? 'running' : 'stopped'}`}>
              {status?.running ? 'Running' : 'Stopped'}
            </span>
            {status?.cameras?.length ? (
              <span className="apriltag-cameras"> ({status.cameras.length} camera(s))</span>
            ) : null}
          </div>
          <div className="apriltag-buttons">
            <button
              type="button"
              className="apriltag-btn apriltag-btn-start"
              onClick={handleStart}
              disabled={loading || status?.running === true}
            >
              Start
            </button>
            <button
              type="button"
              className="apriltag-btn apriltag-btn-stop"
              onClick={handleStop}
              disabled={loading || status?.running !== true}
            >
              Stop
            </button>
          </div>
        </section>

        {status?.metrics && (
          <section className="apriltag-metrics">
            <h3>Pipeline metrics</h3>
            <div className="apriltag-metrics-grid">
              <span>Pipeline FPS:</span>
              <span title="Frames per second through detection; can be lower than target when using CPU for two cameras.">
                {status.metrics.fps ?? '—'}
                {status.target_fps != null && (
                  <span className="apriltag-fps-target"> (target: {status.target_fps})</span>
                )}
              </span>
              <span>Frames processed:</span>
              <span>{status.metrics.frames_processed ?? '—'}</span>
              <span>Detections (latest):</span>
              <span>{status.metrics.latest_detections_count ?? '—'}</span>
              {status.metrics.detect_num_quads != null && (
                <>
                  <span>Quads (count):</span>
                  <span title="Number of quad candidates decoded (count, not ms). Higher values can increase CPU decode work.">
                    {status.metrics.detect_num_quads}
                  </span>
                </>
              )}
              {status.metrics.stage_timings_ms && (
                <>
                  <span>Stage timings (ms):</span>
                  <span title="preprocess, detect, detect_overlay">
                    {Object.entries(status.metrics.stage_timings_ms)
                      .map(([k, v]) => `${k}: ${v}`)
                      .join(' | ')}
                  </span>
                </>
              )}
            </div>
            {status.target_fps != null && (status.metrics.fps ?? 0) < status.target_fps * 0.9 && (
              <p className="apriltag-fps-note">Pipeline FPS is below camera target; both cameras are now processed in parallel. Use GPU detection to get closer to {status.target_fps} FPS.</p>
            )}
          </section>
        )}

        {settings && (
          <section className="apriltag-settings">
            <h3>Detector settings</h3>
            <p className="apriltag-settings-hint">
              quad_decimate: 1=full res, 2=4× fewer pixels (faster). nthreads: CPU cores for AprilTag.
            </p>
            <div className="apriltag-settings-grid">
              <label htmlFor="apriltag-quad-decimate">quad_decimate:</label>
              <input
                id="apriltag-quad-decimate"
                type="number"
                min={0.5}
                max={4}
                step={0.5}
                value={editQuadDecimate}
                onChange={(e) => setEditQuadDecimate(e.target.value)}
              />
              <label htmlFor="apriltag-nthreads">nthreads:</label>
              <input
                id="apriltag-nthreads"
                type="number"
                min={1}
                max={8}
                value={editNthreads}
                onChange={(e) => setEditNthreads(e.target.value)}
              />
            </div>
            <button
              type="button"
              className="apriltag-btn apriltag-btn-apply"
              onClick={handleApplySettings}
              disabled={loading}
            >
              Apply
            </button>
          </section>
        )}

        <section className="apriltag-viewer">
          <h3>Debug frame (both cameras)</h3>
          <div className="apriltag-step-select">
            <label htmlFor="apriltag-step">Step:</label>
            <select
              id="apriltag-step"
              value={selectedStep}
              onChange={(e) => setSelectedStep(e.target.value)}
            >
              {DEBUG_STEPS.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>
          <div className="apriltag-frame-wrap">
            {debugFrameUrl ? (
              <img
                src={debugFrameUrl}
                alt={`Debug ${selectedStep}`}
                className="apriltag-frame-img"
              />
            ) : (
              <div className="apriltag-frame-placeholder">
                {status?.running && status.cameras.length < 2
                  ? 'Open two AprilTag cameras to see composite.'
                  : status?.running
                    ? 'Loading…'
                    : 'Start the pipeline to view frames.'}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};

export default AprilTagPage;
