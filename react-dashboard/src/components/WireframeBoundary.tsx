import React from 'react';

export default function WireframeBoundary({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      border: '2px dashed #6366f1',
      borderRadius: 16,
      padding: 24,
      margin: '24px 0',
      background: 'rgba(99,102,241,0.03)',
      position: 'relative',
    }}>
      <div style={{
        position: 'absolute',
        top: -18,
        left: 24,
        background: '#020617',
        color: '#6366f1',
        fontWeight: 700,
        fontSize: 13,
        padding: '0 10px',
        borderRadius: 8,
        letterSpacing: 1,
      }}>
        Wireframe Boundary
      </div>
      {children}
    </div>
  );
}
