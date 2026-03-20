import React from 'react';

export default function JupyterLabPanel() {
  return (
    <div style={{ padding: 32 }}>
      <h2>JupyterLab</h2>
      <iframe
        src="http://localhost:8888/lab"
        title="JupyterLab"
        style={{ width: '100%', height: '80vh', border: 'none', borderRadius: 8 }}
      />
      <p>Full JupyterLab interface (proxied from local Jupyter server).</p>
    </div>
  );
}
