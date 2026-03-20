import React, { useEffect, useState } from 'react';

const SERVICES = [
  { name: 'LMDeploy', url: 'http://localhost:8000/health' },
  { name: 'Opencode Gateway', url: 'http://localhost:8080/health' },
  { name: 'ZeroClaw', url: 'http://localhost:8500/health' },
  { name: 'n8n', url: 'http://localhost:5678/healthz' },
  { name: 'Kafka', url: 'http://localhost:9092' },
  { name: 'Prometheus', url: 'http://localhost:9090/-/healthy' },
  { name: 'Grafana', url: 'http://localhost:3000' },
  { name: 'Jupyter', url: 'http://localhost:8888' },
];

export default function ServiceHealth() {
  const [status, setStatus] = useState<{ [key: string]: boolean }>({});

  useEffect(() => {
    SERVICES.forEach(service => {
      fetch(service.url)
        .then(res => setStatus(s => ({ ...s, [service.name]: res.ok })))
        .catch(() => setStatus(s => ({ ...s, [service.name]: false })));
    });
  }, []);

  return (
    <div style={{ margin: '24px 0' }}>
      <h3>Service Health</h3>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        {SERVICES.map(s => (
          <span key={s.name} style={{
            padding: '6px 16px', borderRadius: 8,
            background: status[s.name] ? '#22c55e33' : '#ef444433',
            color: status[s.name] ? '#22c55e' : '#ef4444',
            border: `1px solid ${status[s.name] ? '#22c55e' : '#ef4444'}`,
            fontWeight: 600,
          }}>
            {s.name}: {status[s.name] ? 'Online' : 'Offline'}
          </span>
        ))}
      </div>
    </div>
  );
}
