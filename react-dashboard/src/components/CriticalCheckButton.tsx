import React, { useState } from 'react';
import { runCriticalSuite, KibDSuiteResponse } from '../lib/kibdClient';

export default function CriticalCheckButton() {
  const [state, setState] = useState<'idle'|'running'|'pass'|'fail'|'error'>('idle');
  const [details, setDetails] = useState<KibDSuiteResponse | null>(null);

  async function handleRun() {
    setState('running');
    try {
      const res = await runCriticalSuite();
      setDetails(res);
      setState(res.overall === 'pass' ? 'pass' : 'fail');
    } catch (err) {
      setState('error');
      setDetails(null);
    }
  }

  return (
    <div>
      <button onClick={handleRun} disabled={state === 'running'}>
        {state === 'idle' && 'Run Critical Diagnostics'}
        {state === 'running' && 'Scanning...'}
        {state === 'pass' && 'All Critical Checks Pass'}
        {state === 'fail' && 'Critical Issues Found'}
        {state === 'error' && 'Error Running Checks'}
      </button>

      {details && (
        <div style={{ marginTop: 12 }}>
          <b>Overall:</b> {details.overall}
          <ul>
            {details.results.map(r => (
              <li key={r.id}>{r.name}: {r.status}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
