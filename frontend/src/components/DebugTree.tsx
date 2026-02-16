import React, { useState, useEffect } from 'react';
import { DebugTreeNode, HealthStatus } from '../types';
import '../styles/DebugTree.css';

interface DebugTreeProps {
  nodes: DebugTreeNode[];
  onNodeClick?: (node: DebugTreeNode) => void;
  selectedNodeId?: string;
}

const DebugTree: React.FC<DebugTreeProps> = ({ nodes, onNodeClick, selectedNodeId }) => {
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(
    new Set(nodes.map(n => n.id))
  );

  // When tree data loads, expand root and top-level nodes so Host, Camera Manager, Vision Pipeline, Stage timings, Web Server are visible
  useEffect(() => {
    if (nodes.length > 0) {
      setExpandedNodes((prev) => {
        const next = new Set(prev);
        nodes.forEach((n) => {
          next.add(n.id);
          (n.children || []).forEach((c) => next.add(c.id));
        });
        return next;
      });
    }
  }, [nodes]);

  const toggleExpand = (nodeId: string) => {
    const newExpanded = new Set(expandedNodes);
    if (newExpanded.has(nodeId)) {
      newExpanded.delete(nodeId);
    } else {
      newExpanded.add(nodeId);
    }
    setExpandedNodes(newExpanded);
  };

  const getStatusColor = (status: HealthStatus): string => {
    switch (status) {
      case 'OK':
        return 'var(--status-ok)';
      case 'WARN':
        return 'var(--status-warn)';
      case 'STALE':
        return 'var(--status-stale)';
      case 'ERROR':
        return 'var(--status-error)';
      default:
        return 'var(--text-secondary)';
    }
  };

  const renderNode = (node: DebugTreeNode, depth: number = 0): React.ReactNode => {
    const hasChildren = node.children && node.children.length > 0;
    const isExpanded = expandedNodes.has(node.id);
    const isSelected = selectedNodeId === node.id;
    const metrics = node.metrics || {};

    return (
      <div key={node.id} className="debug-tree-node">
        <div
          className={`debug-tree-row ${isSelected ? 'selected' : ''}`}
          style={{ paddingLeft: `${depth * 12 + 4}px` }}
          onClick={() => onNodeClick?.(node)}
        >
          {hasChildren && (
            <span
              className="expand-icon"
              onClick={(e) => {
                e.stopPropagation();
                toggleExpand(node.id);
              }}
            >
              {isExpanded ? '▼' : '▶'}
            </span>
          )}
          {!hasChildren && <span className="expand-icon-placeholder"></span>}
          
          <span
            className="status-dot"
            style={{ backgroundColor: getStatusColor(node.status) }}
          ></span>
          
          <span className="node-name">{node.name}</span>
          
          <span className="node-reason">{node.reason}</span>
          
          <div className="node-metrics">
            {metrics.cpu_percent !== undefined && metrics.cpu_percent !== null && (
              <span className="metric">CPU {Number(metrics.cpu_percent).toFixed(1)}%</span>
            )}
            {metrics.gpu_percent !== undefined && metrics.gpu_percent !== null && (
              <span className="metric">GPU {Number(metrics.gpu_percent)}%</span>
            )}
            {metrics.gpu_memory_used_mb !== undefined && metrics.gpu_memory_total_mb !== undefined && (
              <span className="metric">{Number(metrics.gpu_memory_used_mb).toFixed(0)}/{Number(metrics.gpu_memory_total_mb).toFixed(0)} MB</span>
            )}
            {metrics.fps !== undefined && (
              <span className="metric">{Number(metrics.fps).toFixed(1)} fps</span>
            )}
            {metrics.latency !== undefined && (
              <span className="metric">{Number(metrics.latency).toFixed(0)}ms</span>
            )}
            {metrics.drops !== undefined && (
              <span className="metric">{metrics.drops} drops</span>
            )}
            {metrics.tags_detected !== undefined && (
              <span className="metric">{metrics.tags_detected} tags</span>
            )}
            {metrics.frames_processed !== undefined && (
              <span className="metric">{metrics.frames_processed} frames</span>
            )}
            {metrics.lastUpdateAge !== undefined && (
              <span className="metric">{metrics.lastUpdateAge}ms ago</span>
            )}
            {metrics.ms !== undefined && (
              <span className="metric">{Number(metrics.ms).toFixed(1)} ms</span>
            )}
            {metrics.total_ms !== undefined && (
              <span className="metric">{Number(metrics.total_ms).toFixed(1)} ms total</span>
            )}
          </div>
        </div>
        
        {hasChildren && isExpanded && (
          <div className="debug-tree-children">
            {node.children!.map(child => renderNode(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="debug-tree">
      <div className="debug-tree-header">
        <h3>Debug Tree</h3>
      </div>
      <div className="debug-tree-content">
        {nodes.map(node => renderNode(node))}
      </div>
    </div>
  );
};

export default DebugTree;
