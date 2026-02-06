/**
 * Inline StreamTap preview - small video when pipeline is running.
 * Size: 2x width, 4x height (160px × 320px base → 320px × 480px).
 */

import React, { useState, useEffect, useRef } from 'react';
import { getWsBaseUrl } from '../../utils/config';
import { fetchStreamTaps } from '../../utils/pipelineApi';
import '../../styles/vp/StreamTapPreview.css';

interface StreamTapPreviewProps {
  /** Running pipeline instance IDs. Show preview when non-empty. */
  instanceIds: string[];
}

const BASE_WIDTH = 160;
const BASE_HEIGHT = 120;
const WIDTH = BASE_WIDTH * 2;   // 2x width  → 320px
const HEIGHT = BASE_HEIGHT * 4; // 4x height → 480px

const StreamTapPreview: React.FC<StreamTapPreviewProps> = ({ instanceIds }) => {
  const [instanceId, setInstanceId] = useState<string | null>(null);
  const [tapId, setTapId] = useState<string | null>(null);
  const [taps, setTaps] = useState<Record<string, { tap_id: string; attach_point: string }>>({});
  const [connected, setConnected] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // When we have running instances, pick first and load its taps
  useEffect(() => {
    if (instanceIds.length === 0) {
      setInstanceId(null);
      setTapId(null);
      setTaps({});
      return;
    }
    const first = instanceIds[0];
    setInstanceId(first);
    fetchStreamTaps(first)
      .then((t) => {
        setTaps(t);
        const ids = Object.keys(t);
        setTapId(ids.length > 0 ? ids[0] : null);
      })
      .catch(() => {
        setTaps({});
        setTapId(null);
      });
  }, [instanceIds.join(',')]);

  // WebSocket: connect when we have instanceId + tapId
  useEffect(() => {
    if (!instanceId || !tapId) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setConnected(false);
      return;
    }
    const wsUrl = `${getWsBaseUrl()}/ws/vp/tap/${instanceId}/${encodeURIComponent(tapId)}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    setConnected(false);

    ws.onopen = () => setConnected(true);
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'frame' && data.data && imgRef.current) {
          imgRef.current.src = `data:image/jpeg;base64,${data.data}`;
        }
      } catch {
        // ignore
      }
    };
    ws.onclose = () => setConnected(false);

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [instanceId, tapId, wsHost]);

  if (instanceIds.length === 0) return null;

  const tapIds = Object.keys(taps);

  return (
    <div className="vp-streamtap-preview" style={{ width: WIDTH, height: HEIGHT }}>
      <div className="vp-streamtap-preview-header">
        <span className="vp-streamtap-preview-title">StreamTap</span>
        <span className={`vp-streamtap-preview-status ${connected ? 'connected' : 'disconnected'}`}>
          {connected ? '●' : '○'}
        </span>
      </div>
      {tapIds.length === 0 ? (
        <div className="vp-streamtap-preview-placeholder">
          No tap — add StreamTap sink
        </div>
      ) : (
        <>
          {tapIds.length > 1 && (
            <select
              className="vp-streamtap-preview-select"
              value={tapId || ''}
              onChange={(e) => setTapId(e.target.value || null)}
            >
              {tapIds.map((id) => (
                <option key={id} value={id}>{id}</option>
              ))}
            </select>
          )}
          <div className="vp-streamtap-preview-video">
            <img ref={imgRef} alt="StreamTap" />
          </div>
        </>
      )}
    </div>
  );
};

export default StreamTapPreview;
