import React, { useState } from 'react';

export default function ChatWidget() {
  const [prompt, setPrompt] = useState('');
  const [response, setResponse] = useState('');
  const [loading, setLoading] = useState(false);

  async function sendPrompt() {
    setLoading(true);
    setResponse('');
    try {
      // TODO: Update endpoint for LMDeploy/Opencode
      const res = await fetch('http://localhost:8000/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
      });
      const data = await res.json();
      setResponse(data.response || JSON.stringify(data));
    } catch (e) {
      setResponse('Error contacting LLM.');
    }
    setLoading(false);
  }

  return (
    <div style={{ margin: '24px 0' }}>
      <h3>LLM Chat</h3>
      <div style={{ display: 'flex', gap: 8 }}>
        <input
          value={prompt}
          onChange={e => setPrompt(e.target.value)}
          placeholder="Ask the LLM..."
          style={{ flex: 1, padding: 8, borderRadius: 6, border: '1px solid #334155' }}
        />
        <button className="btn-sm" onClick={sendPrompt} disabled={loading || !prompt.trim()}>
          {loading ? '...' : 'Send'}
        </button>
      </div>
      {response && <div style={{ marginTop: 12, color: '#94a3b8', background: '#0f172a', padding: 12, borderRadius: 8 }}>{response}</div>}
    </div>
  );
}
