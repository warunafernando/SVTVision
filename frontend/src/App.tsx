import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import TopBar from './components/TopBar';
import DebugTree from './components/DebugTree';
import ConsoleOutput from './components/ConsoleOutput';
import CamerasPage from './pages/CamerasPage';
import CameraDiscoveryPage from './pages/CameraDiscoveryPage';
import VisionPipelinePage from './pages/VisionPipelinePage';
import SettingsPage from './pages/SettingsPage';
import SelfTestPage from './pages/SelfTestPage';
import { fetchSystemInfo, fetchDebugTree } from './utils/api';
import { DebugTreeNode, SystemInfo } from './types';
import './styles/App.css';

const App: React.FC = () => {
  const [selectedNodeId, setSelectedNodeId] = useState<string>();
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [debugTreeNodes, setDebugTreeNodes] = useState<DebugTreeNode[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<'connected' | 'reconnecting' | 'disconnected'>('reconnecting');

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
        setTimeout(() => {
          setConnectionStatus('reconnecting');
          loadData();
        }, 2000);
      }
    };

    // Brief delay so backend is ready when just started on same machine
    const t = setTimeout(loadData, 300);
    const interval = setInterval(loadData, 2000);
    return () => {
      clearTimeout(t);
      clearInterval(interval);
    };
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
    <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
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
              <Route path="/vision-pipeline" element={<VisionPipelinePage />} />
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
    { path: '/vision-pipeline', label: 'Vision Pipeline' },
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
