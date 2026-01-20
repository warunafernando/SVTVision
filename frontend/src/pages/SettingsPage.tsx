import React from 'react';
import '../styles/SettingsPage.css';

const SettingsPage: React.FC = () => {
  return (
    <div className="settings-page">
      <div className="settings-content">
        <h2>Settings</h2>
        <div className="settings-section">
          <h3>Global Configuration</h3>
          <p className="coming-soon">Settings configuration coming soon</p>
        </div>
        <div className="settings-section">
          <h3>Logging</h3>
          <p className="coming-soon">Logging configuration coming soon</p>
        </div>
        <div className="settings-section">
          <h3>Retention</h3>
          <p className="coming-soon">Retention settings coming soon</p>
        </div>
      </div>
    </div>
  );
};

export default SettingsPage;
