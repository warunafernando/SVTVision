import React, { useState } from 'react';
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
            {node.metrics.fps !== undefined && (
              <span className="metric">{node.metrics.fps.toFixed(1)} fps</span>
            )}
            {node.metrics.latency !== undefined && (
              <span className="metric">{node.metrics.latency.toFixed(0)}ms</span>
            )}
            {node.metrics.drops !== undefined && (
              <span className="metric">{node.metrics.drops} drops</span>
            )}
            {node.metrics.lastUpdateAge !== undefined && (
              <span className="metric">{node.metrics.lastUpdateAge}ms ago</span>
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
