import React, { useState, useEffect, useRef } from 'react';
import '../styles/ConsoleOutput.css';

interface ConsoleMessage {
  id: number;
  timestamp: Date;
  level: 'error' | 'warn' | 'info' | 'log';
  message: string;
  section?: string; // Optional section/category (e.g., 'controls', 'camera', 'settings')
  data?: any;
}

const ConsoleOutput: React.FC = () => {
  const [messages, setMessages] = useState<ConsoleMessage[]>([]);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isVisible, setIsVisible] = useState(true); // Track if console is visible
  const [isPaused, setIsPaused] = useState(false);
  const [filterLevel, setFilterLevel] = useState<'all' | 'errors' | 'warnings' | 'logs'>('all');
  const [filterSection, setFilterSection] = useState<string>('all');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messageIdRef = useRef(0);
  const isPausedRef = useRef(false);

  useEffect(() => {
    isPausedRef.current = isPaused;
  }, [isPaused]);

  // Extract unique sections from messages (always include common sections)
  const messageSections = Array.from(
    new Set(messages.map(m => m.section).filter(Boolean) as string[])
  );
  const availableSections = ['controls', 'settings', 'camera', 'stream', 'api', 'errors', 'Vision Pipeline', ...messageSections]
    .filter((v, i, a) => a.indexOf(v) === i) // Remove duplicates
    .sort();

  // Toggle visibility when clicking header (hide if visible, show if hidden)
  const handleHeaderClick = () => {
    if (isVisible) {
      setIsVisible(false);
    } else {
      setIsVisible(true);
      setIsExpanded(false); // Reset to collapsed when showing
    }
  };

  // Toggle expand/collapse when clicking header (only if visible)
  const handleToggleExpand = (e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent header click handler
    if (isVisible) {
      setIsExpanded(!isExpanded);
    }
  };

  useEffect(() => {
    // Capture console errors and warnings
    const originalError = console.error;
    const originalWarn = console.warn;
    const originalLog = console.log;
    const originalInfo = console.info;

    const addMessage = (level: ConsoleMessage['level'], args: any[]) => {
      if (isPausedRef.current) return;
      const messageStr = args.map(arg => 
        typeof arg === 'object' ? JSON.stringify(arg) : String(arg)
      ).join(' ');
      
      // Extract section from message (backend [Section] prefix or [SETTINGS]/[CONTROLS], etc.)
      let section: string | undefined = undefined;
      const msgLower = messageStr.toLowerCase();
      const bracketMatch = messageStr.match(/^\[([^\]]+)\]\s*/);
      if (bracketMatch) {
        section = bracketMatch[1]; // e.g. App, Camera, Stream, Pipeline, Config
      } else if (messageStr.includes('[SETTINGS]') || messageStr.includes('[CONTROLS]')) {
        if (messageStr.includes('[SETTINGS]')) {
          section = 'settings';
        } else if (messageStr.includes('[CONTROLS]')) {
          section = 'controls';
        }
      } else if (messageStr.includes('📥') || messageStr.includes('📋') || messageStr.includes('✅') || messageStr.includes('⚠️') || messageStr.includes('🔄')) {
        // Control/settings related (with emoji markers)
        if (msgLower.includes('contrast') || msgLower.includes('brightness') || msgLower.includes('saturation') || 
            msgLower.includes('gain') || msgLower.includes('exposure') || msgLower.includes('control') ||
            msgLower.includes('using saved value') || msgLower.includes('using current camera value')) {
          section = 'controls';
        } else if (msgLower.includes('settings') || msgLower.includes('loaded saved settings') || msgLower.includes('save control')) {
          section = 'settings';
        } else {
          section = 'general';
        }
      } else if (msgLower.includes('error') || msgLower.includes('failed')) {
        section = 'errors';
      } else if (msgLower.includes('camera') && !msgLower.includes('control')) {
        section = 'camera';
      } else if (msgLower.includes('stream') || msgLower.includes('websocket')) {
        section = 'stream';
      } else if (msgLower.includes('api') || msgLower.includes('fetch')) {
        section = 'api';
      } else if (msgLower.includes('control') || msgLower.includes('contrast') || msgLower.includes('brightness') || 
                 msgLower.includes('saturation') || msgLower.includes('gain') || msgLower.includes('exposure')) {
        section = 'controls';
      } else if (msgLower.includes('setting') || msgLower.includes('config')) {
        section = 'settings';
      }
      
      const message: ConsoleMessage = {
        id: messageIdRef.current++,
        timestamp: new Date(),
        level,
        message: messageStr,
        section,
        data: args.length > 1 ? args : undefined
      };

      setMessages(prev => {
        const newMessages = [...prev, message];
        // Keep only last 200 messages for better filtering
        return newMessages.slice(-200);
      });
    };

    console.error = (...args: any[]) => {
      originalError(...args);
      addMessage('error', args);
    };

    console.warn = (...args: any[]) => {
      originalWarn(...args);
      addMessage('warn', args);
    };

    console.log = (...args: any[]) => {
      originalLog(...args);
      // Capture all logs for better filtering
      addMessage('log', args);
    };

    console.info = (...args: any[]) => {
      originalInfo(...args);
      // Capture all info messages
      addMessage('info', args);
    };

    // Capture unhandled errors
    const handleError = (event: ErrorEvent) => {
      addMessage('error', [event.message, event.filename, event.lineno]);
    };

    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      addMessage('error', ['Unhandled Promise Rejection:', event.reason]);
    };

    window.addEventListener('error', handleError);
    window.addEventListener('unhandledrejection', handleUnhandledRejection);

    return () => {
      console.error = originalError;
      console.warn = originalWarn;
      console.log = originalLog;
      console.info = originalInfo;
      window.removeEventListener('error', handleError);
      window.removeEventListener('unhandledrejection', handleUnhandledRejection);
    };
  }, [isExpanded]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Filter messages based on selected level and section
  const filteredMessages = messages.filter(msg => {
    // Filter by level
    if (filterLevel !== 'all') {
      if (filterLevel === 'errors' && msg.level !== 'error') return false;
      if (filterLevel === 'warnings' && msg.level !== 'warn') return false;
      if (filterLevel === 'logs' && msg.level !== 'log' && msg.level !== 'info') return false;
    }
    
    // Filter by section
    if (filterSection !== 'all') {
      if (!msg.section || msg.section !== filterSection) return false;
    }
    
    return true;
  });

  // Get visible messages (last 5 when collapsed, more when expanded)
  const visibleMessages = isExpanded ? filteredMessages : filteredMessages.slice(-5);
  const errorCount = messages.filter(m => m.level === 'error').length;
  const warnCount = messages.filter(m => m.level === 'warn').length;

  // Don't render at all if hidden
  if (!isVisible) {
    return (
      <div className="console-output console-hidden" onClick={handleHeaderClick}>
        <div className="console-header">
          <div className="console-header-left">
            <span className="console-title">Console</span>
            <span className="console-stats">
              {errorCount > 0 && <span className="stat-error">{errorCount} errors</span>}
              {warnCount > 0 && <span className="stat-warn">{warnCount} warnings</span>}
              <span className="console-toggle">▲</span>
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`console-output ${isExpanded ? 'expanded' : ''}`}>
      <div className="console-header">
        <div className="console-header-left" onClick={handleHeaderClick}>
          <span className="console-title">Console</span>
          <span className="console-stats">
            {errorCount > 0 && <span className="stat-error">{errorCount} errors</span>}
            {warnCount > 0 && <span className="stat-warn">{warnCount} warnings</span>}
            <span className="console-toggle" onClick={handleToggleExpand}>
              {isExpanded ? '▼' : '▲'}
            </span>
          </span>
        </div>
        <div className="console-filter" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            className={`console-pause-btn ${isPaused ? 'paused' : ''}`}
            onClick={() => setIsPaused(p => !p)}
            title={isPaused ? 'Resume console output' : 'Pause console to copy errors'}
          >
            {isPaused ? 'Resume' : 'Pause'}
          </button>
          {isPaused && <span className="console-paused-label">Paused — copy text, then click Resume</span>}
          <select
            className="console-filter-select"
            value={filterLevel}
            onChange={(e) => setFilterLevel(e.target.value as 'all' | 'errors' | 'warnings' | 'logs')}
            title="Filter by level"
          >
            <option value="all">All Levels</option>
            <option value="errors">Errors</option>
            <option value="warnings">Warnings</option>
            <option value="logs">Logs</option>
          </select>
          <select
            className="console-filter-select"
            value={filterSection}
            onChange={(e) => {
              setFilterSection(e.target.value);
              console.log('Filter section changed to:', e.target.value);
            }}
            title="Filter by section"
          >
            <option value="all">All Sections</option>
            {availableSections.map(section => (
              <option key={section} value={section}>
                {section.charAt(0).toUpperCase() + section.slice(1)}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="console-content">
        {visibleMessages.length > 0 && (
          <div className="console-line console-header-row">
            <span className="console-time">TIME</span>
            <span className="console-level">LEVEL</span>
            <span className="console-section">SECTION</span>
            <span className="console-message">MESSAGE</span>
          </div>
        )}
        {visibleMessages.length === 0 ? (
          <div className="console-empty">No messages</div>
        ) : (
          visibleMessages.map(msg => (
            <div key={msg.id} className={`console-line console-${msg.level}`}>
              <span className="console-time" title={msg.timestamp.toISOString()}>
                {msg.timestamp.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
              <span className="console-level">{msg.level.toUpperCase()}</span>
              <span className="console-section">{msg.section || '—'}</span>
              <span className="console-message">{msg.message}</span>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
};

export default ConsoleOutput;
