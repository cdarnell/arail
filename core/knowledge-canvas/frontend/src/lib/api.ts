const BASE = (import.meta.env.VITE_API_URL as string) ?? "/knowledge-canvas";

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

export const api = {
  snapshot:      () => j<any>("/api/graph/snapshot"),
  graphStatus:   () => j<any>("/api/graph/status"),
  semanticEdges: (k = 5, threshold = 0.75) =>
    j<{ links: any[] }>(`/api/graph/semantic-edges?k=${k}&threshold=${threshold}`),
  getSource:     (id: string) => j<any>(`/api/sources/${id}`),
  ingest:        (payload: any) =>
    j<any>("/api/sources/ingest", { method: "POST", body: JSON.stringify(payload) }),
  clusterSummary: (id: string, hops = 2) =>
    j<{ summary: string }>("/api/agents/cluster-summary", {
      method: "POST", body: JSON.stringify({ source_id: id, hops }),
    }),
  discoverLinks: (threshold = 0.65, maxOrphans = 20) =>
    j<any>(`/api/agents/discover-links?threshold=${threshold}&max_orphans=${maxOrphans}`, { method: "POST" }),
  nlq: (utterance: string, k = 25) =>
    j<any>("/api/nlq/query", { method: "POST", body: JSON.stringify({ utterance, k }) }),
};
