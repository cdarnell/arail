import React from 'react';

export default function VaultGoalPanel() {
  const [token, setToken] = React.useState('');
  const [goal, setGoal] = React.useState(() => localStorage.getItem('overarchingGoal') || '');
  const [status, setStatus] = React.useState<string | null>(null);

  async function saveToken() {
    setStatus('Saving token...');
    try {
      const res = await fetch('/api/vault/store-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
        credentials: 'same-origin',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setStatus('Token saved to Vault.');
      setToken('');
    } catch (e:any) {
      setStatus('Failed to save token: ' + (e.message || e));
    }
    setTimeout(() => setStatus(null), 4000);
  }

  async function saveGoal() {
    setStatus('Saving goal...');
    try {
      // Persist locally and send to runbook backend if available
      localStorage.setItem('overarchingGoal', goal);
      await fetch('/api/runbook/goal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal }),
        credentials: 'same-origin',
      });
      setStatus('Overarching goal saved.');
    } catch (e:any) {
      // still keep local copy
      setStatus('Saved locally; backend unavailable.');
    }
    setTimeout(() => setStatus(null), 4000);
  }

  async function runValidation() {
    setStatus('Running validation...');
    try {
      const res = await fetch('/api/validate', { method: 'GET', credentials: 'same-origin' });
      const data = await res.json();
      setStatus(null);
      alert('Validation results:\n' + JSON.stringify(data, null, 2));
    } catch (e:any) {
      setStatus('Validation failed: ' + (e.message || e));
      setTimeout(() => setStatus(null), 4000);
    }
  }

  return (
    <div style={{ margin: '18px 0', padding: 12, borderRadius: 8, background: '#fbfbfc', border: '1px solid #eee' }}>
      <h3>Lab Settings</h3>

      <div style={{ marginBottom: 12 }}>
        <label style={{ display: 'block', fontWeight: 700, marginBottom: 6 }}>Store User Token (Vault)</label>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            value={token}
            onChange={e => setToken(e.target.value)}
            placeholder="Paste token to store in Vault"
            style={{ flex: 1, padding: '8px 10px', borderRadius: 6, border: '1px solid #ddd' }}
          />
          <button onClick={saveToken} className="btn-sm">Save</button>
        </div>
        <div style={{ marginTop: 8, color: '#666', fontSize: 13 }}>
          Tokens are stored in the Vault backend via the UI endpoint `/api/vault/store-token`.
        </div>
      </div>

      <div style={{ marginBottom: 6 }}>
        <label style={{ display: 'block', fontWeight: 700, marginBottom: 6 }}>Define Your Overarching Goal</label>
        <textarea
          value={goal}
          onChange={e => setGoal(e.target.value)}
          placeholder="Describe the lab's primary goal (short sentence)"
          rows={3}
          style={{ width: '100%', padding: 10, borderRadius: 6, border: '1px solid #ddd' }}
        />
        <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
          <button onClick={saveGoal} className="btn-sm">Save Goal</button>
          <button onClick={() => { setGoal(''); localStorage.removeItem('overarchingGoal'); }} className="btn-sm">Clear</button>
          <button onClick={runValidation} className="btn-sm">Run Health & Security Scan</button>
        </div>
        <div style={{ marginTop: 8, color: '#444' }}>
          Examples: Be an AI champion, Retrain models to run well on my GPU, Develop an AI app.
        </div>
      </div>

      {status && (
        <div style={{ marginTop: 10, padding: '8px 10px', background: '#11182710', borderRadius: 6 }}>{status}</div>
      )}
    </div>
  );
}
