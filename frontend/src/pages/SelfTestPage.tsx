import React, { useState } from 'react';
import '../styles/SelfTestPage.css';

interface TestResult {
  name: string;
  pass: boolean;
  message?: string;
  timestamp: number;
}

const SelfTestPage: React.FC = () => {
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<TestResult[]>([]);

  const runTest = async (testName: string) => {
    setRunning(true);
    try {
      const response = await fetch(`/api/selftest/run?test=${testName}`);
      const data = await response.json();
      setResults(prev => [...prev, {
        name: testName,
        pass: data.pass === true,
        message: data.message,
        timestamp: Date.now(),
      }]);
    } catch (error) {
      setResults(prev => [...prev, {
        name: testName,
        pass: false,
        message: `Error: ${error}`,
        timestamp: Date.now(),
      }]);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="selftest-page">
      <div className="selftest-content">
        <h2>Self-Test</h2>
        
        <div className="test-controls">
          <button
            className="button"
            onClick={() => runTest('smoke')}
            disabled={running}
          >
            Run Smoke Test
          </button>
        </div>

        <div className="test-results">
          <h3>Latest Results</h3>
          {results.length === 0 ? (
            <p className="no-results">No tests run yet</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Test</th>
                  <th>Status</th>
                  <th>Message</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {results.map((result, index) => (
                  <tr key={index}>
                    <td>{result.name}</td>
                    <td>
                      <span className={result.pass ? 'status-ok' : 'status-error'}>
                        {result.pass ? 'PASS' : 'FAIL'}
                      </span>
                    </td>
                    <td>{result.message || '-'}</td>
                    <td>{new Date(result.timestamp).toLocaleTimeString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
};

export default SelfTestPage;
