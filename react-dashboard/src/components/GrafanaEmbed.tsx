import React from 'react';

export default function GrafanaEmbed() {
  return (
    <div style={{ padding: 32 }}>
      <h2>Grafana Dashboard</h2>
      <iframe
        src="http://localhost:3000/d/ai-lab-observability/ai-lab-observability"
        title="Grafana"
        style={{ width: '100%', height: '80vh', border: 'none', borderRadius: 8 }}
      />
      <p>Embedded Grafana dashboard for local observability.</p>
    </div>
  );
}
