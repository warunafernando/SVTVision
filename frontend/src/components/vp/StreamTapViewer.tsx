/**
 * StreamTap viewer - connect to /ws/vp/tap/{instance_id}/{tap_id} and display frames.
 */

import React, { useState, useEffect, useRef } from 'react';
import { API_BASE } from '../../utils/config';
import { fetchStreamTaps } from '../../utils/pipelineApi';
import '../../styles/vp/StreamTapViewer.css';

interface StreamTapViewerProps {
  instanceId: string;
  onClose: () => void;
}

const StreamTapViewer: React.FC<StreamTapViewerProps> = ({ instanceId, onClose }) => {
  const [taps, setTaps] = useState<Record<string, { tap_id: string; attach_point: string; fps?: number }>>({});
  const [selectedTapId, setSelectedTapId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [frameCount, setFrameCount] = useState(0);
  const imgRef = useRef<HTMLImageElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const wsHost = API_BASE.startsWith('http')
    ? API_BASE.replace(/^http/, 'ws').replace(/\/api\/?$/, '')
    : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;

  useEffect(() => {
    let cancelled = false;
    fetchStreamTaps(instanceId)
      .then((t) => {
        if (!cancelled) {
          setTaps(t);
          const ids = Object.keys(t);
          if (ids.length === 1) setSelectedTapId(ids[0]);
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load taps');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [instanceId]);

  useEffect(() => {
    if (!selectedTapId) return;
    setError(null);
    const wsUrl = `${wsHost}/ws/vp/tap/${instanceId}/${encodeURIComponent(selectedTapId)}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    setConnected(false);
    setFrameCount(0);

    ws.onopen = () => setConnected(true);
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'error') {
          setError(data.message || 'StreamTap error');
          return;
        }
        if (data.type === 'frame' && data.data && imgRef.current) {
          imgRef.current.src = `data:image/jpeg;base64,${data.data}`;
          setFrameCount((n) => n + 1);
        }
      } catch {
        // ignore
      }
    };
    ws.onerror = () => {
      setError((e) => e || 'WebSocket error');
      console.error('[Vision Pipeline] StreamTap WebSocket error');
    };
    ws.onclose = (ev) => {
      setConnected(false);
      if (ev.code !== 1000 && ev.code !== 1005) {
        setError((e) => e || ev.reason || 'Connection closed');
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [instanceId, selectedTapId, wsHost]);

  const tapIds = Object.keys(taps);

  if (loading) {
    return (
      <div className="vp-streamtap-overlay" onClick={onClose}>
        <div className="vp-streamtap-modal" onClick={(e) => e.stopPropagation()}>
          <div className="vp-streamtap-header">
            <h4>StreamTap — {instanceId}</h4>
            <button type="button" className="vp-streamtap-close" onClick={onClose}>×</button>
          </div>
          <p className="vp-streamtap-loading">Loading taps...</p>
        </div>
      </div>
    );
  }

  if (tapIds.length === 0) {
    return (
      <div className="vp-streamtap-overlay" onClick={onClose}>
        <div className="vp-streamtap-modal" onClick={(e) => e.stopPropagation()}>
          <div className="vp-streamtap-header">
            <h4>StreamTap — {instanceId}</h4>
            <button type="button" className="vp-streamtap-close" onClick={onClose}>×</button>
          </div>
          <p className="vp-streamtap-empty">No StreamTaps in this pipeline. Add a StreamTap sink to your graph and run the pipeline.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="vp-streamtap-overlay" onClick={onClose}>
      <div className="vp-streamtap-modal" onClick={(e) => e.stopPropagation()}>
        <div className="vp-streamtap-header">
          <h4>StreamTap — {instanceId}</h4>
          <button type="button" className="vp-streamtap-close" onClick={onClose}>×</button>
        </div>
        {error && <p className="vp-streamtap-error">{error}</p>}
        <div className="vp-streamtap-toolbar">
          <label>
            Tap:{' '}
            <select
              value={selectedTapId || ''}
              onChange={(e) => setSelectedTapId(e.target.value || null)}
              className="vp-streamtap-select"
            >
              <option value="">Select...</option>
              {tapIds.map((id) => (
                <option key={id} value={id}>
                  {id} ({taps[id]?.attach_point || ''})
                </option>
              ))}
            </select>
          </label>
          <span className={`vp-streamtap-status ${connected ? 'connected' : 'disconnected'}`}>
            {connected ? '● Live' : '○ Connecting...'}
          </span>
          {connected && (
            <>
              <span className="vp-streamtap-frames">{frameCount} frames</span>
              {selectedTapId != null && taps[selectedTapId]?.fps != null && (
                <span className="vp-streamtap-fps">{taps[selectedTapId].fps} fps</span>
              )}
            </>
          )}
        </div>
        <div className="vp-streamtap-video">
          <img ref={imgRef} alt="StreamTap output" />
        </div>
      </div>
    </div>
  );
};

export default StreamTapViewer;
