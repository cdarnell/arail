import React from 'react';

export default function ResearchPanel() {
  return (
    <div style={{ margin: '24px 0' }}>
      <h3>Research & Experiments</h3>
      <p>Track agent activity, token usage, and experiment results here.</p>
      {/* TODO: Integrate with Prometheus/Grafana for metrics */}
    </div>
  );
}
