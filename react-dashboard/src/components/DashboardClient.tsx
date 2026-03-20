import React from 'react';
import ServiceHealth from './ServiceHealth';
import ChatWidget from './ChatWidget';
import ZeroClawPanel from './ZeroClawPanel';
import ResearchPanel from './ResearchPanel';
import WireframeBoundary from './WireframeBoundary';

export default function DashboardClient() {
  return (
    <div className="dashboard-shell">
      <header className="top-bar">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h1 style={{ margin: 0, fontSize: '1.25rem' }}>🏠 gentoofoo (Local)</h1>
          <span className="badge">admin</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: '0.85rem', flexWrap: 'wrap' }}>
          <a href="/notebook" className="nav-link">📓 Open Notebook</a>
          <a href="/jupyterlab" className="nav-link">🧪 JupyterLab</a>
          <a href="/grafana" className="nav-link">📊 Grafana</a>
          <button className="btn-sm">Sign out</button>
        </div>
      </header>
      <WireframeBoundary>
        <div style={{ marginTop: 32 }}>
          <h2>Welcome to Gentoofoo AI Lab (Air-Gapped)</h2>
          <p>This dashboard provides access to local LLMs, agents, notebooks, and observability tools.</p>
          <ServiceHealth />
          <ChatWidget />
          <ZeroClawPanel />
          <ResearchPanel />
        </div>
      </WireframeBoundary>
    </div>
  );
}
