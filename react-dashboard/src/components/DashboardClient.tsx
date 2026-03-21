import React from 'react';
import ServiceHealth from './ServiceHealth';
import ChatWidget from './ChatWidget';
import ZeroClawPanel from './ZeroClawPanel';
import ResearchPanel from './ResearchPanel';
import WireframeBoundary from './WireframeBoundary';

  const [rawMode, setRawMode] = React.useState(false);
  const [showModal, setShowModal] = React.useState(false);
  const [airGap, setAirGap] = React.useState(true); // AirGap enabled by default
  // For RAW MODE flashing effect
  const [flash, setFlash] = React.useState(false);
  React.useEffect(() => {
    if (rawMode) {
      setFlash(true);
      const interval = setInterval(() => setFlash(f => !f), 400);
      return () => clearInterval(interval);
    } else {
      setFlash(false);
    }
  }, [rawMode]);
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
          {/* AirGap Button */}
          <button
            style={{
              background: airGap ? '#22c55e' : '#2563eb', // green if enabled, blue if not
              color: '#fff',
              border: 'none',
              borderRadius: '50%',
              width: 48,
              height: 48,
              fontWeight: 900,
              fontSize: '2rem',
              marginLeft: 8,
              boxShadow: airGap ? '0 0 0 3px #22c55e' : '0 0 0 3px #2563eb',
              cursor: 'pointer',
              transition: 'background 0.2s',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              outline: airGap ? '2px solid #22c55e' : '2px solid #2563eb',
            }}
            title={
              airGap
                ? 'AirGap ENABLED: All outbound (egress) internet traffic is blocked. Internal services, observability, and agents are running.\n\nEverything is secure and isolated.'
                : 'AirGap DISABLED: Outbound internet traffic is allowed.\n\nYou can breathe, but the lab is no longer isolated.'
            }
            aria-label="AirGap Mode"
            onClick={() => setAirGap(a => !a)}
          >
            {airGap ? '🟢' : '🔵'}
          </button>
          {/* RAW MODE (Panic) Button */}
          <button
            style={{
              background: rawMode ? (flash ? '#7f1d1d' : '#b91c1c') : '#7f1d1d', // dark red, flashes when active
              color: '#fff',
              border: 'none',
              borderRadius: '50%',
              width: 48,
              height: 48,
              fontWeight: 900,
              fontSize: '2rem',
              marginLeft: 8,
              boxShadow: rawMode ? '0 0 0 3px #b91c1c' : '0 0 0 3px #7f1d1d',
              cursor: 'pointer',
              transition: 'background 0.2s',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              outline: '2px solid #b91c1c',
              animation: rawMode ? 'flash 1s infinite' : 'none',
            }}
            title={
              rawMode
                ? 'RAW MODE: All safety, mesh, observability, and automation are OFF.\n\nUse only for emergencies or fire drills. No background jobs, no security, no telemetry.'
                : 'Panic Button: Halts all mesh, security, observability, and agents.\n\nUse only for emergencies or fire drills.\n\nAll background activity will stop, and you can perform one focused action in a silent environment.'
            }
            onClick={() => {
              setRawMode(r => !r);
              setShowModal(true);
            }}
            aria-label="RAW MODE Break Glass"
          >
            {rawMode ? '🚨' : '☢️'}
          </button>
          <button className="btn-sm">Sign out</button>
        </div>
      </header>
      {showModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100vw',
          height: '100vh',
          background: 'rgba(0,0,0,0.55)',
          zIndex: 1000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <div style={{
            background: '#fff',
            borderRadius: 16,
            padding: 36,
            maxWidth: 420,
            boxShadow: '0 8px 32px #0006',
            textAlign: 'center',
            border: '4px solid #fbbf24',
          }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>{rawMode ? '🔔' : '☢️'}</div>
            <h2 style={{ color: '#b91c1c', margin: 0 }}>RAW MODE</h2>
            <p style={{ color: '#7c2d12', fontWeight: 600, fontSize: 18, margin: '16px 0' }}>
              No Metrics, No Tracing, No Security.<br />
              <span style={{ color: '#b91c1c', fontWeight: 700 }}>Use only when sleeping or for emergencies!</span>
            </p>
            <p style={{ color: '#444', fontSize: 15, margin: '12px 0 24px' }}>
              <b>RAW MODE disables all background jobs, observability, and mesh protections.</b><br />
              <span style={{ color: '#f59e42' }}>This is the nuclear option. Proceed with caution!</span>
            </p>
            <button
              style={{
                background: '#fbbf24',
                color: '#7c2d12',
                border: 'none',
                borderRadius: 8,
                padding: '10px 28px',
                fontWeight: 800,
                fontSize: '1.1rem',
                marginTop: 8,
                cursor: 'pointer',
                boxShadow: '0 0 0 2px #fbbf24',
              }}
              onClick={() => setShowModal(false)}
            >
              {rawMode ? 'Resume Normal Mode' : 'Enter RAW MODE'}
            </button>
          </div>
        </div>
      )}
      <WireframeBoundary>
        <div style={{ marginTop: 32 }}>
          <h2>Welcome to Gentoofoo AI Lab (Air-Gapped)</h2>
          <p>This dashboard provides access to local LLMs, agents, notebooks, and observability tools.</p>
          {rawMode && (
            <div style={{
              background: '#fbbf24',
              color: '#7c2d12',
              padding: '10px 18px',
              borderRadius: 8,
              fontWeight: 700,
              marginBottom: 16,
              fontSize: '1.1rem',
              boxShadow: '0 0 0 2px #fbbf24',
              display: 'inline-block',
            }}>
              ☢️ RAW MODE: All background jobs, metrics, and mesh protections are OFF.
            </div>
          )}
          <ServiceHealth />
          <ChatWidget />
          <ZeroClawPanel />
          <ResearchPanel />
        </div>
      </WireframeBoundary>
    </div>
  );
}
