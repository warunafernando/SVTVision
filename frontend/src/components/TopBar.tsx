import React from 'react';
import { SystemInfo, HealthStatus } from '../types';
import '../styles/TopBar.css';

interface TopBarProps {
  systemInfo: SystemInfo;
}

const TopBar: React.FC<TopBarProps> = ({ systemInfo }) => {
  const getStatusClass = (status: HealthStatus): string => {
    return `status-indicator status-${status.toLowerCase()}`;
  };

  const getConnectionIcon = (): string => {
    switch (systemInfo.connection) {
      case 'connected':
        return '●';
      case 'reconnecting':
        return '◐';
      case 'disconnected':
        return '○';
      default:
        return '○';
    }
  };

  return (
    <div className="top-bar">
      <div className="top-bar-left">
        <span className="app-name">{systemInfo.appName}</span>
        <span className="build-id">build {systemInfo.buildId}</span>
      </div>
      <div className="top-bar-right">
        <div className="health-indicator">
          <span className={getStatusClass(systemInfo.health)}>
            {systemInfo.health}
          </span>
        </div>
        <div className="connection-indicator" title={systemInfo.connection === 'disconnected' ? 'Backend not reachable. Start with: ./start.sh (or set VITE_API_BASE if backend is on another host)' : ''}>
          <span className={`connection-status ${systemInfo.connection}`}>
            {getConnectionIcon()} {systemInfo.connection === 'disconnected' ? 'Unable to connect' : systemInfo.connection}
          </span>
        </div>
      </div>
    </div>
  );
};

export default TopBar;
