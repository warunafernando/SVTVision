import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import TopBar from './components/TopBar';
import DebugTree from './components/DebugTree';
import ConsoleOutput from './components/ConsoleOutput';
import CamerasPage from './pages/CamerasPage';
import CameraDiscoveryPage from './pages/CameraDiscoveryPage';
import SettingsPage from './pages/SettingsPage';
import SelfTestPage from './pages/SelfTestPage';
import { fetchSystemInfo, fetchDebugTree } from './utils/api';
import { DebugTreeNode, SystemInfo } from './types';
import './styles/App.css';

const App: React.FC = () => {
  const [selectedNodeId, setSelectedNodeId] = useState<string>();
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [debugTreeNodes, setDebugTreeNodes] = useState<DebugTreeNode[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'reconnecting' | 'disconnected'>('disconnected');

  useEffect(() => {
    const loadData = async () => {
      try {
        const [sysInfo, treeNodes] = await Promise.all([
          fetchSystemInfo(),
          fetchDebugTree(),
        ]);
        setSystemInfo(sysInfo);
        setDebugTreeNodes(treeNodes);
        setConnectionStatus('connected');
      } catch (error) {
        console.error('Failed to load data:', error);
        setConnectionStatus('disconnected');
        // Fallback to reconnecting
        setTimeout(() => {
          setConnectionStatus('reconnecting');
          loadData();
        }, 2000);
      }
    };

    loadData();
    
    // Poll for updates every 2 seconds
    const interval = setInterval(loadData, 2000);
    return () => clearInterval(interval);
  }, []);

  const handleNodeClick = (node: DebugTreeNode) => {
    setSelectedNodeId(node.id);
    // TODO: Show detail panel with node information
  };

  // Use fallback data if backend not available
  const displaySystemInfo: SystemInfo = systemInfo || {
    appName: 'SVTVision',
    buildId: '2024.01.20-dev',
    health: 'ERROR',
    connection: connectionStatus,
  };

  return (
    <Router>
      <div className="app">
        <TopBar systemInfo={displaySystemInfo} />
        <div className="app-body">
          <div className="app-sidebar">
            <Navigation />
            <DebugTree
              nodes={debugTreeNodes.length > 0 ? debugTreeNodes : []}
              onNodeClick={handleNodeClick}
              selectedNodeId={selectedNodeId}
            />
          </div>
          <div className="app-main">
            <Routes>
              <Route path="/" element={<CamerasPage />} />
              <Route path="/cameras" element={<CamerasPage />} />
              <Route path="/discovery" element={<CameraDiscoveryPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/selftest" element={<SelfTestPage />} />
            </Routes>
          </div>
        </div>
        <ConsoleOutput />
      </div>
    </Router>
  );
};

const Navigation: React.FC = () => {
  const location = useLocation();

  const navItems = [
    { path: '/cameras', label: 'Cameras' },
    { path: '/discovery', label: 'Discovery' },
    { path: '/settings', label: 'Settings' },
    { path: '/selftest', label: 'Self-Test' },
  ];

  return (
    <nav className="navigation">
      {navItems.map(item => (
        <Link
          key={item.path}
          to={item.path}
          className={`nav-link ${location.pathname === item.path ? 'active' : ''}`}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
};

export default App;
