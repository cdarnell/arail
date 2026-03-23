import React from 'react';
import CriticalCheckButton from './CriticalCheckButton';

export default function ZeroClawPanel() {
  return (
    <div style={{ margin: '24px 0' }}>
      <h3>ZeroClaw Routing</h3>
      <p>Routing metrics and agent status will appear here.</p>
      <CriticalCheckButton />
      {/* TODO: Integrate with ZeroClaw metrics endpoint */}
    </div>
  );
}
