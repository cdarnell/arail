export type KibDResult = {
  id: string;
  name: string;
  severity: string;
  status: string;
  note?: string;
  probe?: any;
};

export type KibDSuiteResponse = {
  overall: string;
  results: KibDResult[];
};

export async function runCriticalSuite(): Promise<KibDSuiteResponse> {
  const resp = await fetch('/api/kibd/run-suite', { method: 'POST' });
  if (!resp.ok) {
    throw new Error(`KibD run failed: ${resp.statusText}`);
  }
  return resp.json();
}
