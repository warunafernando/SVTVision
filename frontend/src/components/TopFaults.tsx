import React, { useState, useEffect } from 'react';
import '../styles/TopFaults.css';

interface Fault {
  path: string;
  node_id: string;
  name: string;
  status: 'OK' | 'WARN' | 'STALE' | 'ERROR';
  reason: string;
  metrics: {
    fps?: number;
    latency?: number;
    drops?: number;
    lastUpdateAge?: number;
  };
}

interface TopFaultsProps {
  maxFaults?: number;
}

const TopFaults: React.FC<TopFaultsProps> = ({ maxFaults = 5 }) => {
  const [faults, setFaults] = useState<Fault[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const apiBase = typeof window !== 'undefined' ? window.location.origin : '';
    const url = `${apiBase}/api/debug/top-faults?max_faults=${maxFaults}`;

    const fetchFaults = async () => {
      try {
        const response = await fetch(url);
        if (!response.ok) {
          setLoading(false);
          return;
        }
        const data = await response.json();
        setFaults(data.faults || []);
        setLoading(false);
      } catch {
        // Do not log to console - avoids [ERROR] in ConsoleOutput panel
        setLoading(false);
      }
    };

    fetchFaults();
    const interval = setInterval(fetchFaults, 2000);
    return () => clearInterval(interval);
  }, [maxFaults]);

  const getStatusColor = (status: string): string => {
    switch (status) {
      case 'ERROR':
        return 'var(--status-error)';
      case 'STALE':
        return 'var(--status-stale)';
      case 'WARN':
        return 'var(--status-warn)';
      default:
        return 'var(--status-ok)';
    }
  };

  if (loading) {
    return (
      <div className="top-faults">
        <div className="top-faults-header">Top Faults</div>
        <div className="top-faults-content">Loading...</div>
      </div>
    );
  }

  if (faults.length === 0) {
    return (
      <div className="top-faults">
        <div className="top-faults-header">Top Faults</div>
        <div className="top-faults-content">
          <div className="no-faults">No faults detected</div>
        </div>
      </div>
    );
  }

  return (
    <div className="top-faults">
      <div className="top-faults-header">Top Faults</div>
      <div className="top-faults-content">
        {faults.map((fault, index) => (
          <div key={fault.node_id} className="fault-item">
            <div className="fault-header">
              <span
                className="fault-status-dot"
                style={{ backgroundColor: getStatusColor(fault.status) }}
              ></span>
              <span className="fault-name">{fault.name}</span>
              <span className="fault-status">{fault.status}</span>
            </div>
            <div className="fault-path">{fault.path}</div>
            <div className="fault-reason">{fault.reason}</div>
            {fault.metrics && (
              <div className="fault-metrics">
                {fault.metrics.fps !== undefined && (
                  <span className="metric">FPS: {fault.metrics.fps.toFixed(1)}</span>
                )}
                {fault.metrics.latency !== undefined && (
                  <span className="metric">Latency: {fault.metrics.latency}ms</span>
                )}
                {fault.metrics.drops !== undefined && (
                  <span className="metric">Drops: {fault.metrics.drops}</span>
                )}
                {fault.metrics.lastUpdateAge !== undefined && (
                  <span className="metric">Age: {fault.metrics.lastUpdateAge}ms</span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default TopFaults;
